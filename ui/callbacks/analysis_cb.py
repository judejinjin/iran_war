"""
Analysis Tab Callbacks — mispricing, edge, trade recommendations, payoff.
"""

from datetime import date
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output

from db.database import get_session, AgentAnalysis


@callback(
    Output("analysis-mispricing-chart", "figure"),
    Output("analysis-edge-chart", "figure"),
    Output("analysis-trades-table", "children"),
    Output("analysis-payoff-chart", "figure"),
    Input("auto-refresh", "n_intervals"),
)
def update_analysis(_n):
    session = get_session()
    try:
        # ─── Mispricing Chart ────────────────────────────────────────
        mispricing_fig = go.Figure()
        mispricing_fig.update_layout(
            template="oil_dark",
            title="AI vs Market-Implied Probabilities",
            xaxis_title="Scenario",
            yaxis_title="Probability",
            height=400,
        )

        # ─── Edge Chart ──────────────────────────────────────────────
        edge_fig = go.Figure()
        edge_fig.update_layout(
            template="oil_dark",
            title="Mispricing Edge by Scenario",
            xaxis_title="Scenario",
            yaxis_title="Edge (AI - Market)",
            height=400,
        )

        # Try to load latest mispricing analysis
        latest = session.query(AgentAnalysis).filter(
            AgentAnalysis.analysis_type == "mispricing",
        ).order_by(AgentAnalysis.date.desc()).first()

        if latest and latest.detailed_analysis:
            try:
                import json
                data = json.loads(latest.detailed_analysis)
                names = list(data.keys())
                ai_probs = [data[n].get("ai_probability", 0) for n in names]
                mkt_probs = [data[n].get("market_probability", 0) for n in names]
                edges = [data[n].get("edge", 0) for n in names]

                mispricing_fig.add_trace(go.Bar(name="AI Probability", x=names, y=ai_probs))
                mispricing_fig.add_trace(go.Bar(name="Market-Implied", x=names, y=mkt_probs))
                mispricing_fig.update_layout(barmode="group")

                colors = ["#44CC44" if e > 0 else "#CC4444" for e in edges]
                edge_fig.add_trace(go.Bar(x=names, y=edges, marker_color=colors))
            except Exception:
                pass

        if not latest:
            for fig in [mispricing_fig, edge_fig]:
                fig.add_annotation(
                    text="No mispricing data. Run the scenario + mispricing agents.",
                    xref="paper", yref="paper", x=0.5, y=0.5,
                    showarrow=False, font=dict(size=14),
                )

        # ─── Trade Recommendations ───────────────────────────────────
        trade_analysis = session.query(AgentAnalysis).filter(
            AgentAnalysis.analysis_type == "trade_recommendation",
        ).order_by(AgentAnalysis.date.desc()).first()

        if trade_analysis and trade_analysis.detailed_analysis:
            try:
                import json
                trades = json.loads(trade_analysis.detailed_analysis)
                if isinstance(trades, list) and trades:
                    rows = []
                    for t in trades:
                        rows.append(html.Tr([
                            html.Td(str(t.get("rank", ""))),
                            html.Td(t.get("underlying", "")),
                            html.Td(t.get("structure", "").replace("_", " ").title()),
                            html.Td(f"${t.get('entry_cost', 0):.2f}"),
                            html.Td(f"${t.get('max_profit', 0):.2f}"),
                            html.Td(f"{t.get('payoff_ratio', 0):.1f}x"),
                            html.Td(f"${t.get('expected_value', 0):.2f}"),
                            html.Td(t.get("target_scenario", "")),
                        ]))

                    trades_table = dbc.Table(
                        [html.Thead(html.Tr([
                            html.Th("#"), html.Th("UL"), html.Th("Structure"),
                            html.Th("Cost"), html.Th("Max Profit"),
                            html.Th("Payoff"), html.Th("EV"),
                            html.Th("Target"),
                        ]))] + [html.Tbody(rows)],
                        bordered=True, hover=True, responsive=True, color="dark",
                    )
                else:
                    trades_table = html.P("No trades recommended.", className="text-muted")
            except Exception:
                trades_table = html.P("Error parsing trade data.", className="text-muted")
        else:
            trades_table = html.P("No trade recommendations yet. Run the trading agent.",
                                   className="text-muted")

        # ─── Payoff Chart ────────────────────────────────────────────
        payoff_fig = go.Figure()
        payoff_fig.update_layout(
            template="oil_dark",
            title="Trade Payoff Diagram",
            xaxis_title="Underlying Price at Expiry",
            yaxis_title="P&L ($)",
            height=400,
        )

        if trade_analysis and trade_analysis.detailed_analysis:
            try:
                trades = json.loads(trade_analysis.detailed_analysis)
                if isinstance(trades, list) and trades:
                    from ui.components.payoff_chart import compute_payoff
                    top_trade = trades[0]
                    prices, pnls = compute_payoff(top_trade)
                    if prices and pnls:
                        payoff_fig.add_trace(go.Scatter(
                            x=prices, y=pnls, mode="lines",
                            name=top_trade.get("structure", "Trade"),
                            fill="tozeroy",
                        ))
                        payoff_fig.add_hline(y=0, line_dash="dash", line_color="gray")
            except Exception:
                pass

        return mispricing_fig, edge_fig, trades_table, payoff_fig

    finally:
        session.close()
