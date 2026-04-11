"""
Trading Agent — AI-driven trade recommendation engine.

Uses Claude Sonnet 4.6 with tool-use to evaluate mispricing edges and
recommend optimal options structures (calls, spreads, strangles, ratios).
"""

import json
from datetime import date, timedelta
from loguru import logger

from config import SCENARIOS
from db.database import get_session, OptionsChain, FuturesCurve
from agents.llm_client import get_llm_client, extract_json
from analysis.options_analysis import black76_price, black76_greeks


TRADING_SYSTEM = """You are an expert oil options trader specializing in geopolitical tail risk strategies.

Given the AI-vs-market probability edges across 6 scenarios, recommend specific options trades.

## Available Structures:
- **Naked calls/puts**: Direct directional bets on specific scenarios
- **Call spreads**: Bull call spreads for defined-risk upside exposure
- **Put spreads**: Bear put spreads for downside exposure
- **Strangles/straddles**: Volatility bets
- **Ratio spreads**: Leveraged bets on tail scenarios with limited risk
- **Calendars**: Term structure plays

## Guidelines:
- Focus on scenarios with largest positive edge (AI prob > market prob)
- Prefer defined-risk structures (spreads over naked options)
- Target payoff ratio > 3:1 for tail risk trades
- Consider liquidity — prefer CL (WTI) for execution, BZ (Brent) for expression
- Account for position sizing — max 2-5% portfolio risk per trade
- Near-term expiries for high-conviction, far expiries for tail risk

## Output Format:
Return a JSON array of ranked trade recommendations:
[
  {
    "rank": 1,
    "underlying": "COIL",
    "structure": "call_spread",
    "legs": [
      {"strike": 120, "expiry": "2026-06", "type": "CALL", "side": "BUY"},
      {"strike": 150, "expiry": "2026-06", "type": "CALL", "side": "SELL"}
    ],
    "entry_cost": 2.50,
    "max_loss": 2.50,
    "max_profit": 27.50,
    "expected_value": 8.75,
    "payoff_ratio": 3.5,
    "target_scenario": "Major Disruption",
    "reasoning": "..."
  }
]"""


TRADING_TOOLS = [
    {
        "name": "get_scenario_edges",
        "description": "Get AI vs market probability edges for all 6 scenarios. Positive edge = underpriced by market.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_options_chain",
        "description": "Get available options chain for an underlying and expiry. Returns strikes, prices, IV, Greeks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "underlying": {"type": "string", "description": "CL or BZ"},
                "expiry": {"type": "string", "description": "Expiry date YYYY-MM-DD or YYYY-MM"},
            },
            "required": ["underlying"],
        },
    },
    {
        "name": "price_option",
        "description": "Price an option using Black-76 at a given scenario price level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "futures_price": {"type": "number", "description": "Scenario target futures price"},
                "strike": {"type": "number"},
                "expiry_days": {"type": "integer", "description": "Days to expiry"},
                "vol": {"type": "number", "description": "Implied vol (decimal)"},
                "option_type": {"type": "string", "enum": ["CALL", "PUT"]},
            },
            "required": ["futures_price", "strike", "expiry_days", "vol", "option_type"],
        },
    },
    {
        "name": "compute_trade_ev",
        "description": "Compute expected value of a trade given scenario probabilities and scenario prices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "legs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "strike": {"type": "number"},
                            "type": {"type": "string"},
                            "side": {"type": "string"},
                            "price": {"type": "number"},
                        },
                    },
                },
                "scenario_prices": {
                    "type": "object",
                    "description": "Map of scenario name to underlying price at that scenario",
                },
                "scenario_probs": {
                    "type": "object",
                    "description": "Map of scenario name to AI probability",
                },
            },
            "required": ["legs", "scenario_prices", "scenario_probs"],
        },
    },
]


