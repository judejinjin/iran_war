"""
IB Futures Data Collector — fetches CL + COIL term structures and spreads.
"""

from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from loguru import logger
from ib_insync import Future, util

import time as _time

from config import FUTURES_SYMBOLS, FUTURES_EXCHANGE, FUTURES_MONTHS_AHEAD
from collectors.ib_connection import IBConnection
from db.database import get_session, FuturesCurve, Spread


def _build_contract_months(n_months: int) -> list[str]:
    """Return next n_months as 'YYYY-MM' strings starting from current month."""
    today = date.today()
    months = []
    for i in range(n_months):
        dt = today + relativedelta(months=i)
        months.append(dt.strftime("%Y-%m"))
    return months


def _make_ib_future(symbol: str, contract_month: str, exchange: str) -> Future:
    """Create an IB Future contract object for the given month."""
    # IB expects lastTradeDateOrContractMonth as YYYYMM
    ym = contract_month.replace("-", "")
    return Future(symbol=symbol, exchange=exchange, lastTradeDateOrContractMonth=ym)


def collect_futures_snapshot(ib_conn: IBConnection = None) -> dict:
    """
    Fetch current futures curves for CL and BZ, store in DB.
    Returns dict with counts: {"CL": n, "COIL": m}.
    """
    own_connection = ib_conn is None
    if own_connection:
        ib_conn = IBConnection()

    try:
        ib = ib_conn.ensure_connected()
        session = get_session()
        today = date.today()
        months = _build_contract_months(FUTURES_MONTHS_AHEAD)
        counts = {}

        for symbol in FUTURES_SYMBOLS:
            exchange = FUTURES_EXCHANGE.get(symbol, "NYMEX")
            symbol_count = 0

            for month_str in months:
                try:
                    contract = _make_ib_future(symbol, month_str, exchange)
                    qualified = ib.qualifyContracts(contract)
                    if not qualified:
                        continue

                    price = None
                    volume = None

                    # Try snapshot first (works during market hours)
                    try:
                        ticker = ib.reqMktData(contract, snapshot=True)
                        ib.sleep(2)
                        price = ticker.last or ticker.close
                        if price is None or price <= 0:
                            price = ticker.bid if ticker.bid and ticker.bid > 0 else None
                        volume = ticker.volume if ticker.volume and ticker.volume != -1 else None
                        ib.cancelMktData(contract)
                    except Exception:
                        pass

                    # Fallback to historical data (works outside market hours)
                    if price is None or price <= 0:
                        bars = ib.reqHistoricalData(
                            contract, endDateTime="", durationStr="3 D",
                            barSizeSetting="1 day", whatToShow="TRADES",
                            useRTH=True, formatDate=1,
                        )
                        if bars:
                            price = bars[-1].close
                            volume = int(bars[-1].volume) if bars[-1].volume > 0 else None

                    if price is None or price <= 0:
                        continue

                    # Upsert into DB
                    existing = session.query(FuturesCurve).filter_by(
                        date=today, symbol=symbol, contract_month=month_str
                    ).first()

                    if existing:
                        existing.settlement_price = price
                        existing.volume = volume
                    else:
                        row = FuturesCurve(
                            date=today,
                            symbol=symbol,
                            contract_month=month_str,
                            settlement_price=price,
                            volume=volume,
                            open_interest=None,
                        )
                        session.add(row)

                    symbol_count += 1
                    ib.sleep(0.3)

                except Exception as e:
                    logger.warning(f"Failed to fetch {symbol} {month_str}: {e}")
                    continue

            counts[symbol] = symbol_count
            logger.info(f"Collected {symbol_count} contract months for {symbol}")

        # Compute and store spreads
        _compute_spreads(session, today)

        session.commit()
        session.close()
        logger.info(f"Futures snapshot complete: {counts}")
        return counts

    finally:
        if own_connection:
            ib_conn.disconnect()


def _compute_spreads(session, today: date):
    """Compute Brent-WTI spread and calendar spreads, store in DB."""
    # Get today's front-month prices
    cl_rows = session.query(FuturesCurve).filter_by(
        date=today, symbol="CL"
    ).order_by(FuturesCurve.contract_month).all()

    coil_rows = session.query(FuturesCurve).filter_by(
        date=today, symbol="COIL"
    ).order_by(FuturesCurve.contract_month).all()

    if not cl_rows or not coil_rows:
        return

    # Brent-WTI spread (front month)
    coil_front = coil_rows[0].settlement_price
    cl_front = cl_rows[0].settlement_price
    if coil_front and cl_front:
        _upsert_spread(session, today, "COIL-CL", coil_rows[0].contract_month,
                        coil_rows[0].contract_month, coil_front - cl_front)

    # Calendar spreads for CL: M1-M2, M1-M6, M1-M12
    for label, back_idx in [("CL_M1-M2", 1), ("CL_M1-M6", 5), ("CL_M1-M12", 11)]:
        if len(cl_rows) > back_idx and cl_rows[0].settlement_price and cl_rows[back_idx].settlement_price:
            _upsert_spread(
                session, today, label,
                cl_rows[0].contract_month,
                cl_rows[back_idx].contract_month,
                cl_rows[0].settlement_price - cl_rows[back_idx].settlement_price,
            )

    # Calendar spreads for COIL
    for label, back_idx in [("COIL_M1-M2", 1), ("COIL_M1-M6", 5), ("COIL_M1-M12", 11)]:
        if len(coil_rows) > back_idx and coil_rows[0].settlement_price and coil_rows[back_idx].settlement_price:
            _upsert_spread(
                session, today, label,
                coil_rows[0].contract_month,
                coil_rows[back_idx].contract_month,
                coil_rows[0].settlement_price - coil_rows[back_idx].settlement_price,
            )


