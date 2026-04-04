"""
Geopolitical Agent — AI classification of news articles.

Uses Claude Sonnet 4.6 to classify articles into 5 categories, extract severity,
supply impact, geolocation, AND facility-level disruption data in a single call.

This consolidates what was previously two separate LLM calls (classification +
infrastructure extraction) into one call per batch.
"""

import json
from datetime import datetime, date
from loguru import logger

from config import EVENT_CATEGORIES
from db.database import get_session, GeopoliticalEvent, Facility, DisruptionEvent
from agents.llm_client import get_llm_client


CLASSIFICATION_SYSTEM = """You are an expert geopolitical analyst specializing in Middle East conflict and global oil markets. 
You classify news articles about the Iran-related conflict and its impact on oil supply.

For each article, you must provide:
1. **category**: One of: geopolitical_development, military_operations, infrastructure_damage, production_shutin, shipment_disruption
2. **severity**: Integer 1-10 (1=minor mention, 5=significant development, 10=catastrophic event)
3. **supply_impact_mbd**: Estimated supply impact in million barrels/day (0.0 if no direct impact, up to 20+ for Hormuz closure)
4. **latitude**: Approximate latitude of the event location (null if unknown)
5. **longitude**: Approximate longitude of the event location (null if unknown)
6. **location_name**: Name of the location (null if unknown)

Category definitions:
- geopolitical_development: Diplomatic moves, sanctions, alliances, negotiations, political statements
- military_operations: Combat operations, strikes, troop movements, naval operations, missile launches
- infrastructure_damage: Damage to oil facilities, refineries, pipelines, ports, storage
- production_shutin: Production halted or reduced at specific fields or countries
- shipment_disruption: Tanker attacks, shipping lane closures, port blockades, insurance changes

Respond ONLY with valid JSON. No markdown, no explanation outside JSON."""

CLASSIFICATION_USER = """Classify this article:

Headline: {headline}
Summary: {summary}
Source: {source_url}
Date: {timestamp}

Respond with JSON:
{{
    "category": "...",
    "severity": N,
    "supply_impact_mbd": N.N,
    "latitude": N.N or null,
    "longitude": N.N or null,
    "location_name": "..." or null
}}"""


UNIFIED_BATCH_SYSTEM = """You are an expert geopolitical and oil infrastructure analyst. You classify news articles about the Iran conflict/oil markets AND extract facility-level disruption data in a single pass.

For EVERY article, provide classification:
- category: one of [geopolitical_development, military_operations, infrastructure_damage, production_shutin, shipment_disruption]
- severity: 1-10
- supply_impact_mbd: float (million barrels/day)
- latitude/longitude: approximate or null
- location_name: string or null

ADDITIONALLY, for articles in categories [infrastructure_damage, production_shutin, shipment_disruption], also extract disruption data:
- facility_match: exact name from the facility registry provided, or "unknown" if no match
- event_type: shut_in | damage | destruction | partial_damage | precautionary_shutdown
- oil_impact_mbd: million barrels/day lost (0 if gas-only or unknown)
- gas_impact_bcfd: billion cubic feet/day lost (0 if oil-only or unknown)
- damage_pct: 0.0 to 1.0 (0=intact, 0.5=half capacity, 1.0=destroyed)
- repair_estimate_days: integer or null
- cause: airstrike | missile | drone | sabotage | fire | precautionary | sanctions | blockade | mining
- confidence: confirmed | estimated | rumored

For articles NOT in those 3 categories, set "disruption" to null.

Respond with a JSON array. Each element MUST have an "id" field matching the input."""


def _get_facility_registry_json() -> str:
    """Get facility registry as JSON for LLM context. Cached per session."""
    session = get_session()
    try:
        facilities = session.query(Facility).all()
        registry = [
            {
                "name": f.name,
                "country": f.country,
                "type": f.facility_type,
                "capacity_oil_mbd": f.capacity_oil_mbd or 0,
                "capacity_gas_bcfd": f.capacity_gas_bcfd or 0,
                "region": f.region or "",
            }
            for f in facilities
        ]
        return json.dumps(registry, indent=1)
    finally:
        session.close()


def _fuzzy_match_facility(name: str, session) -> int | None:
    """Match extracted facility name to DB registry. Returns facility_id or None."""
    if not name or name.lower() == "unknown":
        return None
    facilities = session.query(Facility).all()
    name_lower = name.lower()
    # Exact match
    for f in facilities:
        if f.name.lower() == name_lower:
            return f.id
    # Substring match
    for f in facilities:
        if name_lower in f.name.lower() or f.name.lower() in name_lower:
            return f.id
    # Word overlap
    name_words = set(name_lower.split())
    best_id, best_score = None, 0
    for f in facilities:
        f_words = set(f.name.lower().split())
        overlap = len(name_words & f_words)
        if overlap > best_score and overlap >= 2:
            best_id, best_score = f.id, overlap
    return best_id