def _build_trading_tool_handlers(target_date: date, edges: dict) -> dict:
    """Build tool handlers for the trading agent."""
    session = get_session()

    def get_scenario_edges(_input):
        return edges

    def get_options_chain(params):
        underlying = params.get("underlying", "COIL")
        expiry_str = params.get("expiry")

        query = session.query(OptionsChain).filter(
            OptionsChain.date == target_date,
            OptionsChain.underlying == underlying,
        )

        if expiry_str:
            if len(expiry_str) == 7:  # YYYY-MM
                query = query.filter(
                    OptionsChain.expiry_date >= f"{expiry_str}-01",
                    OptionsChain.expiry_date < f"{expiry_str}-31",
                )
            else:
                query = query.filter(OptionsChain.expiry_date == expiry_str)

        options = query.order_by(OptionsChain.expiry_date, OptionsChain.strike).all()

        return [
            {
                "strike": o.strike,
                "expiry": str(o.expiry_date),
                "type": o.option_type,
                "bid": o.bid,
                "ask": o.ask,
                "last": o.last_price,
                "iv": o.implied_vol,
                "delta": o.delta,
                "volume": o.volume,
                "oi": o.open_interest,
            }
            for o in options[:100]
        ]

    def price_option(params):
        F = params["futures_price"]
        K = params["strike"]
        T = params["expiry_days"] / 365.0
        vol = params["vol"]
        opt_type = params["option_type"]
        r = 0.05

        greeks = black76_greeks(F, K, T, r, vol, opt_type)
        return {
            "price": round(greeks["price"], 4),
            "delta": round(greeks["delta"], 4),
            "gamma": round(greeks["gamma"], 6),
            "vega": round(greeks["vega"], 4),
            "theta": round(greeks["theta"], 4),
        }

    def compute_trade_ev(params):
        legs = params["legs"]
        scenario_prices = params["scenario_prices"]
        scenario_probs = params["scenario_probs"]

        # Entry cost
        entry_cost = sum(
            leg["price"] * (1 if leg["side"] == "BUY" else -1)
            for leg in legs
        )

        # P&L per scenario
        pnl_by_scenario = {}
        for scenario, underlying_price in scenario_prices.items():
            pnl = -entry_cost  # Start with cost
            for leg in legs:
                K = leg["strike"]
                if leg["type"] == "CALL":
                    intrinsic = max(0, underlying_price - K)
                else:
                    intrinsic = max(0, K - underlying_price)

                if leg["side"] == "BUY":
                    pnl += intrinsic
                else:
                    pnl -= intrinsic

            pnl_by_scenario[scenario] = round(pnl, 2)

        # Expected value
        ev = sum(
            pnl_by_scenario.get(s, 0) * scenario_probs.get(s, 0)
            for s in scenario_probs
        )

        return {
            "entry_cost": round(entry_cost, 2),
            "pnl_by_scenario": pnl_by_scenario,
            "expected_value": round(ev, 2),
            "max_loss": round(min(pnl_by_scenario.values()), 2),
            "max_profit": round(max(pnl_by_scenario.values()), 2),
        }

    return {
        "get_scenario_edges": get_scenario_edges,
        "get_options_chain": get_options_chain,
        "price_option": price_option,
        "compute_trade_ev": compute_trade_ev,
    }


def run_trading_agent(target_date: date = None, edges: dict = None) -> list[dict]:
    """
    Run the AI trading agent to produce trade recommendations.

    Args:
        target_date: Date for analysis.
        edges: Pre-computed scenario edges (if None, will compute).

    Returns:
        List of ranked trade recommendation dicts.
    """
    if target_date is None:
        target_date = date.today()

    if edges is None:
        from analysis.mispricing import compute_scenario_edges
        edges = compute_scenario_edges(target_date)

    client = get_llm_client()
    handlers = _build_trading_tool_handlers(target_date, edges)

    # Summarize edges for user prompt
    edge_summary = []
    for name, data in sorted(edges.items(), key=lambda x: -x[1]["edge"]):
        edge_summary.append(
            f"- {name}: AI={data['ai_probability']:.1%}, "
            f"Market={data['market_probability']:.1%}, "
            f"Edge={data['edge']:+.1%}, "
            f"Brent ${data['brent_low']}-${data['brent_high']}"
        )

    user_prompt = f"""Today is {target_date}.

## Scenario Probability Edges (AI vs Market):
{chr(10).join(edge_summary)}

Use the tools to:
1. Get the detailed scenario edges
2. Look at available options chains (BZ and CL)
3. Price options at different scenario levels
4. Compute expected value for potential trades

Then recommend the top 3-5 trades ranked by expected value / risk ratio."""

    try:
        response = client.agent_loop(
            system=TRADING_SYSTEM,
            user_prompt=user_prompt,
            tools=TRADING_TOOLS,
            tool_handlers=handlers,
            max_iterations=10,
        )

        # Parse JSON array from response
        parsed = extract_json(response)
        if isinstance(parsed, list):
            trades = parsed
        else:
            trades = parsed.get("trades", parsed.get("recommendations", []))

        if not isinstance(trades, list):
            trades = [trades]

        logger.info(f"Trading agent recommended {len(trades)} trades")
        return trades

    except Exception as e:
        logger.error(f"Trading agent failed: {e}")
        return []
