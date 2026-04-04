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
    # ─── Controls ─────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("Date Range:", className="fw-bold"),
            dcc.DatePickerRange(
                id="geo-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width=4),
        dbc.Col([
            html.Label("Category Filter:", className="fw-bold"),
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
                style={"color": "#000"},
            ),
        ], width=4),
    ], className="mb-3"),

    # ─── Summary Metrics ─────────────────────────────────────────────────
    dbc.Row(id="geo-metrics-row", className="mb-3"),

    # ─── Events: Master-Detail Layout ────────────────────────────────────
    dbc.Row([
        # Left: scrollable title list
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Recent Events"),
                dbc.CardBody(
                    html.Div(id="geo-events-list", style={
                        "maxHeight": "500px",
                        "overflowY": "auto",
                    }),
                ),
            ]),
        ], width=5),
        # Right: detail panel
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(id="geo-detail-header", children="Select an event"),
                dbc.CardBody(
                    html.Div(id="geo-detail-body", style={
                        "maxHeight": "500px",
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
                dbc.CardHeader("Daily Summary"),
                dbc.CardBody(id="geo-daily-summary"),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Map ─────────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Event Map"),
                dbc.CardBody(html.Div(id="geo-map-container")),
            ]),
        ], width=12),
    ]),
], fluid=True)
