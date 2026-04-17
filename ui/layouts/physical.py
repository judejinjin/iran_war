"""
Physical Crude Tab Layout — Dubai crude price history and differentials vs WTI/Brent.
"""

from datetime import date, timedelta
import dash_bootstrap_components as dbc
from dash import html, dcc

today = date.today()
default_start = today - timedelta(days=5 * 365)  # 5-year default for monthly DUB data

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
        ], width=5),
        dbc.Col([
            html.Label("Compare vs Benchmarks:", className="fw-bold"),
            dbc.Checklist(
                id="physical-benchmark-toggle",
                options=[
                    {"label": " WTI (CL)", "value": "CL"},
                    {"label": " Brent (COIL)", "value": "COIL"},
                ],
                value=["CL", "COIL"],
                inline=True,
            ),
        ], width=4),
    ], className="mb-3"),

    # ─── Summary Metrics ──────────────────────────────────────────────────
    dbc.Row(id="physical-metrics-row", className="mb-3"),

    # ─── Price History: Dubai + Benchmarks ───────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Dubai Crude (DUB) — Monthly Spot vs Benchmarks"),
                dbc.CardBody(dcc.Graph(id="physical-dubai-chart", style={"height": "380px"})),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Differentials ────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Physical Differentials — Dubai vs Brent & WTI"),
                dbc.CardBody(dcc.Graph(id="physical-diff-chart", style={"height": "350px"})),
            ]),
        ], width=12),
    ]),
], fluid=True)

