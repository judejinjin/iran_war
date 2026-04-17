"""
IB Historical Options Backfill — fetch daily bars for active FOP contracts,
compute IV and Greeks via Black-76 model.

Only currently listed (non-expired) options can be backfilled;
IB permanently deletes historical data for expired FOPs.
"""

import asyncio
import math
import time
from datetime import date, datetime, timedelta
from loguru import logger
from scipy.optimize import brentq
from scipy.stats import norm
from ib_insync import Future, FuturesOption, util

from config import FUTURES_SYMBOLS, FUTURES_EXCHANGE, OPTIONS_EXPIRIES_AHEAD
from collectors.ib_connection import IBConnection
from db.database import OptionsChain, VolSurface, FuturesCurve

# IB allows up to 50 simultaneous historical data requests.
# For bars >= 1 min, the hard 60/10min pacing limit is lifted.
# We fire CONCURRENT_REQUESTS at a time, with a short pause between waves.
CONCURRENT_REQUESTS = 45   # Just under IB's 50-simultaneous limit
WAVE_PAUSE_SECONDS = 2     # Brief pause between waves to avoid soft throttle

# Risk-free rate assumption for Black-76
RISK_FREE_RATE = 0.045

# Option-expiry-month → underlying-futures-month offset.
# CL (WTI): options expire mid-month M, settle into M+1 futures.
# COIL (Brent): options expire late month M, settle into M+2 futures.
FUTURES_MONTH_OFFSET = {"CL": 1, "COIL": 2}


# ─── Black-76 Model ─────────────────────────────────────────────────────────

def _black76_price(F, K, T, r, sigma, option_type):
    """Price a European option on a future using Black-76."""
    if T <= 0 or sigma <= 0:
        return 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    df = math.exp(-r * T)
    if option_type == "CALL":
        return df * (F * norm.cdf(d1) - K * norm.cdf(d2))
    else:
        return df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))


def _implied_vol(market_price, F, K, T, r, option_type):
    """Solve for implied volatility using Brent's method."""
    if market_price <= 0 or T <= 0 or F <= 0 or K <= 0:
        return None
    # Intrinsic value check
    intrinsic = max(0, F - K) if option_type == "CALL" else max(0, K - F)
    if market_price < intrinsic * math.exp(-r * T) * 0.99:
        return None
    try:
        iv = brentq(
            lambda sigma: _black76_price(F, K, T, r, sigma, option_type) - market_price,
            0.001, 5.0,
            xtol=1e-6,
            maxiter=100,
        )
        return iv
    except (ValueError, RuntimeError):
        return None


def _black76_greeks(F, K, T, r, sigma, option_type):
    """Compute delta, gamma, vega, theta from Black-76."""
    if T <= 0 or sigma <= 0:
        return None, None, None, None
    sqrt_T = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    df = math.exp(-r * T)
    pdf_d1 = norm.pdf(d1)

    gamma = df * pdf_d1 / (F * sigma * sqrt_T)
    vega = F * df * pdf_d1 * sqrt_T / 100  # per 1% vol move

    if option_type == "CALL":
        delta = df * norm.cdf(d1)
        theta = (
            -F * df * pdf_d1 * sigma / (2 * sqrt_T)
            - r * K * df * norm.cdf(d2)
            + r * F * df * norm.cdf(d1)
        ) / 365
    else:
        delta = df * (norm.cdf(d1) - 1)
        theta = (
            -F * df * pdf_d1 * sigma / (2 * sqrt_T)
            + r * K * df * norm.cdf(-d2)
            - r * F * df * norm.cdf(-d1)
        ) / 365

    return delta, gamma, vega, theta


# ─── Batch Upsert ────────────────────────────────────────────────────────────

def _batch_upsert_options(session, rows):
    """
    Batch upsert options_chains rows using INSERT ... ON CONFLICT ... DO UPDATE.
    Much faster than per-row SELECT+UPDATE because SQLite handles it in one statement.
    """
    from sqlalchemy import text
    if not rows:
        return
    sql = text("""
        INSERT INTO options_chains
            (date, underlying, expiry_date, strike, option_type,
             last_price, volume, implied_vol, delta, gamma, vega, theta,
             underlying_contract_month, created_at)
        VALUES
            (:date, :underlying, :expiry_date, :strike, :option_type,
             :last_price, :volume, :implied_vol, :delta, :gamma, :vega, :theta,
             :underlying_contract_month, CURRENT_TIMESTAMP)
        ON CONFLICT(date, underlying, expiry_date, strike, option_type) DO UPDATE SET
            last_price = excluded.last_price,
            volume = COALESCE(excluded.volume, options_chains.volume),
            implied_vol = excluded.implied_vol,
            delta = excluded.delta,
            gamma = excluded.gamma,
            vega = excluded.vega,
            theta = excluded.theta,
            underlying_contract_month = excluded.underlying_contract_month
    """)
    session.execute(sql, rows)


