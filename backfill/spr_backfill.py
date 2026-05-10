"""
SPR Historical Backfill — Strategic Petroleum Reserve levels.

Data sources:
  - EIA API v2: US SPR (WCSSTUS1) + US commercial stocks (WCESTUS1) — weekly
  - EIA API v2 international: JP, DE, FR, IT, KR total petroleum stocks — monthly
    (activityId=5 "Stocks, OECD", productId=5 "Petroleum and other liquids")

Stores data in spr_levels table via SprLevel ORM model.
"""

from datetime import date, datetime
import calendar
import requests
from loguru import logger

from config import (
    EIA_API_KEY, EIA_SPR_SERIES, EIA_COMMERCIAL_SERIES,
    US_CRUDE_DEMAND_KBD, SPR_COUNTRIES,
)
from db.database import get_session, SprLevel

EIA_API_BASE = "https://api.eia.gov/v2"

# EIA international country IDs → our internal codes (OECD members only)
_EIA_INTL_COUNTRY_MAP = {
    "JPN": "JP",
    "DEU": "DE",
    "FRA": "FR",
    "ITA": "IT",
    "KOR": "KR",
}


def _fetch_eia_weekly(series_id: str, start_date: date) -> list[dict]:
    """Fetch a weekly EIA petroleum series from API v2."""
    url = f"{EIA_API_BASE}/petroleum/stoc/wstk/data/"
    params = {
        "api_key": EIA_API_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": series_id,
        "start": start_date.strftime("%Y-%m-%d"),
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("response", {}).get("data", [])
    except Exception as exc:
        logger.warning(f"EIA SPR fetch failed for {series_id}: {exc}")
        return []


def _fetch_eia_international(eia_codes: list[str], start_date: date) -> list[dict]:
    """
    Fetch monthly total petroleum stocks for OECD countries via EIA international API.
    Returns raw API rows with 'period' (YYYY-MM), 'countryRegionId', 'value' (MBBL).
    """
    url = f"{EIA_API_BASE}/international/data/"
    params = {
        "api_key": EIA_API_KEY,
        "frequency": "monthly",
        "data[0]": "value",
        "facets[activityId][]": "5",   # Stocks, OECD
        "facets[productId][]": "5",    # Petroleum and other liquids
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
        "start": start_date.strftime("%Y-%m"),
    }
    for i, code in enumerate(eia_codes):
        params[f"facets[countryRegionId][{i}]"] = code
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("response", {}).get("data", [])
    except Exception as exc:
        logger.warning(f"EIA international stocks fetch failed: {exc}")
        return []


def _upsert(session, row: SprLevel):
    """Insert or replace an SprLevel row."""
    existing = session.query(SprLevel).filter_by(
        date=row.date, country_code=row.country_code
    ).first()
    if existing:
        existing.spr_mbbl        = row.spr_mbbl
        existing.commercial_mbbl = row.commercial_mbbl
        existing.total_mbbl      = row.total_mbbl
        existing.days_of_cover   = row.days_of_cover
        existing.source          = row.source
    else:
        session.add(row)


def run_backfill(start_from: date, session=None) -> int:
    """
    Fetch SPR data from start_from to today.
    Returns total records upserted.
    """
    own_session = session is None
    if own_session:
        session = get_session()

    total = 0
    today = date.today()

    try:
        # ── US SPR from EIA ───────────────────────────────────────────────
        if not EIA_API_KEY:
            logger.warning("EIA_API_KEY not set — skipping US SPR backfill")
        else:
            logger.info(f"SPR backfill: US SPR (EIA) from {start_from}")
            spr_rows  = _fetch_eia_weekly(EIA_SPR_SERIES, start_from)
            comm_rows = _fetch_eia_weekly(EIA_COMMERCIAL_SERIES, start_from)

            # Build date → value maps (values in thousand barrels → convert to Mbbl)
            spr_map  = {}
            for r in spr_rows:
                try:
                    dt  = datetime.strptime(r["period"][:10], "%Y-%m-%d").date()
                    val = float(r["value"]) / 1000.0   # kbd → Mbbl
                    spr_map[dt] = val
                except Exception:
                    continue

            comm_map = {}
            for r in comm_rows:
                try:
                    dt  = datetime.strptime(r["period"][:10], "%Y-%m-%d").date()
                    val = float(r["value"]) / 1000.0
                    comm_map[dt] = val
                except Exception:
                    continue

            all_dates = sorted(set(spr_map) | set(comm_map))
            demand_mbd = US_CRUDE_DEMAND_KBD / 1000.0

            for dt in all_dates:
                spr_mbbl  = spr_map.get(dt)
                comm_mbbl = comm_map.get(dt)
                total_mbbl = None
                if spr_mbbl is not None and comm_mbbl is not None:
                    total_mbbl = spr_mbbl + comm_mbbl
                days_cover = round(spr_mbbl / demand_mbd, 1) if spr_mbbl and demand_mbd else None

                _upsert(session, SprLevel(
                    date=dt,
                    country_code="US",
                    country_name="United States",
                    spr_mbbl=spr_mbbl,
                    commercial_mbbl=comm_mbbl,
                    total_mbbl=total_mbbl,
                    days_of_cover=days_cover,
                    source="EIA",
                ))
                total += 1

            session.commit()
            logger.info(f"SPR backfill: US — {total} records")

        # ── International stocks from EIA international (OECD, annual) ────
        intl_codes = list(_EIA_INTL_COUNTRY_MAP.keys())
        logger.info(f"SPR backfill: international (EIA intl monthly) from {start_from}")
        intl_rows = _fetch_eia_international(intl_codes, start_from)
        intl_count = 0
        for r in intl_rows:
            try:
                eia_code = r.get("countryRegionId", "")
                our_code = _EIA_INTL_COUNTRY_MAP.get(eia_code)
                if not our_code:
                    continue
                raw_val = r.get("value")
                if raw_val is None or raw_val == "w":
                    continue
                spr_mbbl = float(raw_val)   # already in MBBL
                period = r["period"]        # YYYY-MM
                year = int(period[:4])
                month = int(period[5:7])
                last_day = calendar.monthrange(year, month)[1]
                dt = date(year, month, last_day)  # end-of-month date
                country_name = SPR_COUNTRIES.get(our_code, r.get("countryRegionName", our_code))
                _upsert(session, SprLevel(
                    date=dt,
                    country_code=our_code,
                    country_name=country_name,
                    spr_mbbl=spr_mbbl,
                    commercial_mbbl=None,
                    total_mbbl=spr_mbbl,
                    days_of_cover=None,
                    source="EIA-Intl",
                ))
                intl_count += 1
            except Exception as exc:
                logger.debug(f"EIA intl row parse error: {exc}")
                continue

        session.commit()
        total += intl_count
        logger.info(f"SPR backfill: international — {intl_count} records")

    finally:
        if own_session:
            session.close()

    return total
