"""
IB Historical Futures Backfill — fetch daily bars via reqHistoricalData.
"""

import time
import calendar
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from loguru import logger
from ib_insync import Future

from config import FUTURES_SYMBOLS, FUTURES_EXCHANGE
from collectors.ib_connection import IBConnection
from db.database import FuturesCurve


# IB allows ~60 historical data requests per 10 minutes
BATCH_SIZE = 6
BATCH_PAUSE_SECONDS = 65  # Wait between batches


def _biz_days_before(d: date, n: int) -> date:
    result, counted = d, 0
    while counted < n:
        result -= timedelta(days=1)
        if result.weekday() < 5:
            counted += 1
    return result


def _cl_expiry(year: int, month: int) -> date | None:
    """CL last trading day: 3 biz days before the 25th of the prior month."""
    try:
        prev_m = month - 1 if month > 1 else 12
        prev_y = year if month > 1 else year - 1
        return _biz_days_before(date(prev_y, prev_m, 25), 3)
    except Exception:
        return None


def run_backfill(start_from: date, session) -> int:
    """
    Fetch historical daily bars for CL and COIL front 12 months from IB.
    Pacing: batch 6 contracts, wait 1 minute, next batch.
    Returns total records inserted.
    """
    conn = IBConnection()
    total = 0

    try:
        ib = conn.connect()
        today = date.today()
        duration = (today - start_from).days
        duration_str = f"{duration} D"

        # Build contract months: front 12 from start_from, skipping any
        # whose last trading day has already passed (in-delivery contracts
        # return confusing settlement data, not real trading prices).
        contract_months = []
        for i in range(12):
            dt = start_from + relativedelta(months=i)
            cm = dt.strftime("%Y-%m")
            expiry = _cl_expiry(dt.year, dt.month)
            if expiry is not None and today > expiry:
                logger.debug(f"IB backfill: skipping {cm} (expired {expiry})")
                continue
            contract_months.append(cm)

        for symbol in FUTURES_SYMBOLS:
            exchange = FUTURES_EXCHANGE.get(symbol, "NYMEX")
            logger.info(f"IB backfill: {symbol} from {start_from} ({duration} days, {len(contract_months)} contracts)")

            for batch_start in range(0, len(contract_months), BATCH_SIZE):
                batch = contract_months[batch_start:batch_start + BATCH_SIZE]

                for month_str in batch:
                    try:
                        ym = month_str.replace("-", "")
                        contract = Future(
                            symbol=symbol, exchange=exchange,
                            lastTradeDateOrContractMonth=ym,
                        )
                        ib.qualifyContracts(contract)

                        bars = ib.reqHistoricalData(
                            contract,
                            endDateTime="",
                            durationStr=duration_str,
                            barSizeSetting="1 day",
                            whatToShow="TRADES",
                            useRTH=True,
                            formatDate=1,
                        )

                        if not bars:
                            logger.debug(f"No IB history for {symbol} {month_str}")
                            continue

                        count = 0
                        for bar in bars:
                            bar_date = bar.date if isinstance(bar.date, date) else bar.date.date()

                            existing = session.query(FuturesCurve).filter_by(
                                date=bar_date, symbol=symbol, contract_month=month_str,
                            ).first()

                            if not existing:
                                session.add(FuturesCurve(
                                    date=bar_date,
                                    symbol=symbol,
                                    contract_month=month_str,
                                    settlement_price=bar.close,
                                    volume=bar.volume if bar.volume > 0 else None,
                                ))
                                count += 1

                        total += count
                        logger.debug(f"IB backfill: {symbol} {month_str} → {count} records")

                    except Exception as e:
                        logger.warning(f"IB backfill skip {symbol} {month_str}: {e}")
                        continue

                session.commit()

                # Pacing between batches
                if batch_start + BATCH_SIZE < len(contract_months):
                    logger.debug(f"IB pacing: waiting {BATCH_PAUSE_SECONDS}s...")
                    time.sleep(BATCH_PAUSE_SECONDS)

        logger.info(f"IB backfill complete: {total} total records")
        return total

    finally:
        conn.disconnect()
