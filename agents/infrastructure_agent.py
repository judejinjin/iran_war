"""
Infrastructure Agent — AI-powered disruption extraction and daily status computation.

Uses Claude to extract facility-level disruption events from news, classify shut-in
vs damage, and estimate impacts. Also computes daily rollup of facility/country status.
"""

import json
from datetime import date, timedelta
from loguru import logger

from config import WAR_START_DATE
from db.database import (
    get_session, GeopoliticalEvent, Facility, FacilityStatus,
    CountryProduction, DisruptionEvent, HormuzStatus, ChokepointStatus,
    RegionSupplySummary,
)
from agents.llm_client import get_llm_client, extract_json

# Country baselines for rollup
_BASELINES = {
    "IR": {"oil": 3.2, "gas": 8.5},
    "SA": {"oil": 10.5, "gas": 10.0},
    "IQ": {"oil": 4.5, "gas": 3.0},
    "AE": {"oil": 3.2, "gas": 6.0},
    "KW": {"oil": 2.7, "gas": 1.8},
    "QA": {"oil": 1.8, "gas": 16.0},
    "OM": {"oil": 1.0, "gas": 4.0},
    "BH": {"oil": 0.2, "gas": 1.5},
}

EXTRACTION_SYSTEM = """You are an expert oil and gas infrastructure analyst specializing in Middle East conflict damage assessment.

Given a news event about oil/gas infrastructure, extract structured disruption data.
You have a registry of known facilities to match against.

Rules:
- Match the affected facility from the registry by name/location (choose closest match)
- If no facility matches, set facility_match to "unknown"
- event_type: shut_in (temporary, can resume quickly) | damage (requires repair) | destruction (total loss) | partial_damage (reduced capacity) | precautionary_shutdown (voluntary closure due to threat)
- oil_impact_mbd: million barrels/day lost (0 if gas-only or unknown)
- gas_impact_bcfd: billion cubic feet/day lost (0 if oil-only or unknown)
- damage_pct: 0.0 to 1.0 (0=intact, 0.5=half capacity lost, 1.0=destroyed)
- repair_estimate_days: integer days to restore (null if unknown or operational)
- cause: airstrike | missile | drone | sabotage | fire | precautionary | sanctions
- confidence: confirmed (verified by multiple sources) | estimated (likely from context) | rumored (unverified)

Respond ONLY with valid JSON. No markdown wrapping."""

EXTRACTION_PROMPT = """Analyze this infrastructure event:

Headline: {headline}
Summary: {summary}
Location: {location_name}
Severity: {severity}/10
Reported Supply Impact: {supply_impact_mbd} mbd

Known facilities in the region:
{facilities_json}

Extract disruption details as JSON:
{{
    "facility_match": "exact facility name from registry or 'unknown'",
    "event_type": "shut_in|damage|destruction|partial_damage|precautionary_shutdown",
    "oil_impact_mbd": 0.0,
    "gas_impact_bcfd": 0.0,
    "damage_pct": 0.0,
    "repair_estimate_days": null,
    "cause": "airstrike|missile|drone|sabotage|fire|precautionary|sanctions",
    "confidence": "confirmed|estimated|rumored"
}}"""


def _get_facility_registry(session) -> list[dict]:
    """Get all facilities as simple dicts for LLM context."""
    facilities = session.query(Facility).all()
    return [
        {
            "id": f.id,
            "name": f.name,
            "country": f.country,
            "type": f.facility_type,
            "capacity_oil_mbd": f.capacity_oil_mbd or 0,
            "capacity_gas_bcfd": f.capacity_gas_bcfd or 0,
            "region": f.region or "",
        }
        for f in facilities
    ]


def _fuzzy_match_facility(name: str, facilities: list[dict]) -> dict | None:
    """Match extracted facility name to registry. Uses simple substring matching."""
    if not name or name.lower() == "unknown":
        return None
    name_lower = name.lower()
    # Exact name match
    for f in facilities:
        if f["name"].lower() == name_lower:
            return f
    # Substring match
    for f in facilities:
        if name_lower in f["name"].lower() or f["name"].lower() in name_lower:
            return f
    # Word overlap
    name_words = set(name_lower.split())
    best, best_score = None, 0
    for f in facilities:
        f_words = set(f["name"].lower().split())
        overlap = len(name_words & f_words)
        if overlap > best_score and overlap >= 2:
            best, best_score = f, overlap
    return best