def collect_historical_curves(ib_conn: IBConnection = None, days_back: int = 30) -> dict:
    """
    Backfill daily futures curves for the past *days_back* business days.

    For each contract month of CL/BZ, fetches daily bars via reqHistoricalData
    and stores them in FuturesCurve.  Then computes spreads for every date that
    has enough contracts.

    Returns {"CL": rows_inserted, "COIL": rows_inserted}.
    """
    own_connection = ib_conn is None
    if own_connection:
        ib_conn = IBConnection()

    try:
        ib = ib_conn.ensure_connected()
        session = get_session()
        # Skip the first 2 months — near-term contracts may already be expired
        months = _build_contract_months(FUTURES_MONTHS_AHEAD)[2:]
        counts = {"CL": 0, "COIL": 0}
        req_count = 0  # track IB requests for pacing

        for symbol in FUTURES_SYMBOLS:
            exchange = FUTURES_EXCHANGE.get(symbol, "NYMEX")

            for i, month_str in enumerate(months):
                try:
                    contract = _make_ib_future(symbol, month_str, exchange)
                    qualified = ib.qualifyContracts(contract)
                    if not qualified:
                        logger.debug(f"Skipping unqualified {symbol} {month_str}")
                        continue

                    bars = ib.reqHistoricalData(
                        contract,
                        endDateTime="",
                        durationStr=f"{days_back} D",
                        barSizeSetting="1 day",
                        whatToShow="TRADES",
                        useRTH=True,
                        formatDate=1,
                    )
                    req_count += 1

                    if not bars:
                        _time.sleep(0.5)
                        continue

                    for bar in bars:
                        bar_date = bar.date
                        if isinstance(bar_date, str):
                            bar_date = datetime.strptime(bar_date[:10], "%Y-%m-%d").date()
                        elif isinstance(bar_date, datetime):
                            bar_date = bar_date.date()

                        price = bar.close
                        if price is None or price <= 0:
                            continue

                        vol = int(bar.volume) if bar.volume and bar.volume > 0 else None

                        existing = session.query(FuturesCurve).filter_by(
                            date=bar_date, symbol=symbol, contract_month=month_str,
                        ).first()

                        if existing:
                            existing.settlement_price = price
                            existing.volume = vol
                        else:
                            session.add(FuturesCurve(
                                date=bar_date,
                                symbol=symbol,
                                contract_month=month_str,
                                settlement_price=price,
                                volume=vol,
                                open_interest=None,
                            ))
                            counts[symbol] += 1

                    logger.info(f"  {symbol} {month_str}: {len(bars)} bars")
                    session.commit()

                    # IB drops connection after ~8 rapid requests — pause longer
                    # every 6 requests to let the server breathe
                    if req_count % 6 == 0:
                        logger.info(f"  Pacing pause after {req_count} requests...")
                        _time.sleep(10)
                    else:
                        _time.sleep(1)

                except (Exception, KeyboardInterrupt) as e:
                    logger.warning(f"Historical fetch failed {symbol} {month_str}: {e}")
                    try:
                        session.rollback()
                    except Exception:
                        pass
                    # Reconnect after disconnect
                    _time.sleep(5)
                    try:
                        ib = ib_conn.ensure_connected()
                    except Exception:
                        logger.error("Cannot reconnect to IB, stopping backfill")
                        break
                    continue

            logger.info(f"Historical backfill: inserted {counts[symbol]} rows for {symbol}")

        # Compute spreads for each date that has multi-contract data
        try:
            dates_with_data = [
                row[0] for row in session.query(FuturesCurve.date).filter(
                    FuturesCurve.date >= date.today() - timedelta(days=days_back + 10),
                ).distinct().all()
            ]
            for dt in sorted(dates_with_data):
                _compute_spreads(session, dt)
            session.commit()
        except Exception as e:
            logger.warning(f"Spread computation error: {e}")
            session.rollback()

        session.close()
        logger.info(f"Historical backfill complete: {counts}")
        return counts

    finally:
        if own_connection:
            ib_conn.disconnect()


def _upsert_spread(session, today, spread_type, front_month, back_month, value):
    existing = session.query(Spread).filter_by(
        date=today, spread_type=spread_type, front_month=front_month
    ).first()
    if existing:
        existing.spread_value = value
        existing.back_month = back_month
    else:
        session.add(Spread(
            date=today, spread_type=spread_type,
            front_month=front_month, back_month=back_month,
            spread_value=value,
        ))
