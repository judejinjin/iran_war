"""
Scenario Agent — AI-driven scenario probability assessment.

Uses Claude Sonnet 4.6 with tool-use to ingest geopolitical summaries,
military escalation, futures curves, and options skew, then outputs
probability distribution across 6 scenarios.
"""

import json
from datetime import date, timedelta
from loguru import logger

from config import SCENARIOS
from db.database import (
    get_session, DailySummary, MilitaryDailySummary,
    FuturesCurve, VolSurface, ScenarioProbability,
)
from agents.llm_client import get_llm_client


SCENARIO_SYSTEM = """You are an elite geopolitical risk analyst and oil market strategist. 
Your task: assess the probability distribution across 6 oil price scenarios given current intelligence.

## Scenarios (from extreme disruption to resolution):
1. **Super Spike** (Brent $180-250): Hormuz closed, multi-country production offline, SPR depleted
2. **Major Disruption** (Brent $130-180): Significant Iranian production offline + partial Hormuz restriction  
3. **Moderate Escalation** (Brent $100-130): Limited strikes, some production loss, Hormuz open but risky
4. **Current State** (Brent $80-100): Contained conflict, minimal supply impact
5. **De-escalation** (Brent $65-80): Ceasefire/negotiations, sanctions relief potential
6. **Resolution** (Brent $55-65): War ends, Iranian supply returns, OPEC+ unwinds cuts

## Rules:
- Probabilities MUST sum to exactly 1.00 (±0.01 tolerance)
- Each probability change from yesterday must be justified
- Military escalation score is a KEY input (1-10 scale)
- Supply impact estimates inform scenario selection
- Consider market positioning (skew, curve shape) as sentiment indicator
- Be specific about what events drove probability shifts

Use the provided tools to gather today's intelligence, then produce your assessment.

## Output Format:
Return a JSON object:
{
    "scenarios": {
        "Super Spike": {"probability": 0.XX, "reasoning": "..."},
        "Major Disruption": {"probability": 0.XX, "reasoning": "..."},
        "Moderate Escalation": {"probability": 0.XX, "reasoning": "..."},
        "Current State": {"probability": 0.XX, "reasoning": "..."},
        "De-escalation": {"probability": 0.XX, "reasoning": "..."},
        "Resolution": {"probability": 0.XX, "reasoning": "..."}
    },
    "overall_assessment": "2-3 sentence market outlook",
    "key_drivers": ["driver1", "driver2", "driver3"]
}"""


# ─── Tool Definitions for Agent ──────────────────────────────────────────────

