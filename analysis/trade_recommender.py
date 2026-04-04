"""
Trade Recommender — Orchestrates daily mispricing analysis + trading agent.

Runs after scenario update: computes edges, calls trading agent,
stores results in agent_analyses table.
"""

import json
from datetime import date, datetime
from loguru import logger

from db.database import get_session, AgentAnalysis
from analysis.mispricing import compute_scenario_edges
from agents.trading_agent import run_trading_agent


def run_trade_analysis(target_date: date = None) -> dict:
    """
    Full daily trade recommendation pipeline:
    1. Compute scenario edges (AI vs market)
    2. Run trading agent for trade recommendations
    3. Store mispricing analysis in agent_analyses
    4. Store trade recommendations in agent_analyses

    Returns: dict with edges and trades.
    """
    if target_date is None:
        target_date = date.today()

    # Step 1: Compute edges
    logger.info(f"Computing scenario edges for {target_date}")
    edges = compute_scenario_edges(target_date)

    # Step 2: Run trading agent
    logger.info(f"Running trading agent for {target_date}")
    trades = run_trading_agent(target_date, edges)

    # Step 3 & 4: Store in DB
    session = get_session()
    try:
        # Store mispricing analysis
        edge_summary = []
        for name, data in sorted(edges.items(), key=lambda x: -abs(x[1]["edge"])):
            direction = "UNDERPRICED" if data["edge"] > 0.02 else "OVERPRICED" if data["edge"] < -0.02 else "fairly priced"
            edge_summary.append(f"{name}: {direction} (edge={data['edge']:+.1%})")

        mispricing_record = session.query(AgentAnalysis).filter(
            AgentAnalysis.date == target_date,
            AgentAnalysis.analysis_type == "mispricing",
        ).first()

        mispricing_data = {
            "date": target_date,
            "analysis_type": "mispricing",
            "summary": "; ".join(edge_summary),
            "detailed_analysis": json.dumps(edges, default=str),
            "confidence": max(abs(d["edge"]) for d in edges.values()) if edges else 0,
        }

        if mispricing_record:
            for k, v in mispricing_data.items():
                setattr(mispricing_record, k, v)
        else:
            session.add(AgentAnalysis(**mispricing_data))

        # Store trade recommendations
        trade_record = session.query(AgentAnalysis).filter(
            AgentAnalysis.date == target_date,
            AgentAnalysis.analysis_type == "trade_recommendation",
        ).first()

        trade_summary = f"{len(trades)} trades recommended" if trades else "No trades recommended"
        trade_data = {
            "date": target_date,
            "analysis_type": "trade_recommendation",
            "summary": trade_summary,
            "detailed_analysis": json.dumps(trades, default=str) if trades else "[]",
            "recommended_trades": json.dumps(trades, default=str) if trades else "[]",
            "confidence": trades[0].get("expected_value", 0) if trades else 0,
        }

        if trade_record:
            for k, v in trade_data.items():
                setattr(trade_record, k, v)
        else:
            session.add(AgentAnalysis(**trade_data))

        session.commit()
        logger.info(f"Stored mispricing analysis and {len(trades)} trade recommendations")

        return {"edges": edges, "trades": trades}

    except Exception as e:
        session.rollback()
        logger.error(f"Trade analysis storage failed: {e}")
        raise
    finally:
        session.close()
