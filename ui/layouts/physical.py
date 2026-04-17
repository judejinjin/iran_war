"""
Physical Crude Tab Layout — Dated Brent (multi-source) + Dubai spot prices and differentials.
"""

from datetime import date, timedelta
import dash_bootstrap_components as dbc
from dash import html, dcc

today = date.today()
default_start = today - timedelta(days=5 * 365)

_SOURCE_OPTIONS = [
    {"label": " FRED  (daily, 1987+)",          "value": "FRED"},
    {"label": " EIA direct  (daily, lower lag)", "value": "EIA"},
    {"label": " IMF  (monthly, 1990+)",          "value": "IMF"},
]

layout = dbc.Container([
    # ─── Controls ─────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("Date Range:", className="fw-bold"),
            dcc.DatePickerRange(
                id="physical-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
        dbc.Col([
            html.Label("Dated Brent Source:", className="fw-bold"),
            dbc.RadioItems(
                id="physical-brent-source",
                options=_SOURCE_OPTIONS,
                value="FRED",
                inline=True,
                className="mt-1",
            ),
        ], width=5),
        dbc.Col([
            html.Label("Benchmark Overlays:", className="fw-bold"),
            dbc.Checklist(
                id="physical-benchmark-toggle",
                options=[
                    {"label": " WTI (CL)",           "value": "CL"},
                    {"label": " Brent futures (COIL)", "value": "COIL"},
                ],
                value=["COIL"],
                inline=True,
                className="mt-1",
            ),
        ], width=3),
    ], className="mb-3"),

    # ─── Summary Metrics ──────────────────────────────────────────────────
    dbc.Row(id="physical-metrics-row", className="mb-3"),

    # ─── Dated Brent Price History ────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(id="physical-brent-header",
                               children="Dated Brent Physical Price"),
                dbc.CardBody(dcc.Graph(id="physical-brent-chart",
                                       style={"height": "380px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Brent Physical Basis ─────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Brent Physical Basis — Dated Brent minus ICE Futures (COIL)"),
                dbc.CardBody(dcc.Graph(id="physical-basis-chart",
                                       style={"height": "280px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Dubai Price History ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Dubai Crude (DUB) — Monthly Spot vs Benchmarks"),
                dbc.CardBody(dcc.Graph(id="physical-dubai-chart",
                                       style={"height": "350px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Dubai Differentials ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Physical Differentials — Dubai vs Brent & WTI"),
                dbc.CardBody(dcc.Graph(id="physical-diff-chart",
                                       style={"height": "280px"})),
            ]),
        ], width=12),
    ]),
], fluid=True)

