"""
IB Options Data Collector — fetches options chains for CL + BZ, computes Greeks.
"""

import math
from datetime import date, datetime
from loguru import logger
from ib_insync import Future, Option, util

from config import FUTURES_SYMBOLS, FUTURES_EXCHANGE, OPTIONS_EXPIRIES_AHEAD
from collectors.ib_connection import IBConnection
from db.database import get_session, OptionsChain, VolSurface


def collect_options_snapshot(ib_conn: IBConnection = None) -> dict:
    """
    Fetch options chains for CL and BZ (front N expiries), compute Greeks,
    store in options_chains and vol_surface tables.
    """
    own_connection = ib_conn is None
    if own_connection:
        ib_conn = IBConnection()

    try:
        ib = ib_conn.ensure_connected()
        session = get_session()
        today = date.today()
        counts = {}

        for symbol in FUTURES_SYMBOLS:
            exchange = FUTURES_EXCHANGE.get(symbol, "NYMEX")
            try:
                # Get the underlying future
                und_contract = Future(symbol=symbol, exchange=exchange)
                ib.qualifyContracts(und_contract)

                # Request option chains metadata
                chains = ib.reqSecDefOptParams(
                    und_contract.symbol, "", und_contract.secType, und_contract.conId
                )
                if not chains:
                    logger.warning(f"No option chains found for {symbol}")
                    counts[symbol] = 0
                    continue

                # Pick the chain with the most expirations (main exchange)
                chain = max(chains, key=lambda c: len(c.expirations))
                expirations = sorted(chain.expirations)[:OPTIONS_EXPIRIES_AHEAD]
                strikes = sorted(chain.strikes)

                # Get current underlying price for ATM reference
                ticker = ib.reqMktData(und_contract, snapshot=True)
                ib.sleep(2)
                und_price = ticker.last or ticker.close or 0
                ib.cancelMktData(und_contract)

                if und_price <= 0:
                    logger.warning(f"Could not get underlying price for {symbol}")
                    counts[symbol] = 0
                    continue

                # Filter strikes to reasonable range (±30% of underlying)
                low_strike = und_price * 0.7
                high_strike = und_price * 1.3
                relevant_strikes = [s for s in strikes if low_strike <= s <= high_strike]

                symbol_count = 0
                for expiry in expirations:
                    expiry_date = datetime.strptime(expiry, "%Y%m%d").date()
                    vol_data = {"calls_iv": [], "puts_iv": []}

                    for strike in relevant_strikes:
                        for right in ["C", "P"]:
                            try:
                                opt = Option(
                                    symbol=symbol, exchange=chain.exchange,
                                    lastTradeDateOrContractMonth=expiry,
                                    strike=strike, right=right,
                                )
                                ib.qualifyContracts(opt)

                                tk = ib.reqMktData(opt, snapshot=True)
                                ib.sleep(1)

                                option_type = "CALL" if right == "C" else "PUT"

                                # Extract data
                                iv = tk.modelGreeks.impliedVol if tk.modelGreeks else None
                                delta = tk.modelGreeks.delta if tk.modelGreeks else None
                                gamma = tk.modelGreeks.gamma if tk.modelGreeks else None
                                vega = tk.modelGreeks.vega if tk.modelGreeks else None
                                theta = tk.modelGreeks.theta if tk.modelGreeks else None

                                # Track IV for vol surface
                                if iv and iv > 0:
                                    if right == "C":
                                        vol_data["calls_iv"].append((strike, delta or 0, iv))
                                    else:
                                        vol_data["puts_iv"].append((strike, delta or 0, iv))

                                # Upsert into DB
                                existing = session.query(OptionsChain).filter_by(
                                    date=today, underlying=symbol,
                                    expiry_date=expiry_date, strike=strike,
                                    option_type=option_type,
                                ).first()

                                if existing:
                                    existing.bid = tk.bid if tk.bid != -1 else None
                                    existing.ask = tk.ask if tk.ask != -1 else None
                                    existing.last_price = tk.last if tk.last != -1 else None
                                    existing.implied_vol = iv
                                    existing.delta = delta
                                    existing.gamma = gamma
                                    existing.vega = vega
                                    existing.theta = theta
                                    existing.volume = tk.volume if tk.volume != -1 else None
                                else:
                                    session.add(OptionsChain(
                                        date=today, underlying=symbol,
                                        expiry_date=expiry_date, strike=strike,
                                        option_type=option_type,
                                        bid=tk.bid if tk.bid != -1 else None,
                                        ask=tk.ask if tk.ask != -1 else None,
                                        last_price=tk.last if tk.last != -1 else None,
                                        implied_vol=iv, delta=delta,
                                        gamma=gamma, vega=vega, theta=theta,
                                        volume=tk.volume if tk.volume != -1 else None,
                                        open_interest=None,
                                    ))

                                ib.cancelMktData(opt)
                                symbol_count += 1

                            except Exception as e:
                                logger.debug(f"Skip {symbol} {expiry} {strike}{right}: {e}")
                                continue

                    # Compute and store vol surface for this expiry
                    _compute_vol_surface(session, today, symbol, expiry_date, und_price, vol_data)

                counts[symbol] = symbol_count
                logger.info(f"Collected {symbol_count} option entries for {symbol}")

            except Exception as e:
                logger.error(f"Failed to collect options for {symbol}: {e}")
                counts[symbol] = 0

        session.commit()
        session.close()
        logger.info(f"Options snapshot complete: {counts}")
        return counts

    finally:
        if own_connection:
            ib_conn.disconnect()


def _compute_vol_surface(session, today, symbol, expiry_date, und_price, vol_data):
    """Compute ATM vol, 25-delta skew, and butterfly for a single expiry."""
    calls = vol_data.get("calls_iv", [])
    puts = vol_data.get("puts_iv", [])

    if not calls and not puts:
        return

    # ATM vol: closest strike to underlying price
    all_ivs = calls + puts
    if all_ivs:
        atm = min(all_ivs, key=lambda x: abs(x[0] - und_price))
        atm_vol = atm[2]
    else:
        return

    # 25-delta risk reversal (25d call IV - 25d put IV)
    skew_25d = None
    call_25d = [c for c in calls if c[1] and 0.20 <= abs(c[1]) <= 0.30]
    put_25d = [p for p in puts if p[1] and -0.30 <= p[1] <= -0.20]
    if call_25d and put_25d:
        c25 = min(call_25d, key=lambda x: abs(abs(x[1]) - 0.25))
        p25 = min(put_25d, key=lambda x: abs(abs(x[1]) - 0.25))
        skew_25d = c25[2] - p25[2]

    # 25-delta butterfly (avg of 25d wings - ATM)
    smile_25d = None
    if call_25d and put_25d:
        c25_iv = min(call_25d, key=lambda x: abs(abs(x[1]) - 0.25))[2]
        p25_iv = min(put_25d, key=lambda x: abs(abs(x[1]) - 0.25))[2]
        smile_25d = (c25_iv + p25_iv) / 2 - atm_vol

    existing = session.query(VolSurface).filter_by(
        date=today, underlying=symbol, expiry_date=expiry_date,
    ).first()

    if existing:
        existing.atm_vol = atm_vol
        existing.skew_25d = skew_25d
        existing.smile_25d = smile_25d
    else:
        session.add(VolSurface(
            date=today, underlying=symbol, expiry_date=expiry_date,
            atm_vol=atm_vol, skew_25d=skew_25d, smile_25d=smile_25d,
        ))
