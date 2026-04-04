"""
Military Agent — AI extraction of structured military data from news articles.

Uses Claude Sonnet 4.6 to extract: side, loss type, quantities, units,
equipment, deployments, coordinates from military news.
"""

import json
from loguru import logger

from agents.llm_client import get_llm_client


MILITARY_SYSTEM = """You are a military intelligence analyst. Given news articles about the Iran conflict, extract structured military data.

For each article, extract ALL of the following that apply:

**Events** (combat actions, strikes, losses):
- side: "Iran" or "Opposing" (US, Israel, coalition, etc.)
- event_type: one of [airstrike, naval_engagement, missile_launch, ground_operation, drone_attack, cyber_attack, special_operation]
- loss_type: one of [personnel, aircraft, naval_vessel, armor, missile, drone, infrastructure] or null
- quantity: integer count of losses, or null
- unit_name: military unit involved, or null
- equipment: specific equipment mentioned (e.g., "F-35A", "Shahed-136"), or null
- latitude/longitude: approximate coordinates if mentioned or inferable
- location_name: location name

**Deployments** (troop/asset movements, positioning):
- side: "Iran" or "Opposing"
- status: "active", "pending", "withdrawn"
- force_type: one of [air_force, navy, ground_forces, missile_forces, special_forces, cyber]
- unit_name: unit identifier
- personnel_count: estimated personnel, or null
- equipment: key equipment listed
- region: deployment region
- latitude/longitude: approximate coordinates
- location_name: location name

Respond with a JSON array. Each element corresponds to one input article and has:
{
    "id": <matching input id>,
    "headline": "...",
    "events": [{...}, ...],
    "deployments": [{...}, ...]
}

If an article has no extractable military data, return empty arrays for events and deployments."""


def extract_military_data(articles: list[dict]) -> list[dict]:
    """
    Extract structured military data from news articles via Claude.

    Args:
        articles: List of dicts with id, headline, summary, latitude, longitude, location_name.

    Returns:
        List of dicts with id, headline, events[], deployments[].
    """
    if not articles:
        return []

    client = get_llm_client()

    # Build prompt
    items = []
    for art in articles:
        items.append({
            "id": art["id"],
            "headline": art.get("headline", ""),
            "summary": art.get("summary", "")[:500],
            "known_latitude": art.get("latitude"),
            "known_longitude": art.get("longitude"),
            "known_location": art.get("location_name"),
        })

    prompt = f"Extract military data from these {len(items)} articles:\n\n{json.dumps(items, indent=1)}"

    try:
        response = client.simple_prompt(MILITARY_SYSTEM, prompt)
        text = response.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

        results = json.loads(text)
        if not isinstance(results, list):
            results = [results]

        # Validate and clean
        for r in results:
            # Ensure events is a list
            if not isinstance(r.get("events"), list):
                r["events"] = []
            if not isinstance(r.get("deployments"), list):
                r["deployments"] = []

            # Validate each event
            valid_sides = {"Iran", "Opposing", "Unknown"}
            for event in r["events"]:
                if event.get("side") not in valid_sides:
                    event["side"] = "Unknown"
                if event.get("quantity") is not None:
                    try:
                        event["quantity"] = int(event["quantity"])
                    except (ValueError, TypeError):
                        event["quantity"] = None

            # Validate deployments
            for dep in r["deployments"]:
                if dep.get("side") not in valid_sides:
                    dep["side"] = "Unknown"
                if dep.get("status") not in {"active", "pending", "withdrawn"}:
                    dep["status"] = "active"
                if dep.get("personnel_count") is not None:
                    try:
                        dep["personnel_count"] = int(dep["personnel_count"])
                    except (ValueError, TypeError):
                        dep["personnel_count"] = None

        return results

    except Exception as e:
        logger.error(f"Military data extraction failed: {e}")
        # Return empty results for each article
        return [
            {
                "id": art["id"],
                "headline": art.get("headline", ""),
                "events": [],
                "deployments": [],
            }
            for art in articles
        ]


def extract_single_military_event(headline: str, summary: str,
                                   latitude: float = None,
                                   longitude: float = None,
                                   location_name: str = None) -> dict:
    """
    Extract military data from a single article.

    Returns: dict with events[] and deployments[].
    """
    results = extract_military_data([{
        "id": 0,
        "headline": headline,
        "summary": summary,
        "latitude": latitude,
        "longitude": longitude,
        "location_name": location_name,
    }])

    if results:
        return results[0]
    return {"events": [], "deployments": []}