def _fill_symmetric_strikes(session, symbol):
    """
    Ensure every (date, expiry, strike) has BOTH a CALL and a PUT row.
    When IB returns MIDPOINT bars for only one side of a strike (e.g. the call
    has activity but the deep-OTM put doesn't), the chain is asymmetric.
    This inserts placeholder rows for the missing side so the UI chain view
    always shows balanced call/put columns.
    """
    from sqlalchemy import text
    sql = text("""
        INSERT OR IGNORE INTO options_chains
            (date, underlying, expiry_date, strike, option_type,
             last_price, underlying_contract_month, created_at)
        SELECT oc.date, oc.underlying, oc.expiry_date, oc.strike,
               CASE WHEN oc.option_type = 'CALL' THEN 'PUT' ELSE 'CALL' END,
               NULL,
               oc.underlying_contract_month,
               CURRENT_TIMESTAMP
        FROM options_chains oc
        WHERE oc.underlying = :symbol
        AND NOT EXISTS (
            SELECT 1 FROM options_chains oc2
            WHERE oc2.date = oc.date
            AND oc2.underlying = oc.underlying
            AND oc2.expiry_date = oc.expiry_date
            AND oc2.strike = oc.strike
            AND oc2.option_type != oc.option_type
        )
    """)
    result = session.execute(sql, {"symbol": symbol})
    count = result.rowcount
    session.commit()
    if count:
        logger.info(f"  {symbol}: filled {count} symmetric strike placeholders")
    return count


def _ensure_today_rows(session, symbol, contracts_by_expiry, today, expiry_to_fut_month):
    """
    Insert placeholder rows for ALL requested (expiry, strike, right) combos
    for today's date.  Historical MIDPOINT bars typically cover only ~20% of
    strikes on a single day; this ensures the UI chain view shows the full
    strike grid immediately and the market-snapshot step can fill bid/ask/OI.
    """
    from sqlalchemy import text
    sql = text("""
        INSERT OR IGNORE INTO options_chains
            (date, underlying, expiry_date, strike, option_type,
             underlying_contract_month, created_at)
        VALUES
            (:date, :underlying, :expiry_date, :strike, :option_type,
             :underlying_contract_month, CURRENT_TIMESTAMP)
    """)
    rows = []
    for expiry_str, expiry_date, contracts in contracts_by_expiry:
        if expiry_date <= today:
            continue
        ucm = expiry_to_fut_month.get(expiry_str) if expiry_to_fut_month else None
        if not ucm:
            ucm = _expiry_to_contract_month(expiry_date, symbol)
        for _, _, strike, right in contracts:
            option_type = "CALL" if right == "C" else "PUT"
            rows.append({
                "date": today,
                "underlying": symbol,
                "expiry_date": expiry_date,
                "strike": strike,
                "option_type": option_type,
                "underlying_contract_month": ucm,
            })
    if rows:
        session.execute(sql, rows)
        session.commit()
        logger.info(f"  {symbol}: ensured {len(rows)} strike rows exist for {today}")


# ─── Underlying Price Lookup ─────────────────────────────────────────────────

def _expiry_to_contract_month(expiry_date, symbol=None):
    """
    Map an option expiry date to its underlying futures contract month string 'YYYY-MM'.
    Uses FUTURES_MONTH_OFFSET when symbol is provided:
      CL  (WTI):   option exp month + 1 → futures month
      COIL (Brent): option exp month + 2 → futures month
    Falls back to same month if symbol is unknown.
    """
    offset = FUTURES_MONTH_OFFSET.get(symbol, 0) if symbol else 0
    m = expiry_date.month + offset
    y = expiry_date.year
    while m > 12:
        m -= 12
        y += 1
    return f"{y}-{m:02d}"


