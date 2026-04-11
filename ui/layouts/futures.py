"""
Futures Tab Layout — curve charts, spread charts, key metrics.
"""

from datetime import date, timedelta
import dash_bootstrap_components as dbc
from dash import html, dcc

from config import DEFAULT_TIMELINE_DAYS

today = date.today()
default_start = today - timedelta(days=DEFAULT_TIMELINE_DAYS)

layout = dbc.Container([
    # ─── Controls ─────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("Date Range:", className="fw-bold"),
            dcc.DatePickerRange(
                id="futures-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
        dbc.Col([
            html.Label("Symbol:", className="fw-bold"),
            dbc.RadioItems(
                id="futures-symbol-toggle",
                options=[
                    {"label": "Both", "value": "BOTH"},
                    {"label": "WTI (CL)", "value": "CL"},
                    {"label": "Brent (COIL)", "value": "COIL"},
                ],
                value="BOTH",
                inline=True,
            ),
        ], width=4),
    ], className="mb-3"),

    # ─── Key Metrics ──────────────────────────────────────────────────────
    dbc.Row(id="futures-metrics-row", className="mb-3"),

    # ─── Futures Curve Chart ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Term Structure (Current)"),
                dbc.CardBody(dcc.Graph(id="futures-curve-chart")),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Price History + Spreads ──────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Front-Month Price History"),
                dbc.CardBody(dcc.Graph(id="futures-price-history")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Spreads Over Time"),
                dbc.CardBody(dcc.Graph(id="futures-spread-chart")),
            ]),
        ], width=6),
    ]),
], fluid=True)
