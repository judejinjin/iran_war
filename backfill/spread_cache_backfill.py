"""
Spread Cache Backfill — pre-compute calendar spread series into the Spread table.

Reads all FuturesCurve rows for the requested date range, groups them by
(date, symbol), sorts by contract_month, and computes M1-M2, M1-M6, M1-M12 spreads.

The Spread table serves as a fast pre-computed cache so the UI callback no longer
needs to query hundreds of FuturesCurve rows per request for every chart render.

Spread types stored:
  CL_M1M2, CL_M1M6, CL_M1M12
  COIL_M1M2, COIL_M1M6, COIL_M1M12

The existing Spread UniqueConstraint is (date, spread_type, front_month), so
upserts are safe and idempotent.
"""

from collections import defaultdict
from datetime import date
from loguru import logger

from db.database import FuturesCurve, Spread


# (label_suffix, 0-based offset into sorted contract list)
_SPREAD_CONFIGS = [
    ("M1M2",  1),
    ("M1M6",  5),
    ("M1M12", 11),
]


def run_backfill(start_from: date, session) -> int:
    """
    Compute and cache calendar spread values from all FuturesCurve data
    into the Spread table.

    Only recomputes rows from start_from onwards (typically today-60 days for
    daily scheduler refreshes, or war_start for the initial full backfill).

    Returns the number of Spread rows inserted or updated.
    """
    # Load all relevant FuturesCurve rows (minimise per-row queries)
    rows = (
        session.query(FuturesCurve)
        .filter(FuturesCurve.date >= start_from)
        .order_by(FuturesCurve.date, FuturesCurve.symbol, FuturesCurve.contract_month)
        .all()
    )

    if not rows:
        logger.info("Spread cache backfill: no FuturesCurve rows found, nothing to compute.")
        return 0

    # Group by (date, symbol) → list of curve rows sorted by contract_month
    grouped: dict[tuple, list] = defaultdict(list)
    for r in rows:
        grouped[(r.date, r.symbol)].append(r)

    upserted = 0
    BATCH_SIZE = 500

    for (dt, sym), contracts in grouped.items():
        # Already ordered by contract_month (from the ORDER BY above)
        prices = [c for c in contracts if c.settlement_price is not None]

        for label_suffix, offset in _SPREAD_CONFIGS:
            if len(prices) <= offset:
                continue  # Not enough contracts for this spread

            m1 = prices[0]
            mn = prices[offset]

            spread_value = m1.settlement_price - mn.settlement_price
            spread_type  = f"{sym}_{label_suffix}"
            front_month  = m1.contract_month
            back_month   = mn.contract_month

            # Upsert: find existing row by the unique constraint (date, spread_type, front_month)
            existing = session.query(Spread).filter_by(
                date=dt,
                spread_type=spread_type,
                front_month=front_month,
            ).first()

            if existing:
                existing.spread_value = spread_value
                existing.back_month   = back_month
            else:
                session.add(Spread(
                    date=dt,
                    spread_type=spread_type,
                    front_month=front_month,
                    back_month=back_month,
                    spread_value=spread_value,
                ))
                upserted += 1

        # Commit in batches to avoid holding huge transactions
        if upserted % BATCH_SIZE == 0 and upserted > 0:
            session.commit()

    session.commit()
    logger.info(f"Spread cache backfill complete: {upserted} rows inserted/updated.")
    return upserted
