"""
Scenario Analysis — Probability updater and storage.

Calls the scenario agent, validates output, stores in scenario_probabilities table.
"""

import json
from datetime import date, datetime
from loguru import logger

from config import SCENARIOS
from db.database import get_session, ScenarioProbability
from agents.scenario_agent import run_scenario_assessment


def update_scenario_probabilities(target_date: date = None) -> int:
    """
    Run scenario agent and store validated probabilities in DB.

    Returns: number of scenario rows stored (should be 6).
    """
    if target_date is None:
        target_date = date.today()

    # Run the AI assessment
    result = run_scenario_assessment(target_date)

    scenarios_data = result.get("scenarios", {})
    if not scenarios_data:
        logger.error("Scenario agent returned no scenario data")
        return 0

    # Validate probabilities sum to ~1.0
    probs = {name: data.get("probability", 0) for name, data in scenarios_data.items()}
    total = sum(probs.values())

    if abs(total - 1.0) > 0.05:
        logger.warning(f"Probabilities sum to {total:.3f}, normalizing")
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}

    # Store in DB
    session = get_session()
    try:
        stored = 0
        for scenario in SCENARIOS:
            name = scenario["name"]
            prob = probs.get(name, 0)
            reasoning = scenarios_data.get(name, {}).get("reasoning", "")

            existing = session.query(ScenarioProbability).filter(
                ScenarioProbability.date == target_date,
                ScenarioProbability.scenario_name == name,
            ).first()

            if existing:
                existing.probability = prob
                existing.reasoning = reasoning
            else:
                session.add(ScenarioProbability(
                    date=target_date,
                    scenario_name=name,
                    probability=prob,
                    brent_low=scenario["brent_low"],
                    brent_high=scenario["brent_high"],
                    reasoning=reasoning,
                ))

            stored += 1

        session.commit()
        logger.info(f"Stored {stored} scenario probabilities for {target_date}")

        # Log summary
        for name, prob in sorted(probs.items(), key=lambda x: -x[1]):
            logger.debug(f"  {name}: {prob:.1%}")

        return stored

    except Exception as e:
        session.rollback()
        logger.error(f"Scenario probability storage failed: {e}")
        raise
    finally:
        session.close()


def get_latest_probabilities(target_date: date = None) -> dict:
    """
    Get the latest scenario probabilities from DB.

    Returns: dict mapping scenario_name → {probability, reasoning, brent_low, brent_high}.
    """
    session = get_session()
    try:
        if target_date is None:
            target_date = date.today()

        rows = session.query(ScenarioProbability).filter(
            ScenarioProbability.date == target_date
        ).all()

        if not rows:
            # Try most recent available
            latest_date = session.query(ScenarioProbability.date).order_by(
                ScenarioProbability.date.desc()
            ).first()
            if latest_date:
                rows = session.query(ScenarioProbability).filter(
                    ScenarioProbability.date == latest_date[0]
                ).all()

        return {
            r.scenario_name: {
                "probability": r.probability,
                "reasoning": r.reasoning,
                "brent_low": r.brent_low,
                "brent_high": r.brent_high,
                "date": str(r.date),
            }
            for r in rows
        }

    finally:
        session.close()


def compute_expected_price(probs: dict = None) -> dict:
    """
    Compute probability-weighted expected Brent price.

    Returns: dict with expected_brent, expected_low, expected_high.
    """
    if probs is None:
        probs = get_latest_probabilities()

    expected_low = 0.0
    expected_high = 0.0

    for name, data in probs.items():
        p = data.get("probability", 0)
        expected_low += p * data.get("brent_low", 0)
        expected_high += p * data.get("brent_high", 0)

    expected_mid = (expected_low + expected_high) / 2.0

    return {
        "expected_brent": expected_mid,
        "expected_low": expected_low,
        "expected_high": expected_high,
    }
