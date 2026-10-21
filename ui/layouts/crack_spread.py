"""
Crack Spread Tab Layout — US diesel (ULSD) crack spread vs WTI/Brent
and 3-2-1 composite crack spread, with seasonal context.
"""

from datetime import date, timedelta
import dash_bootstrap_components as dbc
from dash import html, dcc

today = date.today()
default_start = today - timedelta(days=5 * 365)

_CRACK_TYPE_OPTIONS = [
    {"label": " Diesel Crack vs WTI",   "value": "DIESEL_CRACK_WTI"},
    {"label": " Diesel Crack vs Brent", "value": "DIESEL_CRACK_BRENT"},
    {"label": " 3-2-1 Crack vs WTI",   "value": "CRACK_321_WTI"},
]

layout = dbc.Container([
    # ─── Controls ─────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("Date Range:", className="fw-bold"),
            dcc.DatePickerRange(
                id="crack-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
        dbc.Col([
            html.Label("Crack Spread Type:", className="fw-bold"),
            dbc.Checklist(
                id="crack-type-toggle",
                options=_CRACK_TYPE_OPTIONS,
                value=["DIESEL_CRACK_WTI"],
                inline=True,
                className="mt-1",
            ),
        ], width=5),
        dbc.Col([
            html.Label("Options:", className="fw-bold"),
            dbc.Checklist(
                id="crack-seasonal-toggle",
                options=[{"label": " Show 5-yr Seasonal Band", "value": "seasonal"}],
                value=["seasonal"],
                inline=True,
                className="mt-1",
            ),
        ], width=3),
    ], className="mb-3"),

    # ─── Metric Cards ─────────────────────────────────────────────────────
    dbc.Row(id="crack-metrics-row", className="mb-3"),

    # ─── Main Crack Spread Chart ───────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Diesel & 3-2-1 Crack Spreads — Time Series ($/bbl)"),
                dbc.CardBody(dcc.Graph(id="crack-main-chart",
                                       style={"height": "400px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Seasonal Comparison ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Diesel Crack Seasonal Pattern — Current Year vs 5-Year Band"),
                dbc.CardBody(dcc.Graph(id="crack-seasonal-chart",
                                       style={"height": "300px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Price Components ─────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Crack Spread Components — ULSD spot vs WTI ($/bbl)"),
                dbc.CardBody(dcc.Graph(id="crack-components-chart",
                                       style={"height": "300px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Distribution ─────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Diesel Crack Spread Distribution (full history) — Current Percentile"),
                dbc.CardBody(dcc.Graph(id="crack-distribution-chart",
                                       style={"height": "280px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Recent Data Table ────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Diesel Crack — Recent 20 Trading Days"),
                dbc.CardBody(id="crack-recent-table"),
            ]),
        ], width=12),
    ]),
], fluid=True)
