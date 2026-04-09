"""
News Backfill — Day-by-day fetch from WAR_START_DATE using NewsAPI.

Fetches articles for each day, classifies them, extracts military data,
and generates retroactive summaries.
"""

import time
from datetime import date, datetime, timedelta
from loguru import logger

from config import WAR_START_DATE
from db.database import get_session, BackfillStatus, GeopoliticalEvent, DisruptionEvent
from collectors.news_collector import (
    fetch_newsapi_for_date, deduplicate_articles, extract_article_body,
)
from agents.geopolitical_agent import classify_batch, _fuzzy_match_facility
from collectors.military_collector import collect_military_from_events
from analysis.summarizer import generate_daily_summaries, generate_military_daily_summary

# NewsAPI free tier: 100 req/day — one request per date is fine for 29 days.
NEWSAPI_BETWEEN_DATES_SLEEP = 2  # seconds between date requests


def run_backfill(start_from=None, session=None) -> dict:
    """
    Backfill articles from WAR_START_DATE to today via NewsAPI.
    Processes each day: fetch → dedup → store → classify → military extract → summarize.

    Resumes from last_backfilled_date if interrupted.
    Returns: dict with stats.
    """
    close_session = False
    if session is None:
        session = get_session()
        close_session = True

    try:
        war_start = datetime.strptime(WAR_START_DATE, "%Y-%m-%d").date()
        today = date.today()

        # Check resume point
        status = session.query(BackfillStatus).filter(
            BackfillStatus.source == "gdelt"
        ).first()

        if status and status.last_backfilled_date:
            start_date = status.last_backfilled_date + timedelta(days=1)
        else:
            start_date = war_start

        if start_date > today:
            logger.info("News backfill already complete")
            return {"status": "complete", "days_processed": 0}

        total_days = (today - start_date).days + 1
        total_articles = 0
        total_classified = 0

        logger.info(f"News backfill: {start_date} → {today} ({total_days} days)")

        current_date = start_date
        consecutive_failures = 0
        while current_date <= today:
            try:
                # Fetch articles for this day (None = failed, [] = no articles)
                articles = fetch_newsapi_for_date(current_date)

                if articles is None:
                    # Fetch failed — don't advance date
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        logger.warning(
                            f"News backfill: {consecutive_failures} consecutive failures, "
                            f"stopping at {current_date} (will resume next run)"
                        )
                        break
                    time.sleep(10)
                    continue

                consecutive_failures = 0  # reset on success

                if articles:
                    # Deduplicate
                    articles = deduplicate_articles(articles)

                    # Filter already stored
                    existing_urls = set()
                    rows = session.query(GeopoliticalEvent.source_url).filter(
                        GeopoliticalEvent.timestamp >= datetime.combine(current_date, datetime.min.time()),
                        GeopoliticalEvent.timestamp < datetime.combine(current_date, datetime.max.time()),
                    ).all()
                    for (url,) in rows:
                        if url:
                            existing_urls.add(url.strip().lower())

                    new_articles = [
                        a for a in articles
                        if a.get("source_url", "").strip().lower() not in existing_urls
                    ]

                    # Extract bodies for top 10
                    for art in new_articles[:10]:
                        if art.get("source_url") and not art.get("summary"):
                            body = extract_article_body(art["source_url"])
                            if body:
                                art["summary"] = body[:500]

                    # Store raw events
                    event_ids = []
                    for art in new_articles:
                        event = GeopoliticalEvent(
                            timestamp=art.get("timestamp", datetime.combine(current_date, datetime.min.time())),
                            category="unclassified",
                            headline=art.get("headline", ""),
                            summary=art.get("summary", ""),
                            source_url=art.get("source_url", ""),
                        )
                        session.add(event)
                        session.flush()
                        event_ids.append(event.id)

                    total_articles += len(new_articles)

                    # Classify via batch agent
                    if event_ids:
                        events = session.query(GeopoliticalEvent).filter(
                            GeopoliticalEvent.id.in_(event_ids)
                        ).all()

                        batch_input = [
                            {"id": e.id, "headline": e.headline or "", "summary": e.summary or ""}
                            for e in events
                        ]

                        # Process in batches of 10
                        for i in range(0, len(batch_input), 10):
                            batch = batch_input[i:i + 10]
                            try:
                                results = classify_batch(batch)
                                result_map = {r["id"]: r for r in results if "id" in r}

                                for event in events:
                                    r = result_map.get(event.id)
                                    if r:
                                        event.category = r.get("category", "geopolitical_development")
                                        event.severity = r.get("severity", 5)
                                        event.supply_impact_mbd = r.get("supply_impact_mbd", 0)
                                        event.latitude = r.get("latitude")
                                        event.longitude = r.get("longitude")
                                        event.location_name = r.get("location_name")
                                        total_classified += 1

                                        # Create DisruptionEvent if extracted
                                        disruption = r.get("disruption")
                                        if disruption and isinstance(disruption, dict):
                                            fac_name = disruption.get("facility_match", "")
                                            fac_id = _fuzzy_match_facility(fac_name, session)
                                            if fac_id:
                                                existing = session.query(DisruptionEvent).filter_by(
                                                    source_event_id=event.id,
                                                    facility_id=fac_id,
                                                ).first()
                                                if not existing:
                                                    de = DisruptionEvent(
                                                        facility_id=fac_id,
                                                        source_event_id=event.id,
                                                        event_type=disruption.get("event_type", "damage"),
                                                        start_date=current_date,
                                                        is_resolved=False,
                                                        oil_impact_mbd=float(disruption.get("oil_impact_mbd", 0)),
                                                        gas_impact_bcfd=float(disruption.get("gas_impact_bcfd", 0)),
                                                        damage_pct=float(disruption.get("damage_pct", 0)),
                                                        repair_estimate_days=disruption.get("repair_estimate_days"),
                                                        cause=disruption.get("cause", "unknown"),
                                                        confidence=disruption.get("confidence", "estimated"),
                                                        headline=event.headline,
                                                        summary=event.summary,
                                                    )
                                                    session.add(de)
                            except Exception as e:
                                logger.warning(f"Batch classify failed for {current_date}: {e}")

                    session.commit()

                # Military extraction (uses committed data)
                try:
                    collect_military_from_events(current_date)
                except Exception as e:
                    logger.warning(f"Military extraction failed for {current_date}: {e}")

                # Generate summaries
                try:
                    generate_daily_summaries(current_date)
                    generate_military_daily_summary(current_date)
                except Exception as e:
                    logger.warning(f"Summary generation failed for {current_date}: {e}")

                # Update backfill status
                if status:
                    status.last_backfilled_date = current_date
                    status.total_records = total_articles
                    status.updated_at = datetime.utcnow()
                session.commit()

                days_done = (current_date - start_date).days + 1
                if days_done % 7 == 0:
                    logger.info(f"News backfill progress: {days_done}/{total_days} days, {total_articles} articles")

            except Exception as e:
                logger.error(f"News backfill day {current_date} failed: {e}")
                session.rollback()

            time.sleep(NEWSAPI_BETWEEN_DATES_SLEEP)
            current_date += timedelta(days=1)

        # Mark complete only if we actually processed all days
        all_done = current_date > today
        if status and all_done:
            status.status = "complete"
            status.completed_at = datetime.utcnow()
            session.commit()

        fin = "complete" if all_done else f"partial (stopped at {current_date})"
        logger.info(f"News backfill {fin}: {total_articles} articles, {total_classified} classified")
        return {
            "status": "complete" if all_done else "partial",
            "days_processed": total_days,
            "articles_stored": total_articles,
            "articles_classified": total_classified,
        }

    except Exception as e:
        logger.error(f"News backfill failed: {e}")
        raise
    finally:
        if close_session:
            session.close()