def _build_underlying_price_maps(session, symbol, ib=None, futures_months=None, days_back=365,
                                  expiry_to_fut_month=None):
    """
    Build per-contract-month underlying price maps for IV computation.
    Each option expiry maps to the futures contract of the same month.

    1) If IB connection + futures contracts provided, fetch daily bars from IB
       for each futures month (authoritative, full coverage).
       Also persists to futures_curves table so recompute_greeks can use DB data.
    2) Fall back to futures_curves table in DB.

    Returns dict {contract_month_str: {date: close_price}}
      e.g. {"2026-05": {date(2026,4,13): 92.76, ...}, "2026-06": {...}, ...}
    """
    price_maps = {}  # {contract_month: {date: price}}

    # Primary: fetch from IB for each futures month
    if ib and futures_months:
        stored = 0
        for fut in futures_months:
            cm = fut.lastTradeDateOrContractMonth[:4] + "-" + fut.lastTradeDateOrContractMonth[4:6]
            try:
                bars = ib.reqHistoricalData(
                    fut,
                    endDateTime="",
                    durationStr=f"{days_back} D",
                    barSizeSetting="1 day",
                    whatToShow="MIDPOINT",
                    useRTH=True,
                    formatDate=1,
                )
                # Preload existing dates for this contract month
                existing_dates = set(
                    r[0] for r in session.query(FuturesCurve.date).filter_by(
                        symbol=symbol, contract_month=cm
                    ).all()
                )
                pm = {}
                for bar in bars:
                    bar_date = bar.date if isinstance(bar.date, date) else bar.date.date()
                    pm[bar_date] = bar.close
                    # Persist to futures_curves so recompute_greeks works offline
                    if bar_date not in existing_dates:
                        session.add(FuturesCurve(
                            date=bar_date,
                            symbol=symbol,
                            contract_month=cm,
                            settlement_price=bar.close,
                            volume=bar.volume if hasattr(bar, 'volume') and bar.volume > 0 else None,
                        ))
                        stored += 1
                if pm:
                    price_maps[cm] = pm
            except Exception as e:
                logger.debug(f"  {symbol} {cm}: IB fetch failed ({e})")
        if price_maps:
            session.commit()
            logger.info(
                f"  {symbol}: loaded underlying prices from IB for "
                f"{len(price_maps)} contract months ({stored} rows persisted to DB)"
            )
            return price_maps

    # Fallback: futures_curves table (already has per-contract-month data)
    rows = (
        session.query(FuturesCurve.date, FuturesCurve.settlement_price, FuturesCurve.contract_month)
        .filter(FuturesCurve.symbol == symbol)
        .filter(FuturesCurve.settlement_price.isnot(None))
        .order_by(FuturesCurve.date, FuturesCurve.contract_month)
        .all()
    )
    for row in rows:
        if row.contract_month not in price_maps:
            price_maps[row.contract_month] = {}
        price_maps[row.contract_month][row.date] = row.settlement_price

    if price_maps:
        logger.info(
            f"  {symbol}: loaded underlying prices from DB for "
            f"{len(price_maps)} contract months"
        )
    return price_maps


def _get_underlying_price(price_maps, expiry_date, bar_date, expiry_to_fut_month=None, symbol=None):
    """
    Look up the underlying futures price for a given option expiry and date.
    Uses explicit expiry_to_fut_month mapping if provided (from reqSecDefOptParams);
    otherwise falls back to offset-based mapping then nearest available month.
    """
    # Try explicit mapping first (e.g. option exp "20260427" -> futures "2026-06")
    if expiry_to_fut_month:
        expiry_str = expiry_date.strftime("%Y%m%d")
        cm = expiry_to_fut_month.get(expiry_str)
        if cm:
            pm = price_maps.get(cm)
            if pm:
                price = pm.get(bar_date)
                if price:
                    return price

    # Offset-based mapping: CL +1 month, COIL +2 months
    cm = _expiry_to_contract_month(expiry_date, symbol)
    pm = price_maps.get(cm)
    if pm:
        price = pm.get(bar_date)
        if price:
            return price

    # Fallback: find any contract month that has data for this date
    for month_key in sorted(price_maps.keys()):
        pm = price_maps[month_key]
        if bar_date in pm:
            return pm[bar_date]
    return None


# ─── Vol Surface Computation ─────────────────────────────────────────────────

def _compute_vol_surface(session, bar_date, symbol, expiry_date, und_price, iv_data):
    """Compute ATM vol, 25-delta risk-reversal, and butterfly for one expiry/date."""
    calls = iv_data.get("calls", [])  # list of (strike, delta, iv)
    puts = iv_data.get("puts", [])

    if not calls and not puts:
        return

    all_ivs = calls + puts
    # ATM vol: closest strike to underlying
    atm = min(all_ivs, key=lambda x: abs(x[0] - und_price))
    atm_vol = atm[2]

    # 25-delta risk reversal & butterfly
    skew_25d = None
    smile_25d = None
    call_25d = [c for c in calls if c[1] and 0.20 <= abs(c[1]) <= 0.30]
    put_25d = [p for p in puts if p[1] and -0.30 <= p[1] <= -0.20]
    if call_25d and put_25d:
        c25 = min(call_25d, key=lambda x: abs(abs(x[1]) - 0.25))
        p25 = min(put_25d, key=lambda x: abs(abs(x[1]) - 0.25))
        skew_25d = c25[2] - p25[2]
        smile_25d = (c25[2] + p25[2]) / 2 - atm_vol

    existing = session.query(VolSurface).filter_by(
        date=bar_date, underlying=symbol, expiry_date=expiry_date,
    ).first()

    if existing:
        existing.atm_vol = atm_vol
        existing.skew_25d = skew_25d
        existing.smile_25d = smile_25d
    else:
        session.add(VolSurface(
            date=bar_date, underlying=symbol, expiry_date=expiry_date,
            atm_vol=atm_vol, skew_25d=skew_25d, smile_25d=smile_25d,
        ))


