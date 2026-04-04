"""
P&L Projector — Scenario-based P&L projection for portfolio positions.

For each open position × each scenario: reprice at scenario target price,
compute P&L, store in pnl_projections table.
"""

from datetime import date, datetime
from loguru import logger

from config import SCENARIOS
from db.database import get_session, Position, PnlProjection, FuturesCurve
from analysis.options_analysis import black76_price
from analysis.scenarios import get_latest_probabilities


def project_position_pnl(
    position: Position,
    scenario_name: str,
    target_price: float,
    current_price: float,
    vol_adjustment: float = 0.0,
    r: float = 0.05,
    days_to_expiry: int = 90,
) -> float:
    """
    Project P&L for a single position under a given scenario.

    For futures: simple price difference × quantity × multiplier.
    For options: reprice at scenario target using Black-76.

    Returns: projected P&L in dollars.
    """
    multiplier = 1000  # Standard crude oil contract = 1000 barrels

    if position.instrument_type == "future":
        pnl = (target_price - position.entry_price) * position.quantity * multiplier
        return pnl

    elif position.instrument_type == "option":
        if not position.strike:
            return 0.0

        T = max(1, days_to_expiry) / 365.0

        # Estimate vol at target price — higher prices generally mean higher vol
        base_vol = 0.35
        if current_price > 0:
            price_ratio = target_price / current_price
            vol = base_vol + vol_adjustment
            # Vol tends to increase with price in oil during crisis
            if price_ratio > 1.2:
                vol *= 1.0 + (price_ratio - 1.2) * 0.5
        else:
            vol = base_vol

        # Price option at scenario target
        projected_price = black76_price(
            F=target_price,
            K=position.strike,
            T=T,
            r=r,
            sigma=vol,
            option_type=position.option_type or "CALL",
        )

        # P&L = (projected price - entry price) × quantity × multiplier
        pnl = (projected_price - position.entry_price) * position.quantity * multiplier
        return pnl

    return 0.0


def project_all_positions(target_date: date = None) -> dict:
    """
    Project P&L for all open positions across all 6 scenarios.
    Stores results in pnl_projections table.

    Returns: dict with per-position and aggregate results.
    """
    if target_date is None:
        target_date = date.today()

    session = get_session()
    try:
        positions = session.query(Position).filter(Position.is_open == True).all()

        if not positions:
            logger.info("No open positions to project")
            return {"positions": [], "aggregate": {}}

        # Get current prices
        current_prices = {}
        for symbol in ["CL", "BZ"]:
            latest = session.query(FuturesCurve).filter(
                FuturesCurve.symbol == symbol,
                FuturesCurve.date <= target_date,
            ).order_by(
                FuturesCurve.date.desc(), FuturesCurve.contract_month
            ).first()
            if latest and latest.settlement_price:
                current_prices[symbol] = latest.settlement_price

        # Get scenario probabilities for expected P&L
        probs = get_latest_probabilities(target_date)

        # Clear existing projections for today
        session.query(PnlProjection).filter(
            PnlProjection.date == target_date
        ).delete()

        position_results = []
        aggregate = {s["name"]: 0.0 for s in SCENARIOS}

        for pos in positions:
            underlying = pos.underlying
            current_price = current_prices.get(underlying, 80.0)

            # Days to expiry estimate
            if pos.contract_month:
                try:
                    exp_year = int(pos.contract_month[:4])
                    exp_month = int(pos.contract_month[5:7])
                    exp_date = date(exp_year, exp_month, 15)
                    days_to_expiry = max(1, (exp_date - target_date).days)
                except (ValueError, IndexError):
                    days_to_expiry = 90
            else:
                days_to_expiry = 90

            pos_result = {"position_id": pos.id, "underlying": underlying, "scenarios": {}}

            for scenario in SCENARIOS:
                scenario_price = (scenario["brent_low"] + scenario["brent_high"]) / 2.0

                # Adjust for WTI (~$5 discount to Brent typically)
                if underlying == "CL":
                    scenario_price -= 5.0

                pnl = project_position_pnl(
                    position=pos,
                    scenario_name=scenario["name"],
                    target_price=scenario_price,
                    current_price=current_price,
                    days_to_expiry=days_to_expiry,
                )

                # Store projection
                session.add(PnlProjection(
                    date=target_date,
                    position_id=pos.id,
                    scenario_name=scenario["name"],
                    projected_underlying_price=scenario_price,
                    projected_option_price=None,
                    projected_pnl=pnl,
                ))

                pos_result["scenarios"][scenario["name"]] = {
                    "projected_price": scenario_price,
                    "projected_pnl": pnl,
                }
                aggregate[scenario["name"]] += pnl

            position_results.append(pos_result)

        # Compute expected P&L
        expected_pnl = 0.0
        for scenario_name, total_pnl in aggregate.items():
            prob = probs.get(scenario_name, {}).get("probability", 1.0 / len(SCENARIOS))
            expected_pnl += total_pnl * prob

        session.commit()
        logger.info(
            f"Projected P&L for {len(positions)} positions across {len(SCENARIOS)} scenarios. "
            f"Expected P&L: ${expected_pnl:,.0f}"
        )

        return {
            "positions": position_results,
            "aggregate": aggregate,
            "expected_pnl": expected_pnl,
            "date": str(target_date),
        }

    except Exception as e:
        session.rollback()
        logger.error(f"P&L projection failed: {e}")
        raise
    finally:
        session.close()


def get_aggregate_pnl(target_date: date = None) -> dict:
    """
    Get aggregate P&L from stored projections.

    Returns: dict with per-scenario totals and expected P&L.
    """
    if target_date is None:
        target_date = date.today()

    session = get_session()
    try:
        projections = session.query(PnlProjection).filter(
            PnlProjection.date == target_date
        ).all()

        if not projections:
            return {"aggregate": {}, "expected_pnl": 0}

        aggregate = {}
        for proj in projections:
            if proj.scenario_name not in aggregate:
                aggregate[proj.scenario_name] = 0.0
            aggregate[proj.scenario_name] += proj.projected_pnl or 0

        probs = get_latest_probabilities(target_date)
        expected_pnl = sum(
            total * probs.get(name, {}).get("probability", 1.0 / len(SCENARIOS))
            for name, total in aggregate.items()
        )

        return {"aggregate": aggregate, "expected_pnl": expected_pnl}

    finally:
        session.close()
