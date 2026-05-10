"""
Supply/Demand Historical Backfill - global oil production and consumption.

Source: EIA API v2 international (/international/data/)
  Supply (production): activityId=1, frequency=monthly, unit=TBPD
    Products: total (productId=53), crude (57), ngpl (58)
  Demand (consumption): activityId=2, frequency=annual, unit=TBPD
    Products: total (5), gasoline (62), jet_fuel (63), diesel (65),
              residual (66), lpg (67)

Annual demand stored as Dec-31 end-of-year dates.
Monthly supply stored as end-of-month dates.
All values in thousand barrels per day (TBPD = kbd).
"""

import calendar
from datetime import date

import requests
from loguru import logger

from config import (
    EIA_API_KEY, SD_SUPPLY_PRODUCTS, SD_DEMAND_PRODUCTS,
    SD_COUNTRIES, SD_EIA_COUNTRY_MAP,
)
from db.database import get_session, SupplyDemand, init_db

EIA_API_BASE = "https://api.eia.gov/v2"
_EIA_ISO2_TO_3 = {v: k for k, v in SD_EIA_COUNTRY_MAP.items()}


def _end_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _fetch_eia_intl(
    activity_id: str,
    product_id: str,
    country_eia_codes: list[str],
    start: str,
    frequency: str = "monthly",
    unit_filter: str = "TBPD",
) -> list[dict]:
    """
    Fetch EIA international data. Filters by unit to avoid duplicate rows
    (the API returns the same value in MTOE, QBTU, TBPD, and TJ).
    """
    url = f"{EIA_API_BASE}/international/data/"
    params = {
        "api_key": EIA_API_KEY,
        "frequency": frequency,
        "data[0]": "value",
        "facets[activityId][]": activity_id,
        "facets[productId][]": product_id,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
        "start": start,
    }
    for i, code in enumerate(country_eia_codes):
        params[f"facets[countryRegionId][{i}]"] = code
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        all_rows = resp.json().get("response", {}).get("data", [])
        return [r for r in all_rows if r.get("unit") == unit_filter]
    except Exception as exc:
        logger.warning(
            f"EIA fetch failed (activity={activity_id}, product={product_id}, "
            f"freq={frequency}): {exc}"
        )
        return []


def _upsert_rows(
    session,
    rows: list[dict],
    flow: str,
    product_key: str,
    frequency: str,
) -> int:
    count = 0
    for row in rows:
        period = row.get("period", "")
        eia_code = row.get("countryRegionId", "")
        raw_val = row.get("value")
        if not period or raw_val is None:
            continue
        try:
            raw_val = float(raw_val)
        except (TypeError, ValueError):
            continue
        iso2 = SD_EIA_COUNTRY_MAP.get(eia_code)
        if not iso2:
            continue
        try:
            if frequency == "annual":
                row_date = date(int(period[:4]), 12, 31)
            else:
                year, month = int(period[:4]), int(period[5:7])
                row_date = _end_of_month(year, month)
        except (ValueError, IndexError):
            continue
        existing = session.query(SupplyDemand).filter_by(
            date=row_date, country=iso2, flow=flow, product=product_key
        ).first()
        if existing:
            existing.value_kbd = raw_val
            existing.source = "EIA"
        else:
            session.add(SupplyDemand(
                date=row_date,
                country=iso2,
                flow=flow,
                product=product_key,
                value_kbd=raw_val,
                source="EIA",
            ))
        count += 1
    if count:
        session.commit()
    return count


_BATCH_SIZE = 5  # EIA API slows significantly with many country codes per request


def _batched(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _fetch_all_batched(
    activity_id: str,
    product_id: str,
    eia_codes: list[str],
    start: str,
    frequency: str = "monthly",
) -> list[dict]:
    """Fetch all countries in batches of _BATCH_SIZE to avoid slow API responses."""
    results: list[dict] = []
    for batch in _batched(eia_codes, _BATCH_SIZE):
        batch_rows = _fetch_eia_intl(activity_id, product_id, batch, start, frequency)
        results.extend(batch_rows)
    return results


def run_backfill(start_year: int = 2015) -> dict:
    """
    Full historical backfill for all flows x products x countries.
    Supply: monthly from start_year (3 products x 5 batches of countries = 15 requests).
    Demand: annual from start_year  (6 products x 5 batches of countries = 30 requests).
    """
    init_db()
    session = get_session()
    eia_codes = [_EIA_ISO2_TO_3[iso2] for iso2 in SD_COUNTRIES if iso2 in _EIA_ISO2_TO_3]
    summary: dict[str, int] = {}
    total = 0
    try:
        # Supply (monthly)
        start_monthly = f"{start_year}-01"
        for product_key, prod_cfg in SD_SUPPLY_PRODUCTS.items():
            label = f"supply/{product_key}"
            logger.info(f"Fetching {label} (monthly, batched)...")
            rows = _fetch_all_batched(
                "1", prod_cfg["eia_product_id"], eia_codes, start_monthly, "monthly"
            )
            n = _upsert_rows(session, rows, "supply", product_key, "monthly")
            summary[label] = n
            total += n
            logger.info(f"  upserted {n} rows")

        # Demand (annual)
        start_annual = str(start_year)
        for product_key, prod_cfg in SD_DEMAND_PRODUCTS.items():
            label = f"demand/{product_key}"
            logger.info(f"Fetching {label} (annual, batched)...")
            rows = _fetch_all_batched(
                "2", prod_cfg["eia_product_id"], eia_codes, start_annual, "annual"
            )
            n = _upsert_rows(session, rows, "demand", product_key, "annual")
            summary[label] = n
            total += n
            logger.info(f"  upserted {n} rows")

    finally:
        session.close()

    logger.info(f"Supply/demand backfill complete: {total} rows total")
    return {"total": total, "by_flow_product": summary}


def run_incremental(lookback_months: int = 3) -> int:
    """Incremental refresh - supply: last N months; demand: last 2 years."""
    today = date.today()
    m = today.month - lookback_months
    y = today.year
    while m < 1:
        m += 12
        y -= 1
    start_monthly = f"{y}-{m:02d}"
    start_annual = str(today.year - 2)

    init_db()
    session = get_session()
    eia_codes = [_EIA_ISO2_TO_3[iso2] for iso2 in SD_COUNTRIES if iso2 in _EIA_ISO2_TO_3]
    total = 0
    try:
        for product_key, prod_cfg in SD_SUPPLY_PRODUCTS.items():
            rows = _fetch_all_batched(
                "1", prod_cfg["eia_product_id"], eia_codes, start_monthly, "monthly"
            )
            total += _upsert_rows(session, rows, "supply", product_key, "monthly")

        for product_key, prod_cfg in SD_DEMAND_PRODUCTS.items():
            rows = _fetch_all_batched(
                "2", prod_cfg["eia_product_id"], eia_codes, start_annual, "annual"
            )
            total += _upsert_rows(session, rows, "demand", product_key, "annual")
    finally:
        session.close()

    logger.info(f"Supply/demand incremental refresh: {total} rows")
    return total


if __name__ == "__main__":
    result = run_backfill(start_year=2015)
    print(f"Done - {result['total']} rows")
    for k, v in result["by_flow_product"].items():
        print(f"  {k}: {v}")