# ─── Recompute IV/Greeks for existing rows ───────────────────────────────────

def recompute_greeks(session) -> int:
    """
    Fill in IV/delta/gamma/vega/theta for options_chains rows where they're NULL
    but we have an underlying price + valid last_price.  Works offline (no IB).
    Uses per-expiry underlying futures prices (matching option expiry to futures month).
    Returns number of rows updated.
    """
    from config import FUTURES_SYMBOLS

    updated = 0
    for symbol in FUTURES_SYMBOLS:
        # Build per-contract-month underlying price maps from DB
        und_price_maps = _build_underlying_price_maps(session, symbol)
        if not und_price_maps:
            logger.warning(f"recompute_greeks: no underlying prices for {symbol}")
            continue

        # Build expiry_to_fut_month mapping from stored underlying_contract_month
        mapping_rows = (
            session.query(OptionsChain.expiry_date, OptionsChain.underlying_contract_month)
            .filter(
                OptionsChain.underlying == symbol,
                OptionsChain.underlying_contract_month.isnot(None),
            )
            .distinct()
            .all()
        )
        expiry_to_fut_month = {}
        for exp_date, ucm in mapping_rows:
            exp_str = exp_date.strftime("%Y%m%d")
            if exp_str not in expiry_to_fut_month:
                expiry_to_fut_month[exp_str] = ucm
        if expiry_to_fut_month:
            logger.info(f"recompute_greeks {symbol}: loaded {len(expiry_to_fut_month)} expiry→futures mappings from DB")

        # Get all rows with NULL IV but non-NULL last_price
        rows = (
            session.query(OptionsChain)
            .filter(
                OptionsChain.underlying == symbol,
                OptionsChain.implied_vol.is_(None),
                OptionsChain.last_price.isnot(None),
                OptionsChain.last_price > 0,
            )
            .all()
        )
        logger.info(f"recompute_greeks {symbol}: {len(rows)} rows with NULL IV")

        for row in rows:
            # Use stored contract month if available on this row, else mapping
            row_mapping = expiry_to_fut_month
            if row.underlying_contract_month:
                row_mapping = {row.expiry_date.strftime("%Y%m%d"): row.underlying_contract_month}
            F = _get_underlying_price(und_price_maps, row.expiry_date, row.date, row_mapping, symbol=symbol)
            if not F or F <= 0:
                continue
            T = (row.expiry_date - row.date).days / 365.0
            if T <= 0:
                continue

            iv = _implied_vol(row.last_price, F, row.strike, T, RISK_FREE_RATE, row.option_type)
            if iv and iv > 0:
                delta, gamma, vega, theta = _black76_greeks(
                    F, row.strike, T, RISK_FREE_RATE, iv, row.option_type
                )
                row.implied_vol = iv
                row.delta = delta
                row.gamma = gamma
                row.vega = vega
                row.theta = theta
                updated += 1

        session.commit()
        logger.info(f"recompute_greeks {symbol}: updated {updated} rows")

    return updated


# ─── Main Backfill ───────────────────────────────────────────────────────────

