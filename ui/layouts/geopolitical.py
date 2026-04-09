"""
Geopolitical Tab Layout — news events master-detail + map + daily summary.
"""

from datetime import date, timedelta
import dash_bootstrap_components as dbc
from dash import html, dcc

from config import DEFAULT_TIMELINE_DAYS

today = date.today()
default_start = today - timedelta(days=DEFAULT_TIMELINE_DAYS)

layout = dbc.Container([
    # ─── Row 1: Stats + Filters on same line ────────────────────────────
    dbc.Row([
        # Stats boxes
        dbc.Col(
            dbc.Row(id="geo-metrics-row", className="g-2"),
            width="auto", className="d-flex align-items-center",
        ),
        # Filters immediately to the right of stats
        dbc.Col([
            dbc.Row([
                dbc.Col([
                    html.Label("Date Range:", className="fw-bold small"),
                    dcc.DatePickerRange(
                        id="geo-date-range",
                        start_date=default_start,
                        end_date=today,
                        display_format="YYYY-MM-DD",
                    ),
                ], width="auto"),
                dbc.Col([
                    html.Label("Category:", className="fw-bold small"),
                    dcc.Dropdown(
                        id="geo-category-filter",
                        options=[
                            {"label": "All Categories", "value": "ALL"},
                            {"label": "Geopolitical Development", "value": "geopolitical_development"},
                            {"label": "Military Operations", "value": "military_operations"},
                            {"label": "Infrastructure Damage", "value": "infrastructure_damage"},
                            {"label": "Production Shut-in", "value": "production_shutin"},
                            {"label": "Shipment Disruption", "value": "shipment_disruption"},
                        ],
                        value="ALL",
                        clearable=False,
                        style={"color": "#000", "minWidth": "200px"},
                    ),
                ], width="auto"),
            ], className="g-2 align-items-end"),
        ], className="d-flex align-items-center"),
    ], className="mb-3 align-items-center"),

    # ─── Row 2: Left = Events + Detail  |  Right = Daily Summary ──────
    dbc.Row([
        # Left half: news events list + detail text below
        dbc.Col([
            # Events scrollable list
            dbc.Card([
                dbc.CardHeader("News Events"),
                dbc.CardBody(
                    html.Div(id="geo-events-list", style={
                        "maxHeight": "220px",
                        "overflowY": "auto",
                    }),
                ),
            ], className="mb-2"),
            # Detail text below the list
            dbc.Card([
                dbc.CardHeader(id="geo-detail-header", children="Select an event"),
                dbc.CardBody(
                    html.Div(id="geo-detail-body", style={
                        "maxHeight": "200px",
                        "overflowY": "auto",
                    }),
                ),
            ]),
        ], width=6),

        # Right half: daily summary scrollable list
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Daily Summary"),
                dbc.CardBody(
                    html.Div(
                        id="geo-daily-summary",
                        style={"maxHeight": "460px", "overflowY": "auto"},
                    ),
                ),
            ], style={"height": "100%"}),
        ], width=6),
    ], className="mb-3"),

    # ─── Row 3: Map ──────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Event Map"),
                dbc.CardBody(html.Div(id="geo-map-container")),
            ]),
        ], width=12),
    ]),
], fluid=True)
