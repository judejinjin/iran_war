"""
Scenarios Tab Layout — probability bars, price range, history, key drivers.
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
                id="scen-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
    ], className="mb-3"),

    # ─── Metrics ─────────────────────────────────────────────────────────
    dbc.Row(id="scen-metrics-row", className="mb-3"),

    # ─── Scenario Probabilities ──────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Scenario Probabilities (Latest)"),
                dbc.CardBody(dcc.Graph(id="scen-probabilities-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Expected Price Range"),
                dbc.CardBody(dcc.Graph(id="scen-price-range-chart")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Probability History ─────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Probability History"),
                dbc.CardBody(dcc.Graph(id="scen-history-chart")),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Supply Impact by Scenario ───────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-oil-can me-2"),
                    "Supply Offline by Scenario (mbd)",
                ]),
                dbc.CardBody(dcc.Graph(id="scen-supply-impact-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-clock me-2"),
                    "Recovery Timeline by Scenario (days)",
                ]),
                dbc.CardBody(dcc.Graph(id="scen-recovery-chart")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Key Drivers + Reasoning ─────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Scenario Details & Reasoning"),
                dbc.CardBody(id="scen-reasoning"),
            ]),
        ], width=12),
    ]),
], fluid=True)