def run_backfill(start_from: date, session) -> int:
    """
    Fetch historical daily TRADES bars for active CL/COIL futures options,
    compute IV and Greeks via Black-76, store in options_chains + vol_surface.

    Returns total records upserted.
    """
    conn = IBConnection()
    total = 0

    try:
        ib = conn.connect()
        today = date.today()

        for symbol in FUTURES_SYMBOLS:
            exchange = FUTURES_EXCHANGE.get(symbol, "NYMEX")
            logger.info(f"IB options backfill: starting {symbol} on {exchange}")

            # ── 1. Get multiple underlying futures months ──
            # Each futures month has its own option chain; we need multiple
            # underlying months to collect 12+ option expiries.
            und_generic = Future(symbol=symbol, exchange=exchange, currency="USD")
            try:
                details = ib.reqContractDetails(und_generic)
                if not details:
                    logger.error(f"No contract details for {symbol}")
                    continue
                details.sort(key=lambda d: d.contract.lastTradeDateOrContractMonth)
                # Take first OPTIONS_EXPIRIES_AHEAD futures months
                futures_months = [d.contract for d in details[:OPTIONS_EXPIRIES_AHEAD]]
                logger.info(
                    f"  {symbol}: querying option chains for {len(futures_months)} "
                    f"futures months ({futures_months[0].localSymbol} → "
                    f"{futures_months[-1].localSymbol})"
                )
            except Exception as e:
                logger.error(f"Cannot get futures contracts for {symbol}: {e}")
                continue

            # ── 2. Collect option chain metadata across all futures months ──
            # Also build mapping: option_expiry_str -> underlying futures contract_month
            PREFERRED_CLASS = {"CL": "LO", "COIL": "COIL"}
            preferred = PREFERRED_CLASS.get(symbol)
            all_expirations = set()
            all_strikes_set = set()
            chain_meta = None  # For tradingClass, multiplier
            expiry_to_fut_month = {}  # "20260527" -> "2026-06" (option expiry -> underlying futures month)

            for und in futures_months:
                fut_cm = und.lastTradeDateOrContractMonth[:4] + "-" + und.lastTradeDateOrContractMonth[4:6]
                chains = ib.reqSecDefOptParams(
                    underlyingSymbol=und.symbol,
                    futFopExchange=exchange,
                    underlyingSecType=und.secType,
                    underlyingConId=und.conId,
                )
                if not chains:
                    continue

                exchange_chains = [c for c in chains if c.exchange == exchange]
                if not exchange_chains:
                    exchange_chains = chains
                if preferred:
                    std = [c for c in exchange_chains if c.tradingClass == preferred]
                    if std:
                        exchange_chains = std
                chain = max(exchange_chains, key=lambda c: len(c.expirations))

                # Map each option expiry to this underlying futures month
                for exp in chain.expirations:
                    if exp not in expiry_to_fut_month:
                        expiry_to_fut_month[exp] = fut_cm

                all_expirations.update(chain.expirations)
                all_strikes_set.update(chain.strikes)
                if chain_meta is None:
                    chain_meta = chain

            if not chain_meta or not all_expirations:
                logger.warning(f"No option chains found for {symbol}")
                continue

            expirations = sorted(all_expirations)[:OPTIONS_EXPIRIES_AHEAD]
            all_strikes = sorted(all_strikes_set)

            logger.info(
                f"  {symbol}: {len(expirations)} expiries, "
                f"{len(all_strikes)} total strikes, "
                f"tradingClass={chain_meta.tradingClass}, multiplier={chain_meta.multiplier}"
            )
            for exp in expirations:
                logger.debug(f"    option exp {exp} -> futures month {expiry_to_fut_month.get(exp, '???')}")

            # ── 3. Get underlying price maps for IV computation ──
            # Each option expiry maps to. specific underlying futures month
            # (e.g. COIL option exp 2026-04-27 -> Jun 2026 futures)
            days_back = min(max((today - start_from).days, 1), 365)
            und_price_maps = _build_underlying_price_maps(
                session, symbol, ib=ib, futures_months=futures_months, days_back=days_back
            )
            if not und_price_maps:
                logger.warning(f"No underlying price history for {symbol} — cannot compute IV")
                # Still fetch bars but skip IV

            # Current front-month price for strike filtering
            front_cm = futures_months[0].lastTradeDateOrContractMonth[:4] + "-" + futures_months[0].lastTradeDateOrContractMonth[4:6]
            front_pm = und_price_maps.get(front_cm, {})
            latest_und_price = front_pm.get(max(front_pm)) if front_pm else None

            # Try getting live price if no history
            if latest_und_price is None:
                try:
                    ticker = ib.reqMktData(futures_months[0], snapshot=True)
                    ib.sleep(2)
                    latest_und_price = ticker.last or ticker.close or 0
                    ib.cancelMktData(futures_months[0])
                except Exception:
                    latest_und_price = 0

            if not latest_und_price or latest_und_price <= 0:
                logger.warning(f"Cannot determine underlying price for {symbol}, skipping")
                continue

            # ── 4. Filter strikes: divisible by 10, within -50% to +200% of underlying ──
            low_strike = latest_und_price * 0.50
            high_strike = latest_und_price * 3.00
            relevant_strikes = [
                s for s in all_strikes
                if low_strike <= s <= high_strike and s % 10 == 0
            ]

            logger.info(
                f"  {symbol}: underlying ~{latest_und_price:.2f}, "
                f"{len(relevant_strikes)} strikes (divisible by 10) in range "
                f"[{low_strike:.1f}, {high_strike:.1f}]"
            )

            # ── 5. Build list of contracts grouped by expiry ──
            contracts_by_expiry = []
            for expiry in expirations:
                expiry_date = datetime.strptime(expiry, "%Y%m%d").date()
                if expiry_date <= today:
                    continue  # Skip expired
                expiry_contracts = []
                for strike in relevant_strikes:
                    for right in ["C", "P"]:
                        expiry_contracts.append((expiry, expiry_date, strike, right))
                contracts_by_expiry.append((expiry, expiry_date, expiry_contracts))

            total_contracts = sum(len(ec) for _, _, ec in contracts_by_expiry)
            logger.info(
                f"  {symbol}: {total_contracts} option contracts across "
                f"{len(contracts_by_expiry)} expiries"
            )

            # ── 6. Fetch bars concurrently ──
            request_count = 0
            symbol_total = 0
            symbol_failed = False

            all_contracts = []
            for _, _, ec in contracts_by_expiry:
                all_contracts.extend(ec)

            # Precompute duration once
            days_back = min(max((today - start_from).days, 1), 365)
            duration_str = f"{days_back} D"

            # Process in waves of CONCURRENT_REQUESTS
            for wave_start in range(0, len(all_contracts), CONCURRENT_REQUESTS):
                if symbol_failed:
                    break
                wave = all_contracts[wave_start:wave_start + CONCURRENT_REQUESTS]

                # Build all FuturesOption contracts for this wave
                opts_info = []  # (opt_contract, expiry_str, expiry_date, strike, right)
                for expiry_str, expiry_date, strike, right in wave:
                    opt = FuturesOption(
                        symbol=symbol,
                        lastTradeDateOrContractMonth=expiry_str,
                        strike=strike,
                        right=right,
                        exchange=chain_meta.exchange,
                        multiplier=chain_meta.multiplier,
                        tradingClass=chain_meta.tradingClass,
                        currency="USD",
                    )
                    opts_info.append((opt, expiry_str, expiry_date, strike, right))

                # Fire all reqHistoricalData in parallel (skip qualifyContracts)
                pending = []
                loop = util.getLoop()  # ib_insync's loop (safe on Python 3.12+)
                for opt, expiry_str, expiry_date, strike, right in opts_info:
                    try:
                        coro = ib.reqHistoricalDataAsync(
                            opt,
                            endDateTime="",
                            durationStr=duration_str,
                            barSizeSetting="1 hour",
                            whatToShow="MIDPOINT",
                            useRTH=True,
                            formatDate=1,
                        )
                        task = loop.create_task(coro)
                        pending.append((task, expiry_str, expiry_date, strike, right))
                    except Exception:
                        continue

                # Wait for all tasks to complete via ib_insync event loop
                while pending and not all(t.done() for t, *_ in pending):
                    ib.sleep(0.1)

                # Process results
                for task, expiry_str, expiry_date, strike, right in pending:
                    try:
                        bars = task.result()
                    except Exception as e:
                        err_msg = str(e)
                        if "No data of type" in err_msg:
                            logger.warning(
                                f"Bar type unsupported for {symbol} FOPs on {exchange}, "
                                f"skipping all {symbol} options"
                            )
                            symbol_failed = True
                            break
                        continue
                    request_count += 1

                    if not bars:
                        continue

                    option_type = "CALL" if right == "C" else "PUT"

                    # Aggregate hourly bars to daily
                    daily = {}
                    for bar in bars:
                        bar_dt = bar.date if isinstance(bar.date, datetime) else datetime.combine(bar.date, datetime.min.time())
                        bar_date = bar_dt.date()
                        if bar_date not in daily:
                            daily[bar_date] = {"close": bar.close, "volume": 0}
                        else:
                            daily[bar_date]["close"] = bar.close
                        daily[bar_date]["volume"] += (bar.volume if bar.volume > 0 else 0)

                    # Bulk upsert: collect rows, then batch insert with ON CONFLICT
                    upsert_rows = []
                    for bar_date, agg in daily.items():
                        F = _get_underlying_price(und_price_maps, expiry_date, bar_date, expiry_to_fut_month, symbol=symbol)
                        T = (expiry_date - bar_date).days / 365.0

                        iv = delta = gamma = vega = theta = None
                        if F and F > 0 and T > 0 and agg["close"] > 0:
                            iv = _implied_vol(
                                agg["close"], F, strike, T, RISK_FREE_RATE, option_type
                            )
                            if iv and iv > 0:
                                delta, gamma, vega, theta = _black76_greeks(
                                    F, strike, T, RISK_FREE_RATE, iv, option_type
                                )

                        # Resolve the underlying futures contract month for this option expiry
                        ucm = expiry_to_fut_month.get(expiry_str) if expiry_to_fut_month else None
                        if not ucm:
                            ucm = _expiry_to_contract_month(expiry_date, symbol)

                        upsert_rows.append({
                            "date": bar_date,
                            "underlying": symbol,
                            "expiry_date": expiry_date,
                            "strike": strike,
                            "option_type": option_type,
                            "last_price": agg["close"],
                            "volume": agg["volume"] or None,
                            "implied_vol": iv,
                            "delta": delta,
                            "gamma": gamma,
                            "vega": vega,
                            "theta": theta,
                            "underlying_contract_month": ucm,
                        })

                    if upsert_rows:
                        _batch_upsert_options(session, upsert_rows)
                        symbol_total += len(upsert_rows)

                session.commit()

                # Brief pause between waves
                if wave_start + CONCURRENT_REQUESTS < len(all_contracts):
                    logger.info(
                        f"  {symbol}: wave {wave_start // CONCURRENT_REQUESTS + 1} done, "
                        f"{request_count} requests so far..."
                    )
                    time.sleep(WAVE_PAUSE_SECONDS)

            # ── 7. Compute vol surfaces from collected data ──
            logger.info(f"  {symbol}: computing vol surfaces...")
            _compute_all_vol_surfaces(session, symbol, expirations, und_price_maps, expiry_to_fut_month)
            session.commit()

            # ── 7b. Fill symmetric strikes (ensure every strike has both C and P) ──
            _fill_symmetric_strikes(session, symbol)

            # ── 7c. Ensure today has rows for ALL requested strikes ──
            # Historical MIDPOINT bars only return data for strikes with active
            # quoting — typically ~20% of strikes on a single day.  Insert
            # placeholder rows for all remaining strikes so the UI chain view
            # always shows the complete grid and the market-snapshot step below
            # can UPDATE those rows with live bid/ask/OI.
            _ensure_today_rows(session, symbol, contracts_by_expiry, today, expiry_to_fut_month)

            # ── 8. Fetch live market snapshots (bid/ask/OI/volume) for all expiries ──
            _fetch_market_snapshots(
                ib, session, symbol, contracts_by_expiry,
                chain_meta, today,
            )
            session.commit()

            total += symbol_total
            logger.info(
                f"IB options backfill {symbol}: {symbol_total} records, "
                f"{request_count} API requests"
            )

        logger.info(f"IB options backfill complete: {total} total records")
        return total

    finally:
        conn.disconnect()


