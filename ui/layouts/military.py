"""
Military Tab Layout — losses tracking, deployments, escalation, map.
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
                id="mil-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
        dbc.Col([
            html.Label("Side:", className="fw-bold"),
            dbc.RadioItems(
                id="mil-side-toggle",
                options=[
                    {"label": "Both", "value": "BOTH"},
                    {"label": "Iran", "value": "Iran"},
                    {"label": "Opposing", "value": "Opposing"},
                ],
                value="BOTH",
                inline=True,
            ),
        ], width=4),
    ], className="mb-3"),

    # ─── Metrics ─────────────────────────────────────────────────────────
    dbc.Row(id="mil-metrics-row", className="mb-3"),

    # ─── Charts Row 1: Losses + Escalation ───────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Daily Losses"),
                dbc.CardBody(dcc.Graph(id="mil-losses-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Escalation Score"),
                dbc.CardBody(dcc.Graph(id="mil-escalation-chart")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Deployments Table ───────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Active Deployments"),
                dbc.CardBody(id="mil-deployments-table"),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Military Events Table ───────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Recent Military Events"),
                dbc.CardBody(id="mil-events-table"),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Map ─────────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Military Map"),
                dbc.CardBody(html.Div(id="mil-map-container")),
            ]),
        ], width=12),
    ]),
], fluid=True)
