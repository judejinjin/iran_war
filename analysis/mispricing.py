"""
Mispricing Analysis — AI probability vs market-implied probability comparison.

Computes edge per scenario by comparing AI-assessed probabilities with
Breeden-Litzenberger market-implied distribution from options.
"""

import numpy as np
from datetime import date
from loguru import logger

from config import SCENARIOS
from db.database import get_session, OptionsChain, FuturesCurve
from analysis.options_analysis import market_implied_scenario_probs
from analysis.scenarios import get_latest_probabilities


def get_market_implied_probs(underlying: str = "BZ",
                              target_date: date = None) -> dict[str, float]:
    """
    Extract market-implied scenario probabilities from options chain
    using Breeden-Litzenberger.

    Uses the front-month options chain for the underlying.

    Returns: dict mapping scenario name → market-implied probability.
    """
    if target_date is None:
        target_date = date.today()

    session = get_session()
    try:
        # Get front-month futures price
        futures = session.query(FuturesCurve).filter(
            FuturesCurve.date == target_date,
            FuturesCurve.symbol == underlying,
        ).order_by(FuturesCurve.contract_month).first()

        if not futures or not futures.settlement_price:
            logger.warning(f"No futures price for {underlying} on {target_date}")
            return {s["name"]: 1.0 / len(SCENARIOS) for s in SCENARIOS}

        F = futures.settlement_price

        # Get call options for nearest expiry
        calls = session.query(OptionsChain).filter(
            OptionsChain.date == target_date,
            OptionsChain.underlying == underlying,
            OptionsChain.option_type == "CALL",
        ).order_by(OptionsChain.expiry_date, OptionsChain.strike).all()

        if not calls:
            logger.warning(f"No options data for {underlying} on {target_date}")
            return {s["name"]: 1.0 / len(SCENARIOS) for s in SCENARIOS}

        # Use first available expiry
        first_expiry = calls[0].expiry_date
        expiry_calls = [c for c in calls if c.expiry_date == first_expiry]

        # Get mid prices
        strikes = np.array([c.strike for c in expiry_calls])
        prices = np.array([
            (c.bid + c.ask) / 2 if c.bid and c.ask else c.last_price or 0
            for c in expiry_calls
        ])

        # Filter out zero prices
        valid = prices > 0
        strikes = strikes[valid]
        prices = prices[valid]

        if len(strikes) < 5:
            logger.warning("Insufficient options data for Breeden-Litzenberger")
            return {s["name"]: 1.0 / len(SCENARIOS) for s in SCENARIOS}

        T = max(1, (first_expiry - target_date).days) / 365.0

        return market_implied_scenario_probs(strikes, prices, F, T, SCENARIOS)

    finally:
        session.close()


def compute_scenario_edges(target_date: date = None) -> dict:
    """
    Compute edge for each scenario: AI_probability - market_implied_probability.
    Positive edge = scenario is underpriced by the market.

    Returns: dict with per-scenario data including AI prob, market prob, and edge.
    """
    if target_date is None:
        target_date = date.today()

    ai_probs = get_latest_probabilities(target_date)
    market_probs = get_market_implied_probs("BZ", target_date)

    edges = {}
    for scenario in SCENARIOS:
        name = scenario["name"]
        ai_p = ai_probs.get(name, {}).get("probability", 1.0 / len(SCENARIOS))
        mkt_p = market_probs.get(name, 1.0 / len(SCENARIOS))
        edge = ai_p - mkt_p

        edges[name] = {
            "ai_probability": ai_p,
            "market_probability": mkt_p,
            "edge": edge,
            "brent_low": scenario["brent_low"],
            "brent_high": scenario["brent_high"],
            "brent_mid": (scenario["brent_low"] + scenario["brent_high"]) / 2,
            "description": scenario["description"],
        }

    logger.info("Scenario edges computed:")
    for name, data in sorted(edges.items(), key=lambda x: -abs(x[1]["edge"])):
        direction = "UNDERPRICED" if data["edge"] > 0.02 else "OVERPRICED" if data["edge"] < -0.02 else "fair"
        logger.debug(f"  {name}: AI={data['ai_probability']:.1%} "
                     f"Mkt={data['market_probability']:.1%} "
                     f"Edge={data['edge']:+.1%} ({direction})")

    return edges