SCENARIO_TOOLS = [
    {
        "name": "get_latest_summaries",
        "description": "Get today's geopolitical daily summaries across all 5 categories (geopolitical_development, military_operations, infrastructure_damage, production_shutin, shipment_disruption). Returns category, severity, supply impact, and summary text.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_military_summary",
        "description": "Get today's military daily summary for both sides (Iran and Opposing forces). Returns losses, deployments, escalation scores.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_latest_futures",
        "description": "Get current CL (WTI) and BZ (Brent) futures prices, term structure shape (contango/backwardation), and key spreads.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_latest_vol_metrics",
        "description": "Get current volatility surface metrics: ATM vol, 25-delta skew, 25-delta butterfly for CL and BZ.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_previous_probabilities",
        "description": "Get yesterday's scenario probability distribution for continuity analysis.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def _build_tool_handlers(target_date: date) -> dict:
    """Build tool handler functions with DB access for the given date."""
    session = get_session()

    def get_latest_summaries(_input):
        summaries = session.query(DailySummary).filter(
            DailySummary.date == target_date
        ).all()
        if not summaries:
            # Try previous day
            summaries = session.query(DailySummary).filter(
                DailySummary.date == target_date - timedelta(days=1)
            ).all()
        return [
            {
                "category": s.category,
                "summary": s.summary_text,
                "severity_avg": s.severity_avg,
                "supply_impact_mbd": s.total_supply_impact_mbd,
            }
            for s in summaries
        ] if summaries else [{"message": "No summaries available for today"}]

    def get_military_summary(_input):
        mil_summaries = session.query(MilitaryDailySummary).filter(
            MilitaryDailySummary.date == target_date
        ).all()
        if not mil_summaries:
            mil_summaries = session.query(MilitaryDailySummary).filter(
                MilitaryDailySummary.date == target_date - timedelta(days=1)
            ).all()
        return [
            {
                "side": m.side,
                "personnel_losses": m.total_personnel_losses,
                "aircraft_losses": m.total_aircraft_losses,
                "naval_losses": m.total_naval_losses,
                "cumulative_personnel": m.cumulative_personnel_losses,
                "active_deployed": m.active_personnel_deployed,
                "escalation_score": m.escalation_score,
                "summary": m.summary_text,
            }
            for m in mil_summaries
        ] if mil_summaries else [{"message": "No military summary available"}]

    def get_latest_futures(_input):
        # Get latest futures curve data
        curves = session.query(FuturesCurve).filter(
            FuturesCurve.date == target_date,
        ).order_by(FuturesCurve.symbol, FuturesCurve.contract_month).all()

        if not curves:
            curves = session.query(FuturesCurve).filter(
                FuturesCurve.date >= target_date - timedelta(days=5),
            ).order_by(
                FuturesCurve.date.desc(), FuturesCurve.symbol, FuturesCurve.contract_month
            ).limit(48).all()

        result = {}
        for c in curves:
            sym = c.symbol
            if sym not in result:
                result[sym] = []
            result[sym].append({
                "month": c.contract_month,
                "price": c.settlement_price,
                "volume": c.volume,
            })

        # Determine curve shape
        for sym, data in result.items():
            if len(data) >= 2:
                front = data[0]["price"] or 0
                back = data[-1]["price"] or 0
                result[sym + "_shape"] = "backwardation" if front > back else "contango"
                result[sym + "_front"] = front

        return result if result else {"message": "No futures data available"}

    def get_latest_vol_metrics(_input):
        vols = session.query(VolSurface).filter(
            VolSurface.date == target_date
        ).all()
        if not vols:
            vols = session.query(VolSurface).filter(
                VolSurface.date >= target_date - timedelta(days=5)
            ).order_by(VolSurface.date.desc()).limit(12).all()

        return [
            {
                "underlying": v.underlying,
                "expiry": str(v.expiry_date),
                "atm_vol": v.atm_vol,
                "skew_25d": v.skew_25d,
                "butterfly_25d": v.smile_25d,
            }
            for v in vols
        ] if vols else [{"message": "No vol surface data available"}]

    def get_previous_probabilities(_input):
        prev = session.query(ScenarioProbability).filter(
            ScenarioProbability.date == target_date - timedelta(days=1)
        ).all()
        if not prev:
            prev = session.query(ScenarioProbability).filter(
                ScenarioProbability.date < target_date
            ).order_by(ScenarioProbability.date.desc()).limit(6).all()

        return [
            {
                "scenario": p.scenario_name,
                "probability": p.probability,
                "reasoning": p.reasoning,
            }
            for p in prev
        ] if prev else [{"message": "No previous probabilities — this is the first assessment"}]

    return {
        "get_latest_summaries": get_latest_summaries,
        "get_military_summary": get_military_summary,
        "get_latest_futures": get_latest_futures,
        "get_latest_vol_metrics": get_latest_vol_metrics,
        "get_previous_probabilities": get_previous_probabilities,
    }


def run_scenario_assessment(target_date: date = None) -> dict:
    """
    Run the full scenario probability assessment via Claude agent.

    The agent will:
    1. Call tools to gather today's intelligence
    2. Analyze geopolitical, military, market data
    3. Produce probability distribution across 6 scenarios

    Returns: dict with scenario probabilities and reasoning.
    """
    if target_date is None:
        target_date = date.today()

    client = get_llm_client()
    handlers = _build_tool_handlers(target_date)

    user_prompt = f"""Today is {target_date}. 

Please assess the current probability distribution across all 6 oil price scenarios.

Start by gathering intelligence using the available tools:
1. Get today's geopolitical summaries
2. Get military situation summary 
3. Get current futures prices and curve shape
4. Get volatility metrics
5. Get yesterday's probabilities for comparison

Then produce your scenario probability assessment as JSON."""

    try:
        response = client.agent_loop(
            system=SCENARIO_SYSTEM,
            user_prompt=user_prompt,
            tools=SCENARIO_TOOLS,
            tool_handlers=handlers,
            max_iterations=8,
        )

        # Parse JSON from response
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

        # Find JSON in response
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            text = text[json_start:json_end]

        result = json.loads(text)
        return result

    except Exception as e:
        logger.error(f"Scenario assessment failed: {e}")
        # Return equal probabilities as fallback
        n = len(SCENARIOS)
        return {
            "scenarios": {
                s["name"]: {
                    "probability": 1.0 / n,
                    "reasoning": "Assessment failed — using equal probabilities",
                }
                for s in SCENARIOS
            },
            "overall_assessment": f"Assessment failed: {e}",
            "key_drivers": [],
        }