def _fetch_market_snapshots(ib, session, symbol, expiry_groups, chain_meta, today):
    """
    Fetch live market data (bid, ask, volume, open interest) via reqMktData
    streaming for all expiry groups.  Updates TODAY's options_chains rows
    with live data.  This fills the bid/ask/volume/OI columns that
    MIDPOINT historical bars cannot provide.
    """
    if not expiry_groups:
        return

    updated = 0
    for expiry_str, expiry_date, contracts in expiry_groups:
        if expiry_date <= today:
            continue

        logger.info(
            f"  {symbol} exp {expiry_str}: fetching live snapshots for "
            f"{len(contracts)} contracts (data_date={today})"
        )

        # Build FuturesOption contracts for this expiry
        opts = []
        for _, _, strike, right in contracts:
            opt = FuturesOption(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiry_str,
                strike=strike,
                right=right,
                exchange=chain_meta.exchange,
                multiplier=chain_meta.multiplier,
                tradingClass=chain_meta.tradingClass,
                currency="USD",
            )
            opts.append((opt, strike, right))

        # Process in waves — streaming mode to get OI + bid/ask ticks
        expiry_updated = 0
        for wave_start in range(0, len(opts), CONCURRENT_REQUESTS):
            wave = opts[wave_start:wave_start + CONCURRENT_REQUESTS]

            tickers = []
            for opt, strike, right in wave:
                try:
                    # genericTickList="100,101,106" — 100=OptionVolume, 101=OptionOI, 106=OI
                    ticker = ib.reqMktData(opt, genericTickList="100,101,106",
                                           snapshot=False, regulatorySnapshot=False)
                    tickers.append((ticker, strike, right))
                except Exception:
                    continue

            # Wait for ticks to arrive
            ib.sleep(5)

            # Debug: log first ticker per expiry
            if tickers and wave_start == 0:
                t = tickers[0][0]
                logger.debug(
                    f"  {symbol} snapshot debug: strike={tickers[0][1]} right={tickers[0][2]} "
                    f"bid={t.bid} ask={t.ask} last={t.last} vol={t.volume} "
                    f"callOI={t.callOpenInterest} putOI={t.putOpenInterest}"
                )

            for ticker, strike, right in tickers:
                ib.cancelMktData(ticker.contract)
                option_type = "CALL" if right == "C" else "PUT"

                bid = _extract_price(ticker, 'bid')
                ask = _extract_price(ticker, 'ask')
                last = _extract_price(ticker, 'last')
                oi = _extract_oi(ticker)
                vol = _extract_volume(ticker)

                if any(v is not None for v in (bid, ask, last, oi, vol)):
                    _upsert_market_snapshot(
                        session, today, symbol, expiry_date,
                        strike, option_type, bid, ask, oi, vol, last,
                    )
                    expiry_updated += 1

            if wave_start + CONCURRENT_REQUESTS < len(opts):
                time.sleep(WAVE_PAUSE_SECONDS)

        updated += expiry_updated
        logger.info(
            f"  {symbol} exp {expiry_str}: {expiry_updated} rows updated with bid/ask/OI/volume"
        )

    if updated:
        session.commit()
        logger.info(f"  {symbol}: total live snapshot updates: {updated}")
    else:
        logger.warning(f"  {symbol}: no live market data returned from IB")


