"""
Portfolio Tab Callbacks — positions CRUD, P&L projection, summary.
"""

from datetime import date, datetime
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, State, no_update

from db.database import (
    get_session, Position, PnlProjection,
    add_position, close_position, get_open_positions,
)
from config import SCENARIOS


@callback(
    Output("port-add-feedback", "children"),
    Output("port-positions-table", "children", allow_duplicate=True),
    Input("port-add-btn", "n_clicks"),
    State("port-underlying", "value"),
    State("port-instrument-type", "value"),
    State("port-contract-month", "value"),
    State("port-strike", "value"),
    State("port-quantity", "value"),
    State("port-entry-price", "value"),
    prevent_initial_call=True,
)
def add_position_cb(n_clicks, underlying, instrument_type, contract_month,
                     strike, quantity, entry_price):
    if not n_clicks:
        return no_update, no_update

    if not all([underlying, instrument_type, contract_month, quantity, entry_price]):
        return dbc.Alert("Please fill all required fields.", color="warning"), no_update

    option_type = None
    if instrument_type in ("call", "put"):
        option_type = instrument_type.upper()
        instrument_type_db = "option"
    else:
        instrument_type_db = "future"

    try:
        pid = add_position(
            underlying=underlying,
            instrument_type=instrument_type_db,
            contract_month=contract_month,
            quantity=int(quantity),
            entry_price=float(entry_price),
            entry_date=date.today(),
            strike=float(strike) if strike else None,
            option_type=option_type,
        )
        feedback = dbc.Alert(f"Position #{pid} added.", color="success", duration=3000)
    except Exception as e:
        feedback = dbc.Alert(f"Error: {e}", color="danger")

    return feedback, _build_positions_table()


@callback(
    Output("port-positions-table", "children"),
    Output("port-pnl-chart", "figure"),
    Output("port-pnl-summary", "children"),
    Input("auto-refresh", "n_intervals"),
)
def update_portfolio(_n):
    positions_table = _build_positions_table()

    # ─── P&L Chart ───────────────────────────────────────────────────
    pnl_fig = go.Figure()
    pnl_fig.update_layout(
        template="oil_dark",
        title="P&L by Scenario",
        xaxis_title="Scenario",
        yaxis_title="P&L ($)",
        height=400,
    )

    session = get_session()
    try:
        # Get latest projections
        latest_date = session.query(PnlProjection.date).order_by(
            PnlProjection.date.desc()
        ).first()

        pnl_summary = html.P("No P&L projections yet. Run the P&L projector.",
                               className="text-muted")

        if latest_date:
            projections = session.query(PnlProjection).filter(
                PnlProjection.date == latest_date[0],
            ).all()

            if projections:
                from collections import defaultdict
                by_scenario = defaultdict(float)
                for p in projections:
                    by_scenario[p.scenario_name] += p.projected_pnl or 0

                names = list(by_scenario.keys())
                pnls = list(by_scenario.values())
                colors = ["#44CC44" if v > 0 else "#CC4444" for v in pnls]

                pnl_fig.add_trace(go.Bar(
                    x=names, y=pnls, marker_color=colors,
                    text=[f"${v:,.0f}" for v in pnls],
                    textposition="auto",
                ))

                # Summary
                positions = get_open_positions()
                total_invested = sum(
                    abs(p.entry_price * p.quantity) for p in positions
                )

                best = max(by_scenario.items(), key=lambda x: x[1])
                worst = min(by_scenario.items(), key=lambda x: x[1])

                pnl_summary = html.Div([
                    html.H6("Portfolio P&L Summary", className="text-info"),
                    html.P(f"Open Positions: {len(positions)}"),
                    html.P(f"Total Invested: ${total_invested:,.2f}"),
                    html.Hr(),
                    html.P([html.Strong("Best Case: "), f"{best[0]}: ${best[1]:,.0f}"]),
                    html.P([html.Strong("Worst Case: "), f"{worst[0]}: ${worst[1]:,.0f}"]),
                    html.Hr(),
                    dbc.Table(
                        [html.Thead(html.Tr([html.Th("Scenario"), html.Th("P&L")]))] +
                        [html.Tbody([
                            html.Tr([
                                html.Td(n),
                                html.Td(f"${v:,.0f}",
                                         style={"color": "#44CC44" if v > 0 else "#CC4444"}),
                            ]) for n, v in sorted(by_scenario.items(),
                                                   key=lambda x: -x[1])
                        ])],
                        bordered=True, hover=True, responsive=True, color="dark",
                    ),
                ])

        return positions_table, pnl_fig, pnl_summary

    finally:
        session.close()


def _build_positions_table():
    """Build the open positions HTML table."""
    positions = get_open_positions()

    if not positions:
        return html.P("No open positions.", className="text-muted")

    rows = []
    for p in positions:
        strike_str = f"${p.strike:.0f}" if p.strike else "—"
        opt_str = p.option_type or "—"
        rows.append(html.Tr([
            html.Td(str(p.id)),
            html.Td(p.underlying),
            html.Td(p.instrument_type),
            html.Td(p.contract_month),
            html.Td(strike_str),
            html.Td(opt_str),
            html.Td(str(p.quantity)),
            html.Td(f"${p.entry_price:.2f}"),
            html.Td(str(p.entry_date)),
        ]))

    return dbc.Table(
        [html.Thead(html.Tr([
            html.Th("ID"), html.Th("UL"), html.Th("Type"),
            html.Th("Month"), html.Th("Strike"), html.Th("Opt"),
            html.Th("Qty"), html.Th("Entry"), html.Th("Date"),
        ]))] + [html.Tbody(rows)],
        bordered=True, hover=True, responsive=True, color="dark",
    )
