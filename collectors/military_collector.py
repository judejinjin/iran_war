"""
Military Collector — Filters military events from news, fetches ACLED data.

Processes classified geopolitical events to extract military data and stores
in military_events, military_deployments tables.
"""

import requests
from datetime import date, datetime
from loguru import logger

from config import EVENT_REGISTRY_KEY
from db.database import (
    get_session, GeopoliticalEvent, MilitaryEvent, MilitaryDeployment,
)
from agents.military_agent import extract_military_data


def collect_military_from_events(target_date: date = None) -> int:
    """
    Filter today's classified geopolitical events for military_operations category,
    then extract structured military data via the military agent.

    Returns: number of military events created.
    """
    if target_date is None:
        target_date = date.today()

    session = get_session()
    try:
        # Get military-classified events for the date
        mil_events = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.timestamp >= datetime.combine(target_date, datetime.min.time()),
            GeopoliticalEvent.timestamp < datetime.combine(target_date, datetime.max.time()),
            GeopoliticalEvent.category == "military_operations",
        ).all()

        if not mil_events:
            logger.info(f"No military events to process for {target_date}")
            return 0

        # Also include infrastructure_damage as these often involve military action
        infra_events = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.timestamp >= datetime.combine(target_date, datetime.min.time()),
            GeopoliticalEvent.timestamp < datetime.combine(target_date, datetime.max.time()),
            GeopoliticalEvent.category == "infrastructure_damage",
        ).all()

        all_events = mil_events + infra_events
        created = 0

        # Extract military data via agent — batch by 5
        for i in range(0, len(all_events), 5):
            batch = all_events[i:i + 5]
            articles = [
                {
                    "id": e.id,
                    "headline": e.headline or "",
                    "summary": e.summary or "",
                    "latitude": e.latitude,
                    "longitude": e.longitude,
                    "location_name": e.location_name,
                }
                for e in batch
            ]

            results = extract_military_data(articles)

            for result in results:
                # Create military events
                for event_data in result.get("events", []):
                    existing = session.query(MilitaryEvent).filter(
                        MilitaryEvent.date == target_date,
                        MilitaryEvent.headline == result.get("headline", ""),
                        MilitaryEvent.side == event_data.get("side", "Unknown"),
                    ).first()

                    if existing:
                        continue

                    session.add(MilitaryEvent(
                        date=target_date,
                        side=event_data.get("side", "Unknown"),
                        event_type=event_data.get("event_type", "unknown"),
                        loss_type=event_data.get("loss_type"),
                        quantity=event_data.get("quantity"),
                        unit_name=event_data.get("unit_name"),
                        equipment_detail=event_data.get("equipment"),
                        headline=result.get("headline", ""),
                        summary=result.get("summary", ""),
                        source_url=result.get("source_url"),
                        latitude=event_data.get("latitude"),
                        longitude=event_data.get("longitude"),
                        location_name=event_data.get("location_name"),
                    ))
                    created += 1

                # Upsert deployments — match on the unique key (date, side, unit_name)
                for dep_data in result.get("deployments", []):
                    unit = dep_data.get("unit_name", "Unknown Unit")
                    side = dep_data.get("side", "Unknown")
                    existing_dep = session.query(MilitaryDeployment).filter_by(
                        date=target_date, side=side, unit_name=unit
                    ).first()
                    if existing_dep:
                        existing_dep.deployment_status = dep_data.get("status", "active")
                        existing_dep.force_type = dep_data.get("force_type", "unknown")
                        existing_dep.personnel_count = dep_data.get("personnel_count")
                        existing_dep.equipment_summary = dep_data.get("equipment")
                        existing_dep.region = dep_data.get("region")
                        existing_dep.latitude = dep_data.get("latitude")
                        existing_dep.longitude = dep_data.get("longitude")
                        existing_dep.location_name = dep_data.get("location_name")
                    else:
                        session.add(MilitaryDeployment(
                            date=target_date,
                            side=side,
                            deployment_status=dep_data.get("status", "active"),
                            force_type=dep_data.get("force_type", "unknown"),
                            unit_name=unit,
                            personnel_count=dep_data.get("personnel_count"),
                            equipment_summary=dep_data.get("equipment"),
                            region=dep_data.get("region"),
                            latitude=dep_data.get("latitude"),
                            longitude=dep_data.get("longitude"),
                            location_name=dep_data.get("location_name"),
                        ))

        session.commit()
        logger.info(f"Created {created} military events for {target_date}")
        return created

    except Exception as e:
        session.rollback()
        logger.error(f"Military collection failed: {e}")
        raise
    finally:
        session.close()


