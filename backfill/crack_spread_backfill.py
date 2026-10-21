"""
Crack Spread Backfill — fetches ULSD and RBOB spot prices from FRED,
converts $/gal → $/bbl (×42), then computes and upserts:

  DIESEL_CRACK_WTI   = ULSD_bbl − WTI_bbl
  DIESEL_CRACK_BRENT = ULSD_bbl − Brent_bbl
  CRACK_321_WTI      = (2×RBOB_bbl + 1×ULSD_bbl − 3×WTI_bbl) / 3

Raw product prices go into crack_spread_prices; derived spreads reuse the
existing Spread table with front_month holding the product symbol ("ULSD").

First-run history override: ULSD goes back to 1986-01-02, giving 40 years of
seasonal context. When no prior rows exist the effective start is forced to
1986-01-02, mirroring the FRED_DUBAI_SERIES pattern in fred_backfill.py.
"""

from datetime import date
from loguru import logger
from fredapi import Fred

from config import FRED_API_KEY, FRED_ULSD_SERIES, FRED_RBOB_SERIES
from db.database import CrackSpreadPrice, FuturesCurve, Spread
from sqlalchemy import func as sa_func

_ULSD_HISTORY_START = date(1986, 1, 2)
_RBOB_HISTORY_START = date(1994, 1, 1)   # WRBWHOLESALE available from mid-1990s


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _upsert_product(session, dt: date, symbol: str, price_per_gal: float):
    row = (
        session.query(CrackSpreadPrice)
        .filter_by(date=dt, symbol=symbol, source="FRED")
        .first()
    )
    price_per_bbl = round(price_per_gal * 42.0, 4)
    if row:
        row.price_per_gal = price_per_gal
        row.price_per_bbl = price_per_bbl
    else:
        session.add(CrackSpreadPrice(
            date=dt,
            symbol=symbol,
            source="FRED",
            price_per_gal=price_per_gal,
            price_per_bbl=price_per_bbl,
        ))


def _upsert_spread(session, dt: date, spread_type: str, front_month: str,
                   back_month: str, value: float):
    row = (
        session.query(Spread)
        .filter_by(date=dt, spread_type=spread_type, front_month=front_month)
        .first()
    )
    if row:
        row.spread_value = value
        row.back_month = back_month
    else:
        session.add(Spread(
            date=dt,
            spread_type=spread_type,
            front_month=front_month,
            back_month=back_month,
            spread_value=value,
        ))


def _front_month_map(session, symbol: str) -> dict:
    """Return {date: price} for the front-month contract of *symbol*."""
    subq = (
        session.query(
            FuturesCurve.date,
            sa_func.min(FuturesCurve.contract_month).label("front"),
        )
        .filter(FuturesCurve.symbol == symbol)
        .group_by(FuturesCurve.date)
        .subquery()
    )
    rows = (
        session.query(FuturesCurve)
        .join(
            subq,
            (FuturesCurve.date == subq.c.date)
            & (FuturesCurve.contract_month == subq.c.front)
            & (FuturesCurve.symbol == symbol),
        )
        .all()
    )
    return {r.date: r.settlement_price for r in rows if r.settlement_price}


# ─── Main entry point ────────────────────────────────────────────────────────