def _upsert_market_snapshot(session, data_date, symbol, expiry_date, strike,
                            option_type, bid, ask, oi, vol, last=None):
    """Upsert bid/ask/OI/volume/last on today's options_chains row.
    Uses INSERT ON CONFLICT so rows are created even if no historical bar existed."""
    from sqlalchemy import text
    sql = text("""
        INSERT INTO options_chains
            (date, underlying, expiry_date, strike, option_type,
             bid, ask, open_interest, volume, last_price, created_at)
        VALUES
            (:date, :underlying, :expiry_date, :strike, :option_type,
             :bid, :ask, :oi, :vol, :last, CURRENT_TIMESTAMP)
        ON CONFLICT(date, underlying, expiry_date, strike, option_type) DO UPDATE SET
            bid = COALESCE(:bid, options_chains.bid),
            ask = COALESCE(:ask, options_chains.ask),
            open_interest = COALESCE(:oi, options_chains.open_interest),
            volume = COALESCE(:vol, options_chains.volume),
            last_price = COALESCE(:last, options_chains.last_price)
    """)
    session.execute(sql, {
        "date": data_date, "underlying": symbol,
        "expiry_date": expiry_date, "strike": strike,
        "option_type": option_type,
        "bid": bid, "ask": ask, "oi": oi, "vol": vol, "last": last,
    })


