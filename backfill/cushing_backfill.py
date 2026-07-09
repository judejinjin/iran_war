"""
Cushing Inventory Backfill — weekly crude oil stocks at Cushing, OK (EIA).

Series: W_EPC0_SAX_YCUOK_MBBL
  "Cushing, OK Ending Stocks excluding SPR of Crude Oil (Thousand Barrels)"
  Weekly, available from 1982-08-20 to present.

Stores into cushing_inventory table via CushingInventory ORM model.
"""

from datetime import date, datetime
import requests
from loguru import logger

from config import EIA_API_KEY, EIA_CUSHING_SERIES
from db.database import get_session, CushingInventory

EIA_API_BASE = "https://api.eia.gov/v2"
_EIA_SERIES = EIA_CUSHING_SERIES   # W_EPC0_SAX_YCUOK_MBBL


def _fetch_cushing(start_date: date) -> list[dict]:
    """Fetch weekly Cushing crude stocks from EIA API v2."""
    url = f"{EIA_API_BASE}/petroleum/stoc/wstk/data/"
    params = {
        "api_key": EIA_API_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": _EIA_SERIES,
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
        logger.warning(f"Cushing EIA fetch failed: {exc}")
        return []


def _upsert(session, row: CushingInventory):
    existing = session.query(CushingInventory).filter_by(date=row.date).first()
    if existing:
        existing.inventory_kbbl = row.inventory_kbbl
        existing.source = row.source
    else:
        session.add(row)


def run_backfill(start_from: date, session=None) -> int:
    """
    Fetch Cushing inventory from start_from to today and upsert into DB.
    Returns count of records upserted.
    """
    own_session = session is None
    if own_session:
        session = get_session()

    if not EIA_API_KEY:
        logger.warning("EIA_API_KEY not set — skipping Cushing backfill")
        return 0

    try:
        logger.info(f"Cushing backfill: fetching from {start_from} (EIA weekly)")
        rows = _fetch_cushing(start_from)
        count = 0
        for r in rows:
            try:
                raw_val = r.get("value")
                if raw_val is None or raw_val in ("", "w", "--"):
                    continue
                inventory_kbbl = float(raw_val)
                dt = datetime.strptime(r["period"][:10], "%Y-%m-%d").date()
                _upsert(session, CushingInventory(
                    date=dt,
                    inventory_kbbl=inventory_kbbl,
                    source="EIA",
                ))
                count += 1
            except Exception as exc:
                logger.debug(f"Cushing row parse error: {exc}")
                continue

        session.commit()
        logger.info(f"Cushing backfill: {count} records upserted")
        return count

    finally:
        if own_session:
            session.close()
