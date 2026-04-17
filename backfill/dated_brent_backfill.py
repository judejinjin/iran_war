"""
Dated Brent Physical Price Backfill — three independent sources.

Sources:
  FRED — DCOILBRENTEU   daily 1987+  (EIA/Platts republication, 1-2 day lag)
  EIA  — RBRTED         daily 1987+  (same underlying, 0-1 day lag)
  IMF  — POILBREUSDM    monthly 1990+ (via FRED; same IMF data as DUB series)

All records stored in physical_prices table with symbol='DATED_BRENT'.
start_from arg is intentionally ignored — always fetches full history so all
three sources stay aligned back to 1987/1990.
"""

from datetime import date
from loguru import logger
import requests

from config import FRED_API_KEY, EIA_API_KEY, FRED_BRENT_SERIES, EIA_BRENT_SERIES
from db.database import PhysicalPrice

SYMBOL = "DATED_BRENT"
_DAILY_START = date(1987, 1, 1)
_MONTHLY_START = date(1990, 1, 1)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _upsert(session, obs_date: date, price: float, source: str, freq: str):
    existing = session.query(PhysicalPrice).filter_by(
        date=obs_date, symbol=SYMBOL, source=source
    ).first()
    if existing:
        existing.price = price          # refresh in case value was revised
    else:
        session.add(PhysicalPrice(
            date=obs_date, symbol=SYMBOL, price=price, source=source, freq=freq
        ))


# ─── Source: FRED ────────────────────────────────────────────────────────────

def _fetch_fred(session) -> int:
    """DCOILBRENTEU — EIA daily Brent spot rereleased via FRED."""
    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set — skipping FRED Dated Brent fetch")
        return 0
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        data = fred.get_series(FRED_BRENT_SERIES, observation_start=_DAILY_START)
        if data is None or data.empty:
            logger.warning("FRED returned empty data for DCOILBRENTEU")
            return 0
        count = 0
        for dt, price in data.items():
            if price is None or price != price:   # NaN guard
                continue
            obs_date = dt.date() if hasattr(dt, "date") else dt
            _upsert(session, obs_date, float(price), "FRED", "daily")
            count += 1
        session.commit()
        logger.info(f"Dated Brent FRED: processed {count} records")
        return count
    except Exception as e:
        logger.error(f"Dated Brent FRED fetch error: {e}")
        session.rollback()
        return 0


# ─── Source: EIA ─────────────────────────────────────────────────────────────

def _fetch_eia(session) -> int:
    """RBRTED — EIA daily Europe Brent spot price (same Platts assessment, lower lag)."""
    if not EIA_API_KEY:
        logger.warning("EIA_API_KEY not set — skipping EIA Dated Brent fetch")
        return 0
    try:
        url = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
        count = 0
        offset = 0
        page_size = 5000

        while True:
            params = {
                "api_key": EIA_API_KEY,
                "frequency": "daily",
                "data[0]": "value",
                "facets[series][]": EIA_BRENT_SERIES,
                "start": _DAILY_START.isoformat(),
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "length": page_size,
                "offset": offset,
            }
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            records = resp.json().get("response", {}).get("data", [])
            if not records:
                break
            for row in records:
                price_val = row.get("value")
                if price_val is None:
                    continue
                try:
                    obs_date = date.fromisoformat(row["period"][:10])
                    price = float(price_val)
                except (ValueError, KeyError, TypeError):
                    continue
                _upsert(session, obs_date, price, "EIA", "daily")
                count += 1
            if len(records) < page_size:
                break
            offset += page_size

        session.commit()
        logger.info(f"Dated Brent EIA: processed {count} records")
        return count
    except Exception as e:
        logger.error(f"Dated Brent EIA fetch error: {e}")
        session.rollback()
        return 0


# ─── Source: IMF (via FRED POILBREUSDM) ──────────────────────────────────────

def _fetch_imf(session) -> int:
    """POILBREUSDM — IMF monthly Brent crude spot price, retrieved via FRED."""
    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set — skipping IMF Dated Brent fetch")
        return 0
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        data = fred.get_series("POILBREUSDM", observation_start=_MONTHLY_START)
        if data is None or data.empty:
            logger.warning("FRED returned empty data for POILBREUSDM")
            return 0
        count = 0
        for dt, price in data.items():
            if price is None or price != price:
                continue
            obs_date = dt.date() if hasattr(dt, "date") else dt
            _upsert(session, obs_date, float(price), "IMF", "monthly")
            count += 1
        session.commit()
        logger.info(f"Dated Brent IMF: processed {count} records")
        return count
    except Exception as e:
        logger.error(f"Dated Brent IMF fetch error: {e}")
        session.rollback()
        return 0


# ─── Entry point ─────────────────────────────────────────────────────────────

def run_backfill(start_from: date, session) -> int:
    """
    Fetch Dated Brent physical prices from FRED, EIA, and IMF.
    start_from is ignored — always fetches full history (1987+).
    Returns total records inserted/updated.
    """
    logger.info("Dated Brent backfill: fetching from FRED, EIA, IMF …")
    total = 0
    total += _fetch_fred(session)
    total += _fetch_eia(session)
    total += _fetch_imf(session)
    logger.info(f"Dated Brent backfill complete: {total} total records")
    return total
