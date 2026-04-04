"""
EIA Historical Backfill — weekly petroleum status, production data.
"""

from datetime import date
from loguru import logger
import requests

from config import EIA_API_KEY, EIA_CRUDE_INVENTORY, EIA_US_PRODUCTION
from db.database import FuturesCurve


EIA_API_BASE = "https://api.eia.gov/v2"


def _fetch_eia_series(series_id: str, start_date: date) -> list[dict]:
    """Fetch a time series from EIA API v2."""
    # Parse the series_id: PET.WCESTUS1.W → frequency=weekly, series=PET
    parts = series_id.split(".")
    if len(parts) < 3:
        raise ValueError(f"Invalid EIA series ID: {series_id}")

    # EIA v2 endpoint
    url = f"{EIA_API_BASE}/petroleum/sum/sndw/data/"
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

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    return data.get("response", {}).get("data", [])


def run_backfill(start_from: date, session) -> int:
    """
    Fetch EIA weekly crude inventories and production from start_from to today.
    Stores as metadata alongside futures data.
    Returns total records fetched.
    """
    if not EIA_API_KEY:
        raise ValueError("EIA_API_KEY not set in .env")

    total = 0

    for series_id, description in [
        (EIA_CRUDE_INVENTORY, "US Crude Inventories"),
        (EIA_US_PRODUCTION, "US Crude Production"),
    ]:
        logger.info(f"EIA backfill: {description} ({series_id}) from {start_from}")
        try:
            records = _fetch_eia_series(series_id, start_from)
            logger.info(f"EIA returned {len(records)} records for {description}")
            total += len(records)
        except Exception as e:
            logger.error(f"EIA backfill error for {series_id}: {e}")
            # Don't raise — EIA is supplementary, continue with other sources

    return total
