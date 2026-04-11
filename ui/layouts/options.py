"""
Options Tab Layout — IV surface, smile, risk reversal, open interest.
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
            html.Label("Underlying:", className="fw-bold"),
            dbc.RadioItems(
                id="opt-underlying-toggle",
                options=[
                    {"label": "WTI (CL)", "value": "CL"},
                    {"label": "Brent (COIL)", "value": "COIL"},
                ],
                value="CL",
                inline=True,
            ),
        ], width=3),
        dbc.Col([
            html.Label("Date Range:", className="fw-bold"),
            dcc.DatePickerRange(
                id="opt-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
    ], className="mb-3"),

    # ─── Metrics ─────────────────────────────────────────────────────────
    dbc.Row(id="opt-metrics-row", className="mb-3"),

    # ─── Charts Row 1: IV Surface + Smile ────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Implied Volatility Surface"),
                dbc.CardBody(dcc.Graph(id="opt-vol-surface")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Volatility Smile"),
                dbc.CardBody(dcc.Graph(id="opt-vol-smile")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Charts Row 2: Risk Reversal + OI ────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("25-Delta Risk Reversal"),
                dbc.CardBody(dcc.Graph(id="opt-risk-reversal")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Open Interest by Strike"),
                dbc.CardBody(dcc.Graph(id="opt-open-interest")),
            ]),
        ], width=6),
    ]),
], fluid=True)
