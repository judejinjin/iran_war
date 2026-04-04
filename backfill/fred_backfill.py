"""
FRED Historical Backfill — fetch WTI + Brent daily spot prices.
"""

from datetime import date, timedelta
from loguru import logger
from fredapi import Fred

from config import FRED_API_KEY, FRED_WTI_SERIES, FRED_BRENT_SERIES
from db.database import FuturesCurve


def run_backfill(start_from: date, session) -> int:
    """
    Fetch FRED daily spot prices for WTI and Brent from start_from to today.
    Returns total records inserted.
    """
    if not FRED_API_KEY:
        raise ValueError("FRED_API_KEY not set in .env")

    fred = Fred(api_key=FRED_API_KEY)
    today = date.today()
    total = 0

    for series_id, symbol in [(FRED_WTI_SERIES, "CL"), (FRED_BRENT_SERIES, "BZ")]:
        logger.info(f"FRED backfill: fetching {series_id} ({symbol}) from {start_from} to {today}")

        try:
            data = fred.get_series(series_id, observation_start=start_from, observation_end=today)

            if data is None or data.empty:
                logger.warning(f"FRED returned no data for {series_id}")
                continue

            count = 0
            for dt, price in data.items():
                if price is None or price != price:  # NaN check
                    continue

                obs_date = dt.date() if hasattr(dt, 'date') else dt
                # FRED spot = front-month equivalent
                contract_month = obs_date.strftime("%Y-%m")

                existing = session.query(FuturesCurve).filter_by(
                    date=obs_date, symbol=symbol, contract_month=contract_month
                ).first()

                if not existing:
                    session.add(FuturesCurve(
                        date=obs_date,
                        symbol=symbol,
                        contract_month=contract_month,
                        settlement_price=float(price),
                    ))
                    count += 1

            session.commit()
            total += count
            logger.info(f"FRED backfill: inserted {count} records for {symbol}")

        except Exception as e:
            logger.error(f"FRED backfill error for {series_id}: {e}")
            raise

    return total