def _extract_price(ticker, field):
    """Extract a price field (bid/ask/last) from an IB Ticker, handling NaN/<=0."""
    val = getattr(ticker, field, None)
    if val is not None and not (isinstance(val, float) and math.isnan(val)) and val > 0:
        return float(val)
    return None


def _extract_oi(ticker):
    """Extract open interest from an IB Ticker, handling NaN values."""
    # Try various OI field names that IB uses
    for attr in ('callOpenInterest', 'putOpenInterest', 'futuresOpenInterest'):
        val = getattr(ticker, attr, None)
        if val is not None and not (isinstance(val, float) and math.isnan(val)) and val > 0:
            return int(val)
    # Check lastGreeks which sometimes carries OI
    greeks = getattr(ticker, 'lastGreeks', None)
    if greeks:
        oi = getattr(greeks, 'openInterest', None)
        if oi and not (isinstance(oi, float) and math.isnan(oi)) and oi > 0:
            return int(oi)
    return None


def _extract_volume(ticker):
    """Extract volume from an IB Ticker, handling NaN values."""
    val = getattr(ticker, 'volume', None)
    if val is not None and not (isinstance(val, float) and math.isnan(val)) and val > 0:
        return int(val)
    return None


def _compute_all_vol_surfaces(session, symbol, expirations, und_price_maps, expiry_to_fut_month=None):
    """
    After all bars are stored, compute vol_surface entries
    for each (date, expiry) combination from the options_chains data.
    """
    for expiry_str in expirations:
        expiry_date = datetime.strptime(expiry_str, "%Y%m%d").date()

        # Get all options for this symbol + expiry that have IV
        options = (
            session.query(OptionsChain)
            .filter(
                OptionsChain.underlying == symbol,
                OptionsChain.expiry_date == expiry_date,
                OptionsChain.implied_vol.isnot(None),
            )
            .all()
        )
        if not options:
            continue

        # Group by date
        by_date = {}
        for opt in options:
            by_date.setdefault(opt.date, []).append(opt)

        for bar_date, opts in by_date.items():
            und_price = _get_underlying_price(und_price_maps, expiry_date, bar_date, expiry_to_fut_month, symbol=symbol)
            if not und_price:
                continue

            iv_data = {"calls": [], "puts": []}
            for opt in opts:
                entry = (opt.strike, opt.delta, opt.implied_vol)
                if opt.option_type == "CALL":
                    iv_data["calls"].append(entry)
                else:
                    iv_data["puts"].append(entry)

            _compute_vol_surface(session, bar_date, symbol, expiry_date, und_price, iv_data)
