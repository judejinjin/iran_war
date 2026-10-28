"""
Scheduler — APScheduler job configuration for all periodic tasks.

Jobs:
- News pipeline: every 2h, 24/7
- Market data (IB futures + options): 3×/day at 10:00, 13:00, 16:15 ET (weekdays)
- EIA/FRED data: 1×/day at 11:00 ET (weekdays)
- AI summaries: 2×/day at 08:00, 17:00 ET
- Scenario + trade analysis: 1×/day at 17:30 ET (weekdays)
- P&L projection: 1×/day at 17:45 ET (weekdays)
"""

import time
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config import SCHEDULE_TIMEZONE


_scheduler = None


def _job_wrapper(func, name):
    """Wrap a job function with timing and error logging."""
    def wrapper():
        start = time.time()
        logger.info(f"Job [{name}] started")
        try:
            result = func()
            elapsed = time.time() - start
            logger.info(f"Job [{name}] completed in {elapsed:.1f}s — {result}")
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"Job [{name}] failed after {elapsed:.1f}s: {e}")
    return wrapper


def _run_news_pipeline():
    """Scheduled: news collection + classification."""
    from collectors.news_collector import run_news_pipeline
    count = run_news_pipeline(classify=True)
    return f"{count} articles"


def _run_military_pipeline():
    """Scheduled: military intelligence extraction."""
    from collectors.military_collector import run_military_pipeline
    result = run_military_pipeline()
    return result


def _run_market_data():
    """Scheduled: IB futures + options data collection."""
    results = {}
    try:
        from collectors.ib_futures import collect_futures_snapshot
        results["futures"] = collect_futures_snapshot()
    except Exception as e:
        logger.error(f"Futures collection failed: {e}")
        results["futures"] = str(e)

    try:
        from collectors.ib_options import collect_options_snapshot
        results["options"] = collect_options_snapshot()
    except Exception as e:
        logger.error(f"Options collection failed: {e}")
        results["options"] = str(e)

    return results


def _run_eia_fred():
    """Scheduled: EIA + FRED weekly data + Dated Brent physical prices."""
    results = {}
    try:
        from backfill.eia_backfill import run_backfill as eia_backfill
        eia_backfill()
        results["eia"] = "ok"
    except Exception as e:
        logger.error(f"EIA update failed: {e}")
        results["eia"] = str(e)

    try:
        from backfill.fred_backfill import run_backfill as fred_backfill
        fred_backfill()
        results["fred"] = "ok"
    except Exception as e:
        logger.error(f"FRED update failed: {e}")
        results["fred"] = str(e)

    try:
        from datetime import date
        from db.database import get_session
        from backfill.dated_brent_backfill import run_backfill as dated_brent_backfill
        session = get_session()
        count = dated_brent_backfill(start_from=date.today(), session=session)
        session.close()
        results["dated_brent"] = f"{count} records"
    except Exception as e:
        logger.error(f"Dated Brent update failed: {e}")
        results["dated_brent"] = str(e)

    try:
        from datetime import date, timedelta
        from db.database import get_session
        from backfill.crack_spread_backfill import run_backfill as crack_backfill
        _cs_session = get_session()
        _cs_count = crack_backfill(
            start_from=date.today() - timedelta(days=7),
            session=_cs_session,
        )
        _cs_session.close()
        results["crack_spread"] = f"{_cs_count} records"
    except Exception as e:
        logger.error(f"Crack spread update failed: {e}")
        results["crack_spread"] = str(e)

    try:
        from datetime import date, timedelta
        from db.database import get_session
        from backfill.spread_cache_backfill import run_backfill as spread_cache_backfill
        _sc_session = get_session()
        _sc_count = spread_cache_backfill(
            start_from=date.today() - timedelta(days=60),
            session=_sc_session,
        )
        _sc_session.close()
        results["spread_cache"] = f"{_sc_count} records"
    except Exception as e:
        logger.error(f"Spread cache update failed: {e}")
        results["spread_cache"] = str(e)

    return results


def _run_ai_summaries():
    """Scheduled: AI daily summaries (geopolitical + military)."""
    from analysis.summarizer import run_all_summaries
    return run_all_summaries()


def _run_scenario_analysis():
    """Scheduled: scenario probability update."""
    from analysis.scenarios import update_scenario_probabilities
    count = update_scenario_probabilities()
    return f"{count} scenarios updated"


def _run_trade_analysis():
    """Scheduled: mispricing + trade recommendations."""
    from analysis.trade_recommender import run_trade_analysis
    result = run_trade_analysis()
    trades = len(result.get("trades", []))
    return f"{trades} trades recommended"


def _run_pnl_projection():
    """Scheduled: P&L projection for open positions."""
    from analysis.pnl_projector import project_all_positions
    result = project_all_positions()
    positions = len(result.get("positions", []))
    return f"{positions} positions projected"


def _run_spr():
    """Scheduled: SPR incremental data update."""
    from collectors.spr_collector import collect_latest
    count = collect_latest()
    return f"{count} SPR records upserted"


