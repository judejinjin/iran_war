"""
Analysis Tab Layout — mispricing edges, trade recommendations, payoff diagrams.
"""

import dash_bootstrap_components as dbc
from dash import html, dcc

layout = dbc.Container([
    # ─── Mispricing Analysis ─────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Scenario Mispricing (AI vs Market)"),
                dbc.CardBody(dcc.Graph(id="analysis-mispricing-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Edge by Scenario"),
                dbc.CardBody(dcc.Graph(id="analysis-edge-chart")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Trade Recommendations ───────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("AI Trade Recommendations"),
                dbc.CardBody(id="analysis-trades-table"),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Payoff Diagram ──────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Selected Trade Payoff"),
                dbc.CardBody(dcc.Graph(id="analysis-payoff-chart")),
            ]),
        ], width=12),
    ]),
], fluid=True)
