"""
Scenarios Tab Callbacks — probability bars, price range, history, reasoning, supply impact.
"""

from datetime import date, datetime
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output

from config import SCENARIOS
from db.database import get_session, ScenarioProbability


@callback(
    Output("scen-metrics-row", "children"),
    Output("scen-probabilities-chart", "figure"),
    Output("scen-price-range-chart", "figure"),
    Output("scen-history-chart", "figure"),
    Output("scen-supply-impact-chart", "figure"),
    Output("scen-recovery-chart", "figure"),
    Output("scen-reasoning", "children"),
    Input("scen-date-range", "start_date"),
    Input("scen-date-range", "end_date"),
    Input("auto-refresh", "n_intervals"),
)
def update_scenarios(start_date, end_date, _n):
    session = get_session()
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        # ─── Latest probabilities ────────────────────────────────────
        latest_date_row = session.query(ScenarioProbability.date).order_by(
            ScenarioProbability.date.desc()
        ).first()

        prob_fig = go.Figure()
        prob_fig.update_layout(
            template="oil_dark",
            title="Scenario Probabilities",
            xaxis_title="Scenario",
            yaxis_title="Probability",
            height=400,
        )

        price_fig = go.Figure()
        price_fig.update_layout(
            template="oil_dark",
            title="Expected Price Ranges by Scenario",
            xaxis_title="Scenario",
            yaxis_title="Brent Price ($/bbl)",
            height=400,
        )

        reasoning_content = html.P("No scenario data available. Run the scenario agent.",
                                    className="text-muted")
        metrics = []

        if latest_date_row:
            latest_probs = session.query(ScenarioProbability).filter(
                ScenarioProbability.date == latest_date_row[0],
            ).order_by(ScenarioProbability.brent_high.desc()).all()

            if latest_probs:
                names = [p.scenario_name for p in latest_probs]
                probs = [p.probability for p in latest_probs]
                colors = ["#FF4444", "#FF8800", "#FFCC00", "#44AA44", "#4488CC", "#8844CC"]

                prob_fig.add_trace(go.Bar(
                    x=names, y=probs,
                    marker_color=colors[:len(names)],
                    text=[f"{p:.0%}" for p in probs],
                    textposition="auto",
                ))

                # Price ranges
                for i, p in enumerate(latest_probs):
                    price_fig.add_trace(go.Bar(
                        name=p.scenario_name,
                        x=[p.scenario_name],
                        y=[(p.brent_high or 0) - (p.brent_low or 0)],
                        base=p.brent_low or 0,
                        marker_color=colors[i] if i < len(colors) else "#666",
                        text=f"${p.brent_low:.0f}-${p.brent_high:.0f}",
                        textposition="auto",
                        showlegend=False,
                    ))

                # Expected price
                exp_price = sum(
                    p.probability * ((p.brent_low or 0) + (p.brent_high or 0)) / 2
                    for p in latest_probs
                )
                metrics = [
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.H6("Expected Brent", className="text-muted"),
                        html.H4(f"${exp_price:.0f}"),
                    ])), width=2),
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.H6("Last Updated", className="text-muted"),
                        html.H4(str(latest_date_row[0])),
                    ])), width=2),
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.H6("Top Scenario", className="text-muted"),
                        html.H4(max(latest_probs, key=lambda p: p.probability).scenario_name),
                    ])), width=3),
                ]

                # Reasoning
                reasoning_items = []
                for p in latest_probs:
                    reasoning_items.append(html.Div([
                        html.H6(f"{p.scenario_name} ({p.probability:.0%})", className="text-info"),
                        html.P(p.reasoning or "No reasoning provided.",
                                style={"fontSize": "0.9rem"}),
                        html.Hr(),
                    ]))
                reasoning_content = html.Div(reasoning_items)

        # ─── Probability History ─────────────────────────────────────
        history_fig = go.Figure()
        history_fig.update_layout(
            template="oil_dark",
            title="Scenario Probability Over Time",
            xaxis_title="Date",
            yaxis_title="Probability",
            height=400,
        )

        all_probs = session.query(ScenarioProbability).filter(
            ScenarioProbability.date >= start_date,
            ScenarioProbability.date <= end_date,
        ).order_by(ScenarioProbability.date).all()

        if all_probs:
            from collections import defaultdict
            by_scenario = defaultdict(list)
            for p in all_probs:
                by_scenario[p.scenario_name].append(p)

            for scenario_name, pts in by_scenario.items():
                history_fig.add_trace(go.Scatter(
                    x=[p.date for p in pts],
                    y=[p.probability for p in pts],
                    mode="lines+markers",
                    name=scenario_name,
                ))

        # ─── Supply Impact by Scenario ───────────────────────────────
        from agents.production_scenario_agent import compute_scenario_supply_impacts
        supply_fig = go.Figure()
        supply_fig.update_layout(
            template="oil_dark",
            title="Supply Offline by Scenario (mbd)",
            xaxis_title="Scenario",
            yaxis_title="Oil Offline (mbd)",
            height=400,
            barmode="stack",
        )

        recovery_fig = go.Figure()
        recovery_fig.update_layout(
            template="oil_dark",
            title="Recovery Timeline by Scenario",
            xaxis_title="Scenario",
            yaxis_title="Days to Recover",
            height=400,
        )

        scenario_impacts = compute_scenario_supply_impacts()
        if scenario_impacts:
            names = [s["scenario"] for s in scenario_impacts]
            prod_off = [s["production_offline_mbd"] for s in scenario_impacts]
            hormuz_off = [s["hormuz_blocked_mbd"] for s in scenario_impacts]
            recovery_days = [s["recovery_days"] for s in scenario_impacts]

            supply_fig.add_trace(go.Bar(
                x=names, y=prod_off, name="Production Offline",
                marker_color="#FF5252",
            ))
            supply_fig.add_trace(go.Bar(
                x=names, y=hormuz_off, name="Hormuz Blocked",
                marker_color="#FFD600",
            ))

            recovery_fig.add_trace(go.Bar(
                x=names, y=recovery_days,
                marker_color=["#FF4444", "#FF8800", "#FFCC00", "#44AA44", "#4488CC", "#8844CC"][:len(names)],
                text=[f"{d}d" for d in recovery_days],
                textposition="auto",
            ))

        return metrics, prob_fig, price_fig, history_fig, supply_fig, recovery_fig, reasoning_content

    finally:
        session.close()
