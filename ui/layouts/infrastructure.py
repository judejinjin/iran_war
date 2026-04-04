"""
Infrastructure Damage Tab Layout — oil facility damage tracking, map, and timeline.
Includes country production dashboard, facility status table, supply waterfall, Hormuz panel.
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
                id="infra-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
        dbc.Col([
            html.Label("Facility Type:", className="fw-bold"),
            dcc.Dropdown(
                id="infra-facility-filter",
                options=[
                    {"label": "All Facilities", "value": "ALL"},
                    {"label": "Refineries", "value": "refinery"},
                    {"label": "Pipelines", "value": "pipeline"},
                    {"label": "Terminals / Ports", "value": "terminal"},
                    {"label": "Storage", "value": "storage"},
                    {"label": "Production Fields", "value": "field"},
                    {"label": "Processing", "value": "processing"},
                    {"label": "LNG Plants", "value": "lng_plant"},
                ],
                value="ALL",
                clearable=False,
                style={"color": "#000"},
            ),
        ], width=3),
        dbc.Col([
            html.Label("Min Severity:", className="fw-bold"),
            dcc.Slider(
                id="infra-severity-slider",
                min=1, max=10, step=1, value=1,
                marks={i: str(i) for i in range(1, 11)},
            ),
        ], width=5),
    ], className="mb-3"),

    # ─── Summary Metrics ─────────────────────────────────────────────────
    dbc.Row(id="infra-metrics-row", className="mb-3"),

    # ─── Chokepoint Transit Panels ─────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-ship me-2"),
                    "Maritime Chokepoint Transit Status",
                ]),
                dbc.CardBody(id="infra-chokepoint-panels"),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Chokepoint Timeline Chart ───────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-chart-line me-2"),
                    "Chokepoint Reduction Over Time",
                ]),
                dbc.CardBody(dcc.Graph(id="infra-chokepoint-timeline-chart")),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Country Production Dashboard ────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-industry me-2"),
                    "Country Oil Production — Baseline vs Current",
                ]),
                dbc.CardBody(dcc.Graph(id="infra-country-production-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-chart-bar me-2"),
                    "Regional Supply Waterfall",
                ]),
                dbc.CardBody(dcc.Graph(id="infra-waterfall-chart")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Infrastructure Map ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-map-marked-alt me-2"),
                    "Oil Infrastructure Status Map",
                ]),
                dbc.CardBody(html.Div(id="infra-map-container")),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Charts Row ──────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Damage Events Over Time"),
                dbc.CardBody(dcc.Graph(id="infra-timeline-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Cumulative Supply Impact (mbd lost)"),
                dbc.CardBody(dcc.Graph(id="infra-supply-impact-chart")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Facility Status Table ───────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.I(className="fas fa-table me-2"),
                    "Facility Status — Latest",
                ]),
                dbc.CardBody(
                    html.Div(id="infra-facility-table", style={
                        "maxHeight": "400px", "overflowY": "auto",
                    }),
                ),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Events: Master-Detail ───────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Infrastructure Damage Events"),
                dbc.CardBody(
                    html.Div(id="infra-events-list", style={
                        "maxHeight": "450px",
                        "overflowY": "auto",
                    }),
                ),
            ]),
        ], width=5),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(id="infra-detail-header", children="Select an event"),
                dbc.CardBody(
                    html.Div(id="infra-detail-body", style={
                        "maxHeight": "450px",
                        "overflowY": "auto",
                    }),
                    style={"minHeight": "200px"},
                ),
            ]),
        ], width=7),
    ], className="mb-3"),

    # ─── Daily Summary ───────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Infrastructure Damage Daily Summary"),
                dbc.CardBody(id="infra-daily-summary"),
            ]),
        ], width=12),
    ]),
], fluid=True)