def classify_single_article(headline: str, summary: str,
                            source_url: str = "", timestamp: str = "") -> dict:
    """Classify a single article via Claude. Returns classification dict."""
    client = get_llm_client()

    prompt = CLASSIFICATION_USER.format(
        headline=headline,
        summary=summary[:1000],
        source_url=source_url,
        timestamp=timestamp,
    )

    try:
        response = client.simple_prompt(CLASSIFICATION_SYSTEM, prompt)

        # Parse JSON from response
        text = response.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

        result = json.loads(text)

        # Validate
        if result.get("category") not in EVENT_CATEGORIES:
            result["category"] = "geopolitical_development"
        result["severity"] = max(1, min(10, int(result.get("severity", 5))))
        result["supply_impact_mbd"] = max(0.0, float(result.get("supply_impact_mbd", 0.0)))

        return result

    except Exception as e:
        logger.warning(f"Classification failed for '{headline[:60]}': {e}")
        return {
            "category": "geopolitical_development",
            "severity": 5,
            "supply_impact_mbd": 0.0,
            "latitude": None,
            "longitude": None,
            "location_name": None,
        }


def classify_batch(articles: list[dict]) -> list[dict]:
    """
    Classify multiple articles AND extract facility disruption data in one Claude call.
    Each article dict should have: id, headline, summary.
    Returns list of dicts with classification + optional disruption fields.
    """
    if not articles:
        return []

    client = get_llm_client()

    # Build batch prompt with facility registry for disruption extraction
    facility_json = _get_facility_registry_json()

    items = []
    for art in articles:
        items.append({
            "id": art["id"],
            "headline": art.get("headline", ""),
            "summary": art.get("summary", "")[:500],
        })

    prompt = (
        f"Known oil/gas facilities:\n{facility_json}\n\n"
        f"Classify these {len(items)} articles and extract disruption data where applicable:\n\n"
        f"{json.dumps(items, indent=1)}\n\n"
        "Respond with a JSON array. For each article:\n"
        '{"id": N, "category": "...", "severity": N, "supply_impact_mbd": N.N, '
        '"latitude": N.N, "longitude": N.N, "location_name": "...", '
        '"disruption": {<disruption fields>} or null}'
    )

    try:
        response = client.simple_prompt(UNIFIED_BATCH_SYSTEM, prompt)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

        results = json.loads(text)
        if not isinstance(results, list):
            results = [results]

        # Validate each
        for r in results:
            if r.get("category") not in EVENT_CATEGORIES:
                r["category"] = "geopolitical_development"
            r["severity"] = max(1, min(10, int(r.get("severity", 5))))
            r["supply_impact_mbd"] = max(0.0, float(r.get("supply_impact_mbd", 0.0)))

        return results

    except Exception as e:
        logger.error(f"Batch classification failed: {e}")
        # Fall back to individual classification
        return [
            {
                "id": art["id"],
                **classify_single_article(
                    art.get("headline", ""),
                    art.get("summary", ""),
                ),
            }
            for art in articles
        ]


def classify_events(event_ids: list[int]) -> int:
    """
    Classify geopolitical events by ID. Updates DB rows with category,
    severity, supply_impact, and geolocation. Also creates DisruptionEvent
    rows for infrastructure/production/shipment articles (single LLM call).

    Args:
        event_ids: List of geopolitical_events.id values to classify.

    Returns:
        Number of events successfully classified.
    """
    session = get_session()
    try:
        events = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.id.in_(event_ids)
        ).all()

        if not events:
            return 0

        # Batch classify in groups of 10
        BATCH_SIZE = 10
        classified = 0
        disruptions_created = 0

        for i in range(0, len(events), BATCH_SIZE):
            batch = events[i:i + BATCH_SIZE]
            articles = [
                {
                    "id": e.id,
                    "headline": e.headline or "",
                    "summary": e.summary or "",
                }
                for e in batch
            ]

            results = classify_batch(articles)

            # Map results by id
            result_map = {r["id"]: r for r in results if "id" in r}

            for event in batch:
                r = result_map.get(event.id)
                if not r:
                    continue

                event.category = r.get("category", "geopolitical_development")
                event.severity = r.get("severity", 5)
                event.supply_impact_mbd = r.get("supply_impact_mbd", 0.0)
                event.latitude = r.get("latitude")
                event.longitude = r.get("longitude")
                event.location_name = r.get("location_name")
                classified += 1

                # Create DisruptionEvent if disruption data was extracted
                disruption = r.get("disruption")
                if not disruption or not isinstance(disruption, dict):
                    continue

                facility_name = disruption.get("facility_match", "")
                facility_id = _fuzzy_match_facility(facility_name, session)
                if not facility_id:
                    logger.debug(
                        f"No facility match for '{facility_name}' "
                        f"from event {event.id}"
                    )
                    continue

                # Check for duplicate
                existing = session.query(DisruptionEvent).filter_by(
                    source_event_id=event.id,
                    facility_id=facility_id,
                ).first()
                if existing:
                    continue

                de = DisruptionEvent(
                    facility_id=facility_id,
                    source_event_id=event.id,
                    event_type=disruption.get("event_type", "damage"),
                    start_date=event.event_date or date.today(),
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
                disruptions_created += 1

        session.commit()
        logger.info(
            f"Classified {classified}/{len(events)} events, "
            f"created {disruptions_created} disruption events"
        )
        return classified

    except Exception as e:
        session.rollback()
        logger.error(f"Event classification failed: {e}")
        raise
    finally:
        session.close()
