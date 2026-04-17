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
                dbc.CardBody([
                    dcc.Graph(id="futures-curve-chart"),
                    html.Div(id="futures-curve-footnotes"),
                ]),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Price History + Spreads ──────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    "Price History — ",
                    dcc.Dropdown(
                        id="futures-contract-cl",
                        placeholder="WTI contract…",
                        clearable=True,
                        style={"width": "150px", "display": "inline-block",
                               "verticalAlign": "middle", "marginRight": "12px"},
                    ),
                    dcc.Dropdown(
                        id="futures-contract-coil",
                        placeholder="Brent contract…",
                        clearable=True,
                        style={"width": "150px", "display": "inline-block",
                               "verticalAlign": "middle", "marginRight": "12px"},
                    ),
                    dbc.Switch(
                        id="futures-spread-toggle",
                        label="Spread",
                        value=False,
                        style={"marginBottom": 0},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
                dbc.CardBody(dcc.Graph(id="futures-price-history")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    "Calendar Spreads ",
                    dbc.Switch(
                        id="futures-cal-6m-toggle",
                        label="Show 6M",
                        value=False,
                        style={"marginBottom": 0, "marginLeft": "12px"},
                    ),
                ], style={"display": "flex", "alignItems": "center"}),
                dbc.CardBody(dcc.Graph(id="futures-spread-chart")),
            ]),
        ], width=6),
    ]),
], fluid=True)
