"""
Production Backfill — reconstruct facility disruption history since WAR_START_DATE.

Processes existing GeopoliticalEvents through the infrastructure agent, then runs
the production tracker to compute daily status for each date.

Usage:
    python -m backfill.production_backfill [--skip-extraction] [--start YYYY-MM-DD]
"""

import argparse
from datetime import date, timedelta
from loguru import logger

from config import WAR_START_DATE
from db.database import init_db


def run_backfill(skip_extraction: bool = False, start_date: str | None = None):
    """
    Full historical backfill of production tracking data.

    Steps:
    1. Extract disruption events from all historical infrastructure news (unless skipped)
    2. Compute daily status for each date from WAR_START_DATE to today
    """
    init_db()
    war_start = date.fromisoformat(start_date or WAR_START_DATE)
    today = date.today()

    # Step 1: Extract disruptions from existing events
    if not skip_extraction:
        logger.info("Step 1: Extracting disruptions from historical events...")
        try:
            from agents.infrastructure_agent import extract_all_pending
            created = extract_all_pending(limit=500)
            logger.info(f"Extracted {created} new disruption events from historical news.")
        except Exception as e:
            logger.error(f"Disruption extraction failed: {e}")
            logger.info("Continuing with daily status computation...")

    # Step 2: Compute daily status for each date
    logger.info(f"Step 2: Computing daily status from {war_start} to {today}...")
    from collectors.production_tracker import compute_daily_status

    d = war_start
    count = 0
    errors = 0
    while d <= today:
        try:
            compute_daily_status(d)
            count += 1
            if count % 7 == 0:
                logger.info(f"  Processed {count} days (current: {d})")
        except Exception as e:
            logger.warning(f"  Failed for {d}: {e}")
            errors += 1
        d += timedelta(days=1)

    logger.info(
        f"Production backfill complete: {count} days processed, {errors} errors. "
        f"Range: {war_start} to {today}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Production tracking backfill")
    parser.add_argument("--skip-extraction", action="store_true",
                        help="Skip AI disruption extraction (use existing disruption_events)")
    parser.add_argument("--start", type=str, default=None,
                        help="Override start date (default: WAR_START_DATE)")
    args = parser.parse_args()

    run_backfill(skip_extraction=args.skip_extraction, start_date=args.start)
