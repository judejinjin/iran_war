"""
Payoff Chart Component — compute option strategy payoff at expiry.
"""

import numpy as np


def compute_payoff(trade: dict) -> tuple[list, list]:
    """
    Compute payoff diagram for a trade structure at expiry.

    Args:
        trade: dict with keys: legs (list of leg dicts), entry_cost.
               Each leg has: strike, type (CALL/PUT), side (BUY/SELL).

    Returns:
        (prices, pnls) — lists of underlying prices and corresponding P&L values.
    """
    legs = trade.get("legs", [])
    entry_cost = trade.get("entry_cost", 0)

    if not legs:
        return [], []

    # Determine price range from strikes
    strikes = [leg.get("strike", 0) for leg in legs if leg.get("strike")]
    if not strikes:
        return [], []

    min_strike = min(strikes)
    max_strike = max(strikes)
    margin = max(30, (max_strike - min_strike) * 0.5)

    prices = np.linspace(max(0, min_strike - margin), max_strike + margin, 200).tolist()
    pnls = [0.0] * len(prices)

    for leg in legs:
        strike = leg.get("strike", 0)
        opt_type = leg.get("type", "CALL").upper()
        side = leg.get("side", "BUY").upper()
        multiplier = 1 if side == "BUY" else -1

        for i, price in enumerate(prices):
            if opt_type == "CALL":
                intrinsic = max(0, price - strike)
            else:  # PUT
                intrinsic = max(0, strike - price)
            pnls[i] += multiplier * intrinsic

    # Subtract entry cost
    pnls = [p - entry_cost for p in pnls]

    return prices, pnls