def run_backfill(start_from: date, session) -> int:
    """
    Fetch ULSD + RBOB from FRED, upsert raw prices and computed crack spreads.
    Returns number of crack_spread_prices rows inserted or updated.
    """
    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set — skipping crack spread backfill")
        return 0

    fred = Fred(api_key=FRED_API_KEY)

    # Force full history on first run (no prior rows) for good seasonal depth
    existing_count = session.query(CrackSpreadPrice).count()
    if existing_count == 0:
        ulsd_start = _ULSD_HISTORY_START
        rbob_start = _RBOB_HISTORY_START
        logger.info("Crack spread: first run — fetching full history from 1986")
    else:
        ulsd_start = start_from
        rbob_start = start_from

    today = date.today()
    total_product_rows = 0

    # ── Fetch ULSD (daily) ───────────────────────────────────────────────────
    logger.info(f"Crack spread: fetching ULSD ({FRED_ULSD_SERIES}) from {ulsd_start}")
    try:
        ulsd_data = fred.get_series(
            FRED_ULSD_SERIES,
            observation_start=ulsd_start,
            observation_end=today,
        )
        for dt_idx, price in ulsd_data.items():
            if price != price or price is None:  # NaN guard
                continue
            obs_date = dt_idx.date() if hasattr(dt_idx, "date") else dt_idx
            _upsert_product(session, obs_date, "ULSD", float(price))
            total_product_rows += 1
        session.commit()
        logger.info(f"Crack spread: {total_product_rows} ULSD rows upserted")
    except Exception as exc:
        logger.error(f"Crack spread: ULSD fetch failed: {exc}")
        session.rollback()

    # ── Fetch RBOB (weekly wholesale) ────────────────────────────────────────
    logger.info(f"Crack spread: fetching RBOB ({FRED_RBOB_SERIES}) from {rbob_start}")
    rbob_rows = 0
    try:
        rbob_data = fred.get_series(
            FRED_RBOB_SERIES,
            observation_start=rbob_start,
            observation_end=today,
        )
        for dt_idx, price in rbob_data.items():
            if price != price or price is None:
                continue
            obs_date = dt_idx.date() if hasattr(dt_idx, "date") else dt_idx
            _upsert_product(session, obs_date, "RBOB", float(price))
            rbob_rows += 1
        session.commit()
        logger.info(f"Crack spread: {rbob_rows} RBOB rows upserted")
    except Exception as exc:
        logger.warning(f"Crack spread: RBOB fetch failed ({exc}); 3-2-1 spread will be skipped")

    # ── Build lookup maps from futures curves (already in DB) ────────────────
    wti_map = _front_month_map(session, "CL")
    brent_map = _front_month_map(session, "COIL")

    # ── Query all ULSD bbl prices ─────────────────────────────────────────────
    ulsd_rows = (
        session.query(CrackSpreadPrice)
        .filter(CrackSpreadPrice.symbol == "ULSD")
        .order_by(CrackSpreadPrice.date)
        .all()
    )
    ulsd_bbl_map = {r.date: r.price_per_bbl for r in ulsd_rows if r.price_per_bbl}

    # ── Query all RBOB bbl prices ─────────────────────────────────────────────
    rbob_rows_db = (
        session.query(CrackSpreadPrice)
        .filter(CrackSpreadPrice.symbol == "RBOB")
        .order_by(CrackSpreadPrice.date)
        .all()
    )
    rbob_bbl_map = {r.date: r.price_per_bbl for r in rbob_rows_db if r.price_per_bbl}

    # ── Compute and upsert spreads ────────────────────────────────────────────
    spread_count = 0

    # DIESEL_CRACK_WTI and DIESEL_CRACK_BRENT (daily, from ULSD × WTI/Brent)
    for dt, ulsd_bbl in ulsd_bbl_map.items():
        if dt in wti_map:
            _upsert_spread(
                session, dt,
                "DIESEL_CRACK_WTI", "ULSD", "CL",
                round(ulsd_bbl - wti_map[dt], 4),
            )
            spread_count += 1
        if dt in brent_map:
            _upsert_spread(
                session, dt,
                "DIESEL_CRACK_BRENT", "ULSD", "COIL",
                round(ulsd_bbl - brent_map[dt], 4),
            )
            spread_count += 1

    # CRACK_321_WTI (weekly, needs RBOB + ULSD on same date → forward-fill ULSD to RBOB dates)
    for dt, rbob_bbl in rbob_bbl_map.items():
        # Use same-day ULSD or nearest prior day within 7 days
        ulsd_bbl = ulsd_bbl_map.get(dt)
        if ulsd_bbl is None:
            # Forward-fill: find nearest prior ULSD date
            prior = [d for d in ulsd_bbl_map if d <= dt]
            if prior and (dt - max(prior)).days <= 7:
                ulsd_bbl = ulsd_bbl_map[max(prior)]
        if ulsd_bbl is None:
            continue

        wti_bbl = wti_map.get(dt)
        if wti_bbl is None:
            prior_wti = [d for d in wti_map if d <= dt]
            if prior_wti and (dt - max(prior_wti)).days <= 7:
                wti_bbl = wti_map[max(prior_wti)]
        if wti_bbl is None:
            continue

        crack_321 = round((2 * rbob_bbl + 1 * ulsd_bbl - 3 * wti_bbl) / 3.0, 4)
        _upsert_spread(session, dt, "CRACK_321_WTI", "ULSD", "CL", crack_321)
        spread_count += 1

    session.commit()
    logger.info(
        f"Crack spread backfill complete: {total_product_rows} product rows, "
        f"{spread_count} spread rows"
    )
    return total_product_rows
