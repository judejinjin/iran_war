"""
Portfolio Tab Layout — positions, P&L projections, Greeks.
"""

import dash_bootstrap_components as dbc
from dash import html, dcc

layout = dbc.Container([
    # ─── Position Entry ──────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Add Position"),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.Label("Underlying"),
                            dcc.Dropdown(id="port-underlying",
                                         options=[{"label": "CL (WTI)", "value": "CL"},
                                                  {"label": "BZ (Brent)", "value": "BZ"}],
                                         value="CL", clearable=False, style={"color": "#000"}),
                        ], width=2),
                        dbc.Col([
                            html.Label("Type"),
                            dcc.Dropdown(id="port-instrument-type",
                                         options=[{"label": "Future", "value": "future"},
                                                  {"label": "Call", "value": "call"},
                                                  {"label": "Put", "value": "put"}],
                                         value="future", clearable=False, style={"color": "#000"}),
                        ], width=2),
                        dbc.Col([
                            html.Label("Contract Month"),
                            dbc.Input(id="port-contract-month", type="text",
                                      placeholder="2026-06", value="2026-06"),
                        ], width=2),
                        dbc.Col([
                            html.Label("Strike"),
                            dbc.Input(id="port-strike", type="number", placeholder="0"),
                        ], width=1),
                        dbc.Col([
                            html.Label("Qty"),
                            dbc.Input(id="port-quantity", type="number", value=1),
                        ], width=1),
                        dbc.Col([
                            html.Label("Entry Price"),
                            dbc.Input(id="port-entry-price", type="number", placeholder="$"),
                        ], width=2),
                        dbc.Col([
                            html.Label("\u00A0"),
                            html.Div(dbc.Button("Add", id="port-add-btn",
                                                color="success", className="w-100")),
                        ], width=2),
                    ]),
                    html.Div(id="port-add-feedback", className="mt-2"),
                ]),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Open Positions ──────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Open Positions"),
                dbc.CardBody(id="port-positions-table"),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── P&L Projection ─────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("P&L Projection by Scenario"),
                dbc.CardBody(dcc.Graph(id="port-pnl-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Aggregate P&L Summary"),
                dbc.CardBody(id="port-pnl-summary"),
            ]),
        ], width=6),
    ]),
], fluid=True)
