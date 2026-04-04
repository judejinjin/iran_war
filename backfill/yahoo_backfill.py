"""
Yahoo Finance Historical Backfill — fetch CL=F + BZ=F daily OHLCV.
"""

from datetime import date
from loguru import logger
import yfinance as yf

from db.database import FuturesCurve


YAHOO_TICKERS = {"CL=F": "CL", "BZ=F": "BZ"}


def run_backfill(start_from: date, session) -> int:
    """
    Fetch Yahoo Finance daily data for WTI and Brent front-month.
    Used as cross-check for FRED data and to get volume.
    Returns total records inserted/updated.
    """
    today = date.today()
    total = 0

    for ticker_str, symbol in YAHOO_TICKERS.items():
        logger.info(f"Yahoo backfill: fetching {ticker_str} ({symbol}) from {start_from}")

        try:
            ticker = yf.Ticker(ticker_str)
            hist = ticker.history(start=str(start_from), end=str(today))

            if hist is None or hist.empty:
                logger.warning(f"Yahoo returned no data for {ticker_str}")
                continue

            count = 0
            for idx, row in hist.iterrows():
                obs_date = idx.date() if hasattr(idx, 'date') else idx
                contract_month = obs_date.strftime("%Y-%m")
                close_price = float(row["Close"]) if row["Close"] == row["Close"] else None
                volume = int(row["Volume"]) if row["Volume"] == row["Volume"] else None

                if close_price is None or close_price <= 0:
                    continue

                existing = session.query(FuturesCurve).filter_by(
                    date=obs_date, symbol=symbol, contract_month=contract_month
                ).first()

                if existing:
                    # Update volume from Yahoo if we got it from FRED (which has no volume)
                    if volume and volume > 0:
                        existing.volume = volume
                else:
                    session.add(FuturesCurve(
                        date=obs_date,
                        symbol=symbol,
                        contract_month=contract_month,
                        settlement_price=close_price,
                        volume=volume,
                    ))
                    count += 1

            session.commit()
            total += count
            logger.info(f"Yahoo backfill: {count} new records for {symbol}")

        except Exception as e:
            logger.error(f"Yahoo backfill error for {ticker_str}: {e}")
            raise

    return total
