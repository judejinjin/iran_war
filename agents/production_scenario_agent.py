"""
Production Scenario Agent — estimates production impact per scenario and recovery timelines.
"""

import json
from datetime import date
from loguru import logger

from db.database import (
    get_session, RegionSupplySummary, ScenarioProbability,
    CountryProduction, HormuzStatus, ChokepointStatus,
)
from agents.llm_client import get_llm_client

# Historical supply disruptions for context
HISTORICAL_DISRUPTIONS = [
    {"event": "Kuwait 1990 (Gulf War)", "offline_mbd": 5.0, "brent_spike": 40},
    {"event": "Libya 2011 (Civil War)", "offline_mbd": 1.5, "brent_spike": 125},
    {"event": "Iran Sanctions 2012", "offline_mbd": 1.0, "brent_spike": 110},
    {"event": "Saudi Abqaiq 2019", "offline_mbd": 5.7, "brent_spike": 72},
    {"event": "Russia-Ukraine 2022", "offline_mbd": 1.5, "brent_spike": 130},
]

# Scenario production impact templates
SCENARIO_IMPACTS = {
    "Super Spike": {
        "description": "Hormuz closed, multi-country production offline",
        "hormuz_blocked_mbd": 17.0,
        "iran_offline_pct": 1.0,
        "saudi_offline_pct": 0.15,
        "iraq_offline_pct": 0.30,
        "uae_offline_pct": 0.20,
        "recovery_days": 180,
    },
    "Major Disruption": {
        "description": "Significant Iranian production offline + partial Hormuz restriction",
        "hormuz_blocked_mbd": 5.0,
        "iran_offline_pct": 0.80,
        "saudi_offline_pct": 0.05,
        "iraq_offline_pct": 0.10,
        "uae_offline_pct": 0.05,
        "recovery_days": 90,
    },
    "Moderate Escalation": {
        "description": "Limited strikes, some production loss, Hormuz open but risky",
        "hormuz_blocked_mbd": 1.0,
        "iran_offline_pct": 0.40,
        "saudi_offline_pct": 0.0,
        "iraq_offline_pct": 0.05,
        "uae_offline_pct": 0.0,
        "recovery_days": 45,
    },
    "Current State": {
        "description": "Contained conflict, minimal supply impact",
        "hormuz_blocked_mbd": 0.0,
        "iran_offline_pct": 0.15,
        "saudi_offline_pct": 0.0,
        "iraq_offline_pct": 0.0,
        "uae_offline_pct": 0.0,
        "recovery_days": 14,
    },
    "De-escalation": {
        "description": "Ceasefire underway, shut-ins recovering",
        "hormuz_blocked_mbd": 0.0,
        "iran_offline_pct": 0.05,
        "saudi_offline_pct": 0.0,
        "iraq_offline_pct": 0.0,
        "uae_offline_pct": 0.0,
        "recovery_days": 7,
    },
    "Resolution": {
        "description": "War ends, Iranian supply returns, sanctions eased",
        "hormuz_blocked_mbd": 0.0,
        "iran_offline_pct": 0.0,
        "saudi_offline_pct": 0.0,
        "iraq_offline_pct": 0.0,
        "uae_offline_pct": 0.0,
        "recovery_days": 0,
    },
}

_BASELINES = {
    "IR": 3.2, "SA": 10.5, "IQ": 4.5, "AE": 3.2,
    "KW": 2.7, "QA": 1.8, "OM": 1.0, "BH": 0.2,
}


def compute_scenario_supply_impacts() -> list[dict]:
    """
    Compute estimated supply offline for each scenario.
    Returns list of dicts with scenario name, offline_mbd, and recovery_days.
    """
    results = []
    for name, params in SCENARIO_IMPACTS.items():
        offline = (
            _BASELINES["IR"] * params["iran_offline_pct"]
            + _BASELINES["SA"] * params["saudi_offline_pct"]
            + _BASELINES["IQ"] * params["iraq_offline_pct"]
            + _BASELINES["AE"] * params["uae_offline_pct"]
            + params["hormuz_blocked_mbd"]
        )
        results.append({
            "scenario": name,
            "total_offline_mbd": round(offline, 2),
            "hormuz_blocked_mbd": params["hormuz_blocked_mbd"],
            "production_offline_mbd": round(offline - params["hormuz_blocked_mbd"], 2),
            "recovery_days": params["recovery_days"],
            "description": params["description"],
        })
    return results


def get_current_vs_scenarios() -> dict:
    """
    Compare current actual offline vs scenario projections.
    Returns dict with current status and all scenario impacts.
    """
    session = get_session()
    try:
        rss = session.query(RegionSupplySummary).order_by(
            RegionSupplySummary.date.desc()
        ).first()

        current = {
            "date": str(rss.date) if rss else "N/A",
            "actual_offline_mbd": rss.total_offline_oil_mbd if rss else 0,
            "actual_pct_global": (rss.pct_global_supply_offline or 0) * 100 if rss else 0,
        }

        scenarios = compute_scenario_supply_impacts()
        return {"current": current, "scenarios": scenarios}

    finally:
        session.close()