def _run_cushing():
    """Scheduled: Cushing inventory incremental update (last 8 weeks)."""
    from datetime import date, timedelta
    from backfill.cushing_backfill import run_backfill
    start_from = date.today() - timedelta(weeks=8)
    count = run_backfill(start_from=start_from)
    return f"{count} Cushing records upserted"


def _run_supply_demand():
    """Scheduled: Supply/demand incremental refresh (last 3 months)."""
    from backfill.supply_demand_backfill import run_incremental
    count = run_incremental(lookback_months=3)
    return f"{count} supply/demand rows upserted"


def create_scheduler() -> BackgroundScheduler:
    """Create and configure the APScheduler with all jobs."""
    et = pytz.timezone(SCHEDULE_TIMEZONE)
    scheduler = BackgroundScheduler(timezone=et)

    # ─── News — every 2 hours, 24/7 ─────────────────────────────────────
    scheduler.add_job(
        _job_wrapper(_run_news_pipeline, "news"),
        CronTrigger(hour="*/2", minute=0, timezone=et),
        id="news",
        name="News Collection Pipeline",
        replace_existing=True,
    )

    # ─── Military — after news, every 2 hours offset by 15 min ──────────
    scheduler.add_job(
        _job_wrapper(_run_military_pipeline, "military"),
        CronTrigger(hour="*/2", minute=15, timezone=et),
        id="military",
        name="Military Intelligence Pipeline",
        replace_existing=True,
    )

    # ─── Market Data — 3× daily on weekdays ─────────────────────────────
    for hour, minute, label in [(10, 0, "morning"), (13, 0, "midday"), (16, 15, "settlement")]:
        scheduler.add_job(
            _job_wrapper(_run_market_data, f"market_{label}"),
            CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri", timezone=et),
            id=f"market_{label}",
            name=f"Market Data ({label.title()})",
            replace_existing=True,
        )

    # ─── EIA/FRED — once daily 11:00 ET weekdays ────────────────────────
    scheduler.add_job(
        _job_wrapper(_run_eia_fred, "eia_fred"),
        CronTrigger(hour=11, minute=0, day_of_week="mon-fri", timezone=et),
        id="eia_fred",
        name="EIA + FRED Data Update",
        replace_existing=True,
    )

    # ─── AI Summaries — 08:00 and 17:00 ET ──────────────────────────────
    scheduler.add_job(
        _job_wrapper(_run_ai_summaries, "summary_morning"),
        CronTrigger(hour=8, minute=0, timezone=et),
        id="summary_morning",
        name="AI Summary (Morning)",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_wrapper(_run_ai_summaries, "summary_evening"),
        CronTrigger(hour=17, minute=0, timezone=et),
        id="summary_evening",
        name="AI Summary (Evening)",
        replace_existing=True,
    )

    # ─── Scenario + Trade Analysis — 17:30 ET weekdays ──────────────────
    scheduler.add_job(
        _job_wrapper(_run_scenario_analysis, "scenario"),
        CronTrigger(hour=17, minute=30, day_of_week="mon-fri", timezone=et),
        id="scenario",
        name="Scenario Probability Update",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_wrapper(_run_trade_analysis, "trade"),
        CronTrigger(hour=17, minute=45, day_of_week="mon-fri", timezone=et),
        id="trade",
        name="Trade Recommendation Analysis",
        replace_existing=True,
    )

    # ─── P&L Projection — 17:45 ET weekdays ─────────────────────────────
    scheduler.add_job(
        _job_wrapper(_run_pnl_projection, "pnl"),
        CronTrigger(hour=18, minute=0, day_of_week="mon-fri", timezone=et),
        id="pnl",
        name="P&L Projection",
        replace_existing=True,
    )

    # ─── SPR + Cushing — daily at 18:30 ET (after EIA Wed 10:30 report) ─
    scheduler.add_job(
        _job_wrapper(_run_spr, "spr"),
        CronTrigger(hour=18, minute=30, day_of_week="mon-fri", timezone=et),
        id="spr",
        name="SPR Data Update",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_wrapper(_run_cushing, "cushing"),
        CronTrigger(hour=18, minute=35, day_of_week="mon-fri", timezone=et),
        id="cushing",
        name="Cushing Inventory Update",
        replace_existing=True,
    )
    # ─── Supply/Demand — daily at 07:30 ET (EIA international updates monthly) ──
    scheduler.add_job(
        _job_wrapper(_run_supply_demand, "supply_demand"),
        CronTrigger(hour=7, minute=30, day_of_week="mon-fri", timezone=et),
        id="supply_demand",
        name="Supply/Demand Data Refresh",
        replace_existing=True,
    )
    return scheduler


def start_scheduler() -> BackgroundScheduler:
    """Create, start, and return the scheduler. Logs all scheduled jobs."""
    global _scheduler
    _scheduler = create_scheduler()
    _scheduler.start()

    logger.info("Scheduler started with jobs:")
    for job in _scheduler.get_jobs():
        logger.info(f"  [{job.id}] {job.name} — next run: {job.next_run_time}")

    return _scheduler


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