def fetch_acled_data(target_date: date = None, days_back: int = 7) -> list[dict]:
    """
    Fetch conflict event data from ACLED API (requires EVENT_REGISTRY_KEY or public access).
    Focuses on Iran/Middle East region.

    Returns: list of event dicts.
    """
    if target_date is None:
        target_date = date.today()

    start_date = target_date.replace(day=max(1, target_date.day - days_back))
    events = []

    try:
        params = {
            "event_date": f"{start_date}|{target_date}",
            "event_date_where": "BETWEEN",
            "region": "11",  # Middle East
            "limit": "500",
        }
        if EVENT_REGISTRY_KEY:
            params["key"] = EVENT_REGISTRY_KEY

        resp = requests.get(
            "https://api.acleddata.com/acled/read",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for row in data.get("data", []):
            # Filter for Iran-related events
            if not any(kw in str(row).lower() for kw in ["iran", "hormuz", "persian gulf", "irgc"]):
                continue

            events.append({
                "date": row.get("event_date"),
                "event_type": row.get("event_type"),
                "sub_event_type": row.get("sub_event_type"),
                "location": row.get("location"),
                "latitude": float(row["latitude"]) if row.get("latitude") else None,
                "longitude": float(row["longitude"]) if row.get("longitude") else None,
                "fatalities": int(row.get("fatalities", 0)),
                "notes": row.get("notes", ""),
            })

        logger.info(f"ACLED: {len(events)} Iran-related events")
    except Exception as e:
        logger.warning(f"ACLED fetch failed (may require API key): {e}")

    return events


def run_military_pipeline(target_date: date = None) -> dict:
    """
    Full military intelligence pipeline:
    1. Extract military data from classified news events
    2. Fetch ACLED conflict data (if available)
    3. Generate military daily summaries

    Returns: dict with counts.
    """
    if target_date is None:
        target_date = date.today()

    # Step 1: Process classified news → military events
    mil_count = collect_military_from_events(target_date)

    # Step 2: ACLED supplementary data
    acled_events = fetch_acled_data(target_date)
    acled_stored = 0
    if acled_events:
        session = get_session()
        try:
            for ae in acled_events:
                ae_date = datetime.strptime(ae["date"], "%Y-%m-%d").date() if isinstance(ae["date"], str) else ae["date"]
                existing = session.query(MilitaryEvent).filter(
                    MilitaryEvent.date == ae_date,
                    MilitaryEvent.location_name == ae.get("location"),
                    MilitaryEvent.event_type == ae.get("event_type"),
                ).first()
                if existing:
                    continue

                session.add(MilitaryEvent(
                    date=ae_date,
                    side="Unknown",
                    event_type=ae.get("event_type", "conflict"),
                    loss_type="personnel" if ae.get("fatalities", 0) > 0 else None,
                    quantity=ae.get("fatalities"),
                    headline=f"ACLED: {ae.get('sub_event_type', '')} in {ae.get('location', '')}",
                    summary=ae.get("notes", "")[:500],
                    latitude=ae.get("latitude"),
                    longitude=ae.get("longitude"),
                    location_name=ae.get("location"),
                ))
                acled_stored += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"ACLED storage failed: {e}")
        finally:
            session.close()

    # Step 3: Generate military daily summaries
    from analysis.summarizer import generate_military_daily_summary
    summary_count = generate_military_daily_summary(target_date)

    return {
        "military_events_from_news": mil_count,
        "acled_events": acled_stored,
        "military_summaries": summary_count,
    }
