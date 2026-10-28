"""
Historical Contracts Backfill — fetch individual expired/live futures contracts
from Yahoo Finance using standard CME/ICE ticker codes.

This populates FuturesCurve with multiple contract_month rows per date so that
the calendar spread algorithm (which sorts contracts by month and picks M1, M6, M12)
has data for historical dates — not just the dates captured by the IB live feed.

WTI  tickers: CL{month_code}{2-digit-year}=F  (e.g. CLK26=F for May-2026)
Brent tickers: BZ{month_code}{2-digit-year}=F  (e.g. BZK26=F for May-2026)

Coverage: 3 years back + 12 months ahead by default (≈ 144 contracts × 2 symbols).
"""

import time
from datetime import date
from dateutil.relativedelta import relativedelta
from loguru import logger
import yfinance as yf

from db.database import FuturesCurve


# CME month codes (NYMEX / ICE standard)
_MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J",  5: "K",  6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}

# Map ORM symbol → Yahoo ticker prefix
_SYMBOL_PREFIX = {
    "CL":   "CL",
    "COIL": "BZ",
}


def _yahoo_ticker(prefix: str, year: int, month: int) -> str:
    """Build the Yahoo Finance futures ticker (e.g. 'CLK26=F')."""
    code = _MONTH_CODES[month]
    yr2  = str(year)[-2:]
    return f"{prefix}{code}{yr2}=F"


def _iter_contract_months(years_back: int = 3, months_ahead: int = 12):
    """
    Yield (year, month) tuples from (today - years_back) to (today + months_ahead).
    """
    today  = date.today()
    start  = today - relativedelta(years=years_back)
    end    = today + relativedelta(months=months_ahead)
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        yield cursor.year, cursor.month
        cursor += relativedelta(months=1)


def run_backfill(start_from: date, session, years_back: int = 3) -> int:
    """
    Fetch individual expired/live futures contract prices from Yahoo Finance.

    For each contract month from (today - years_back) to (today + 12 months) we
    download the full daily OHLCV history via ``yf.Ticker(ticker).history(period="max")``
    and upsert every row into FuturesCurve with the contract's own YYYY-MM as
    ``contract_month`` (not the observation date).

    Returns total FuturesCurve rows inserted.
    """
    total = 0

    contracts = list(_iter_contract_months(years_back=years_back, months_ahead=12))
    symbols   = list(_SYMBOL_PREFIX.items())  # [("CL", "CL"), ("COIL", "BZ")]

    logger.info(
        f"Historical contracts backfill: {len(contracts)} months × {len(symbols)} symbols "
        f"= {len(contracts) * len(symbols)} requests"
    )

    for sym, prefix in symbols:
        for year, month in contracts:
            ticker_str    = _yahoo_ticker(prefix, year, month)
            contract_month = f"{year:04d}-{month:02d}"

            try:
                ticker = yf.Ticker(ticker_str)
                hist   = ticker.history(period="max")

                if hist is None or hist.empty:
                    # Many expired Brent (BZ) contracts have no Yahoo data — skip silently
                    logger.debug(f"No data for {ticker_str} ({sym} {contract_month})")
                    time.sleep(0.05)
                    continue

                count = 0
                for idx, row in hist.iterrows():
                    obs_date    = idx.date() if hasattr(idx, "date") else idx
                    close_price = float(row["Close"]) if row["Close"] == row["Close"] else None
                    volume      = int(row["Volume"])  if row["Volume"] == row["Volume"] else None

                    if close_price is None or close_price <= 0:
                        continue

                    existing = session.query(FuturesCurve).filter_by(
                        date=obs_date,
                        symbol=sym,
                        contract_month=contract_month,
                    ).first()

                    if existing:
                        # Only update if we don't have a price yet (IB data takes priority)
                        if existing.settlement_price is None:
                            existing.settlement_price = close_price
                        if volume and existing.volume is None:
                            existing.volume = volume
                    else:
                        session.add(FuturesCurve(
                            date=obs_date,
                            symbol=sym,
                            contract_month=contract_month,
                            settlement_price=close_price,
                            volume=volume,
                        ))
                        count += 1

                session.commit()
                total += count

                if count:
                    logger.debug(
                        f"  {ticker_str}: {count} new rows ({sym} {contract_month})"
                    )

                # Small pause to be friendly to Yahoo's unofficial API
                time.sleep(0.1)

            except Exception as e:
                logger.warning(
                    f"Yahoo fetch failed for {ticker_str} ({sym} {contract_month}): {e}"
                )
                try:
                    session.rollback()
                except Exception:
                    pass
                time.sleep(0.2)
                continue

    logger.info(f"Historical contracts backfill complete: {total} new rows inserted.")
    return total
