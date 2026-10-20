"""
Oil Super Spike Analyzer — Main Entry Point

Startup flow: load .env → init DB → check backfill → start scheduler → launch Dash.
"""

import sys
import argparse
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from config import LOG_DIR, DASH_DEBUG


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")
    logger.add(
        LOG_DIR / "oil_{time:YYYY-MM-DD}.log",
        rotation="1 day", retention="30 days",
        level="DEBUG", format="{time} | {level} | {module}:{line} | {message}",
    )


def main():
    parser = argparse.ArgumentParser(description="Oil Super Spike Analyzer")
    parser.add_argument("--skip-backfill", action="store_true", help="Skip historical backfill")
    parser.add_argument("--skip-scheduler", action="store_true", help="Don't start APScheduler")
    parser.add_argument("--backfill-only", action="store_true", help="Run backfill then exit")
    parser.add_argument("--ib-options", action="store_true",
                        help="Run IB options backfill (requires TWS, ~5 min)")
    args = parser.parse_args()

    setup_logging()
    logger.info("=== Oil Super Spike Analyzer starting ===")

    # 1. Initialize database
    logger.info("Initializing database...")
    from db.database import init_db, get_session
    init_db()
    logger.info("Database ready.")

    # 2. Automated data quality gate: futures first, then options
    try:
        quality_session = get_session()
        from data_quality_report import run_quality_pass
        q = run_quality_pass(quality_session, fix=True)
        logger.info(
            "Automated quality pass: futures status={f_status}, null_prices={f_null}, duplicates={f_dups}; "
            "options status={o_status}, missing_last_price={o_missing}, missing_pairs={o_pairs}",
            f_status=q["futures"]["status"],
            f_null=q["futures"]["null_prices"],
            f_dups=q["futures"]["duplicate_keys"],
            o_status=q["options"]["status"],
            o_missing=q["options"]["missing_last_price"],
            o_pairs=q["options"]["missing_call_put_pairs"],
        )
    except Exception as e:
        logger.warning(f"Automated quality pass failed: {e}")
    finally:
        try:
            quality_session.close()
        except Exception:
            pass

    # 3. Historical backfill — always run incremental for all sources
    if not args.skip_backfill:
        logger.info("Running backfill (incremental — fetches any new data since last run)...")
        from backfill.backfill_manager import BackfillManager
        bm = BackfillManager()
        # Market data sources (fast, always safe to re-run)
        bm.run_incremental(sources=["fred", "yahoo", "eia", "cushing"])
        # News + geopolitical data (GDELT day-by-day)
        bm.run_incremental(sources=["gdelt"])

        # IB historical options backfill (~5 min with parallel requests, needs TWS running)
        if args.ib_options:
            logger.info("Running IB options backfill (parallel async, ~5 minutes)...")
            bm.run_incremental(sources=["ib_options"])

        # Recompute IV/Greeks for any options rows missing them (uses DB data, no IB needed)
        from backfill.ib_options_backfill import recompute_greeks
        from db.database import get_session
        _sess = get_session()
        try:
            n = recompute_greeks(_sess)
            if n:
                logger.info(f"Recomputed IV/Greeks for {n} options rows")
        finally:
            _sess.close()

        # Quick RSS + GDELT live fetch (gets current headlines even if backfill was rate-limited)
        try:
            from collectors.news_collector import run_news_pipeline
            n = run_news_pipeline(classify=True)
            logger.info(f"News pipeline: {n} new articles from RSS/GDELT live.")
        except Exception as e:
            logger.warning(f"News pipeline failed: {e}")
        logger.info("Backfill complete.")
        bm.close()

        # Run production tracking pipeline for today
        try:
            from datetime import date as _date
            from collectors.production_tracker import compute_daily_status
            compute_daily_status(_date.today())
            logger.info("Production tracker: daily status computed.")
        except Exception as e:
            logger.warning(f"Production tracker failed: {e}")

    if args.backfill_only:
        logger.info("Backfill-only mode, exiting.")
        return

    # 3. Start scheduler
    if not args.skip_scheduler:
        logger.info("Starting APScheduler...")
        try:
            from scheduler import start_scheduler
            start_scheduler()
            logger.info("Scheduler started.")
        except Exception as e:
            logger.warning(f"Scheduler failed to start: {e}. Continuing without scheduler.")

    # 4. Launch Dash
    logger.info("Launching Dash application...")
    from ui.app import start_app
    start_app()


if __name__ == "__main__":
    main()
