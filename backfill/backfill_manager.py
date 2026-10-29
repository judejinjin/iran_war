"""
Backfill Manager — orchestrates first-run historical data loading.

Checks backfill_status table and runs each source in order,
resuming from last_backfilled_date if interrupted.
"""

from datetime import datetime, date
from loguru import logger

from config import WAR_START_DATE
from db.database import get_session, BackfillStatus


BACKFILL_SOURCES = ["fred", "yahoo", "ib_futures", "ib_options", "eia", "gdelt", "dated_brent", "scenarios", "spr", "cushing", "crack_spread", "spread_cache"]


class BackfillManager:
    def __init__(self):
        self.session = get_session()
        self.war_start = datetime.strptime(WAR_START_DATE, "%Y-%m-%d").date()

    def _ensure_status_rows(self):
        """Create backfill_status rows for any missing sources."""
        for source in BACKFILL_SOURCES:
            existing = self.session.query(BackfillStatus).filter_by(source=source).first()
            if not existing:
                self.session.add(BackfillStatus(
                    source=source,
                    war_start_date=self.war_start,
                    status="pending",
                ))
        self.session.commit()

    def needs_backfill(self) -> bool:
        """Return True if any source is not 'complete'."""
        self._ensure_status_rows()
        incomplete = self.session.query(BackfillStatus).filter(
            BackfillStatus.status != "complete"
        ).count()
        return incomplete > 0

    def get_status(self, source: str) -> dict:
        """Return status dict for a source."""
        row = self.session.query(BackfillStatus).filter_by(source=source).first()
        if not row:
            return {"status": "pending", "last_backfilled_date": None}
        return {
            "status": row.status,
            "last_backfilled_date": row.last_backfilled_date,
            "total_records": row.total_records,
            "error_message": row.error_message,
        }

    def update_status(self, source: str, status: str, last_date=None,
                      records=None, error=None):
        row = self.session.query(BackfillStatus).filter_by(source=source).first()
        if row:
            row.status = status
            row.updated_at = datetime.utcnow()
            if last_date:
                row.last_backfilled_date = last_date
            if records is not None:
                row.total_records = (row.total_records or 0) + records
            if error:
                row.error_message = error
            if status == "in_progress" and not row.started_at:
                row.started_at = datetime.utcnow()
            if status == "complete":
                row.completed_at = datetime.utcnow()
            self.session.commit()

    def run(self, sources=None):
        """
        Run backfill for specified sources (or all incomplete ones).
        Skips sources already marked 'complete'.
        """
        self._ensure_status_rows()

        if sources is None:
            sources = BACKFILL_SOURCES

        for source in sources:
            status = self.get_status(source)
            if status["status"] == "complete":
                logger.info(f"Backfill [{source}] already complete, skipping.")
                continue
            self._run_source(source, status)

    def run_incremental(self, sources=None):
        """
        Always re-run sources to pick up new data since last run.
        Resets 'complete' sources back to 'pending' so they fetch new data.
        """
        self._ensure_status_rows()

        if sources is None:
            sources = BACKFILL_SOURCES

        for source in sources:
            status = self.get_status(source)
            # Reset complete → pending so the runner fetches from last_backfilled_date to today
            if status["status"] == "complete":
                self.update_status(source, "pending")
                status["status"] = "pending"
            self._run_source(source, status)

    def _run_source(self, source: str, status: dict):
        """Execute a single backfill source."""
        logger.info(f"Starting backfill [{source}]...")
        self.update_status(source, "in_progress")

        try:
            runner = self._get_runner(source)
            if runner is None:
                logger.warning(f"Backfill runner for [{source}] not yet implemented, skipping.")
                self.update_status(source, "pending")
                return

            last_date = status.get("last_backfilled_date")
            start_from = last_date if last_date else self.war_start
            count = runner(start_from, self.session)

            # GDELT returns a dict; extract article count
            if isinstance(count, dict):
                count = count.get("articles_stored", 0)

            self.update_status(source, "complete", records=count)
            logger.info(f"Backfill [{source}] complete: {count} records.")

        except Exception as e:
            logger.error(f"Backfill [{source}] failed: {e}")
            self.update_status(source, "pending", error=str(e))

    def _get_runner(self, source: str):
        """Dynamically import and return the run function for a source."""
        try:
            if source == "fred":
                from backfill.fred_backfill import run_backfill
                return run_backfill
            elif source == "yahoo":
                from backfill.yahoo_backfill import run_backfill
                return run_backfill
            elif source == "ib_futures":
                from backfill.ib_backfill import run_backfill
                return run_backfill
            elif source == "eia":
                from backfill.eia_backfill import run_backfill
                return run_backfill
            elif source == "ib_options":
                from backfill.ib_options_backfill import run_backfill
                return run_backfill
            elif source == "gdelt":
                from backfill.gdelt_backfill import run_backfill
                return run_backfill
            elif source == "dated_brent":
                from backfill.dated_brent_backfill import run_backfill
                return run_backfill
            elif source == "scenarios":
                # Implemented in Phase 4
                return None
            elif source == "spr":
                from backfill.spr_backfill import run_backfill
                return run_backfill
            elif source == "cushing":
                from backfill.cushing_backfill import run_backfill
                return run_backfill
            elif source == "crack_spread":
                from backfill.crack_spread_backfill import run_backfill
                return run_backfill
            elif source == "historical_contracts":
                from backfill.historical_contracts_backfill import run_backfill
                return run_backfill
            elif source == "spread_cache":
                from backfill.spread_cache_backfill import run_backfill
                return run_backfill
        except ImportError as e:
            logger.warning(f"Could not import backfill runner for [{source}]: {e}")
            return None

    def close(self):
        self.session.close()