def extract_disruption_from_event(event_id: int) -> dict | None:
    """
    Extract facility-level disruption data from a GeopoliticalEvent using Claude.

    Returns dict with disruption details, or None if extraction fails.
    """
    session = get_session()
    try:
        event = session.query(GeopoliticalEvent).get(event_id)
        if not event:
            logger.warning(f"Event {event_id} not found")
            return None

        facility_registry = _get_facility_registry(session)
        facilities_json = json.dumps(facility_registry, indent=2)

        prompt = EXTRACTION_PROMPT.format(
            headline=event.headline or "",
            summary=(event.summary or "")[:2000],
            location_name=event.location_name or "Unknown",
            severity=event.severity or 0,
            supply_impact_mbd=event.supply_impact_mbd or 0,
            facilities_json=facilities_json,
        )

        client = get_llm_client()
        response = client.simple_prompt(EXTRACTION_SYSTEM, prompt)

        # Parse JSON response
        try:
            data = extract_json(response)
        except ValueError:
            logger.warning(f"Failed to parse LLM response for event {event_id}: {response[:200]}")
            return None

        # Match facility
        matched = _fuzzy_match_facility(data.get("facility_match", ""), facility_registry)
        facility_id = matched["id"] if matched else None

        if not facility_id:
            logger.info(f"No facility match for event {event_id}: {data.get('facility_match')}")
            return None

        # Check for existing disruption for this event
        existing = session.query(DisruptionEvent).filter_by(
            source_event_id=event_id
        ).first()
        if existing:
            logger.debug(f"Disruption already exists for event {event_id}")
            return {"disruption_id": existing.id, "already_exists": True}

        # Create disruption event
        event_date = event.timestamp.date() if event.timestamp else date.today()
        repair_days = data.get("repair_estimate_days")

        disruption = DisruptionEvent(
            facility_id=facility_id,
            event_type=data.get("event_type", "damage"),
            start_date=event_date,
            is_resolved=False,
            cause=data.get("cause", "airstrike"),
            oil_impact_mbd=float(data.get("oil_impact_mbd", 0)),
            gas_impact_bcfd=float(data.get("gas_impact_bcfd", 0)),
            damage_pct=float(data.get("damage_pct", 0)),
            repair_estimate_days=int(repair_days) if repair_days else None,
            source_event_id=event_id,
            headline=event.headline,
            summary=event.summary,
            confidence=data.get("confidence", "estimated"),
        )
        session.add(disruption)
        session.commit()

        logger.info(
            f"Extracted disruption: {matched['name']} — "
            f"{data.get('event_type')} — {data.get('oil_impact_mbd', 0)} mbd oil, "
            f"{data.get('gas_impact_bcfd', 0)} bcf/d gas (event {event_id})"
        )
        return {
            "disruption_id": disruption.id,
            "facility": matched["name"],
            "event_type": data.get("event_type"),
            "oil_impact_mbd": data.get("oil_impact_mbd", 0),
            "gas_impact_bcfd": data.get("gas_impact_bcfd", 0),
        }

    except Exception as e:
        session.rollback()
        logger.error(f"extract_disruption_from_event({event_id}) failed: {e}")
        return None
    finally:
        session.close()


def extract_all_pending(limit: int = 50) -> int:
    """
    Process unextracted infrastructure/shutin/shipment events.
    Returns number of new disruptions created.
    """
    session = get_session()
    try:
        # Find events in relevant categories that don't yet have disruption_events
        from sqlalchemy import not_, exists
        already_extracted = session.query(DisruptionEvent.source_event_id).subquery()

        events = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.category.in_([
                "infrastructure_damage", "production_shutin", "shipment_disruption"
            ]),
            ~GeopoliticalEvent.id.in_(
                session.query(DisruptionEvent.source_event_id).filter(
                    DisruptionEvent.source_event_id.isnot(None)
                )
            ),
        ).order_by(GeopoliticalEvent.timestamp).limit(limit).all()

        event_ids = [e.id for e in events]
    finally:
        session.close()

    created = 0
    for eid in event_ids:
        result = extract_disruption_from_event(eid)
        if result and not result.get("already_exists"):
            created += 1

    logger.info(f"extract_all_pending: processed {len(event_ids)} events, created {created} disruptions")
    return created
