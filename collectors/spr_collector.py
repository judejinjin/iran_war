"""
SPR Collector — daily incremental update of Strategic Petroleum Reserve levels.

Fetches the most recent 8 weeks of EIA data (to catch revisions) and the latest
JODI monthly release, then upserts into spr_levels.

Scheduled daily at 18:30 ET (after EIA weekly petroleum status report, Wed 10:30 ET).
"""

from datetime import date, timedelta
from loguru import logger

from backfill.spr_backfill import run_backfill


def collect_latest() -> int:
    """
    Incrementally fetch the last 8 weeks of EIA SPR data and latest JODI month.
    Returns count of records upserted.
    """
    # Go back 8 weeks to catch any EIA revisions
    start_from = date.today() - timedelta(weeks=8)
    logger.info(f"SPR collector: incremental update from {start_from}")
    count = run_backfill(start_from=start_from)
    logger.info(f"SPR collector: {count} records upserted")
    return count
