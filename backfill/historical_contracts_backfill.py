"""
Historical Contracts Backfill — fetch expired/live individual futures contracts
from Interactive Brokers using reqHistoricalData with includeExpired=True.

This populates FuturesCurve with multiple contract_month rows per date so the
calendar spread algorithm (M1-M2 / M1-M6 / M1-M12) has data going back N years,
not just from when the live IB feed started.

IB pacing rules apply: ~60 requests per 10 min.
BATCH_SIZE=6 with 65s pause between batches keeps us well under the limit.

Estimated runtime for 3yr × 2 symbols = 72 contracts:
  12 batches × ~65s = ~14 minutes (one-time; subsequent runs are incremental).

Requires TWS to be running on startup.
"""

import time
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from loguru import logger
from ib_insync import Future

from config import FUTURES_SYMBOLS, FUTURES_EXCHANGE
from collectors.ib_connection import IBConnection
from db.database import FuturesCurve


# IB pacing: stay well under 60 requests/10 min
BATCH_SIZE = 6
BATCH_PAUSE_SECONDS = 65

# Each futures contract trades for roughly 12-14 months before expiry.
# Requesting 400 days captures the full trading life of any single contract.
CONTRACT_DURATION_STR = "400 D"


def _iter_contract_months(years_back: int = 3, months_ahead: int = 12):
    """
    Yield YYYY-MM strings from (today - years_back) to (today + months_ahead).
    """
    today  = date.today()
    start  = today - relativedelta(years=years_back)
    end    = today + relativedelta(months=months_ahead)
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        yield cursor.strftime("%Y-%m")
        cursor += relativedelta(months=1)


def run_backfill(start_from: date, session, years_back: int = 3) -> int:
    """
    Fetch daily settlement prices for each contract month (expired and live)
    from IB and upsert into FuturesCurve.

    start_from is accepted for BackfillManager compatibility but the actual
    coverage is always (today - years_back) → (today + 12 months) to ensure
    we have a full multi-contract curve for every historical date.

    Returns total new FuturesCurve rows inserted.
    """
    conn = IBConnection()
    total = 0

    try:
        ib = conn.connect()

        contract_months = list(_iter_contract_months(years_back=years_back))
        logger.info(
            f"IB historical contracts backfill: {len(contract_months)} months "
            f"× {len(FUTURES_SYMBOLS)} symbols = "
            f"{len(contract_months) * len(FUTURES_SYMBOLS)} requests "
            f"(~{len(contract_months) * len(FUTURES_SYMBOLS) // BATCH_SIZE + 1} batches × {BATCH_PAUSE_SECONDS}s)"
        )

        for symbol in FUTURES_SYMBOLS:
            exchange = FUTURES_EXCHANGE.get(symbol, "NYMEX")

            for batch_start in range(0, len(contract_months), BATCH_SIZE):
                batch = contract_months[batch_start:batch_start + BATCH_SIZE]

                for month_str in batch:
                    ym = month_str.replace("-", "")
                    try:
                        contract = Future(
                            symbol=symbol,
                            exchange=exchange,
                            lastTradeDateOrContractMonth=ym,
                            includeExpired=True,
                        )
                        # Do NOT call qualifyContracts for expired futures — IB's
                        # reqContractDetails does not return expired contracts so the
                        # contract would remain unqualified (conId=0) and
                        # reqHistoricalData would silently return [].
                        # The full spec (symbol+exchange+lastTradeDateOrContractMonth
                        # +includeExpired) is sufficient for IB to serve historical data.

                        bars = ib.reqHistoricalData(
                            contract,
                            endDateTime="",
                            durationStr=CONTRACT_DURATION_STR,
                            barSizeSetting="1 day",
                            whatToShow="TRADES",
                            useRTH=True,
                            formatDate=1,
                            keepUpToDate=False,
                        )

                        if not bars:
                            logger.debug(f"IB: no history for {symbol} {month_str}")
                            continue

                        count = 0
                        for bar in bars:
                            bar_date = (
                                bar.date if isinstance(bar.date, date) else bar.date.date()
                            )

                            existing = session.query(FuturesCurve).filter_by(
                                date=bar_date,
                                symbol=symbol,
                                contract_month=month_str,
                            ).first()

                            if not existing:
                                session.add(FuturesCurve(
                                    date=bar_date,
                                    symbol=symbol,
                                    contract_month=month_str,
                                    settlement_price=float(bar.close),
                                    volume=int(bar.volume) if bar.volume and bar.volume > 0 else None,
                                ))
                                count += 1
                            else:
                                # Back-fill volume if IB has it and DB doesn't
                                if bar.volume and bar.volume > 0 and existing.volume is None:
                                    existing.volume = int(bar.volume)

                        session.commit()
                        total += count

                        if count:
                            logger.debug(f"  {symbol} {month_str}: +{count} rows")

                    except Exception as e:
                        logger.warning(
                            f"IB historical contracts: skip {symbol} {month_str}: {e}"
                        )
                        try:
                            session.rollback()
                        except Exception:
                            pass
                        continue

                # Pacing between batches (skip pause after last batch)
                if batch_start + BATCH_SIZE < len(contract_months):
                    logger.debug(f"IB pacing pause {BATCH_PAUSE_SECONDS}s...")
                    time.sleep(BATCH_PAUSE_SECONDS)

        logger.info(
            f"IB historical contracts backfill complete: {total} new rows inserted."
        )
        return total

    finally:
        conn.disconnect()

