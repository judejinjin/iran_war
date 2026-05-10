"""
SPR Tab Layout — Strategic Petroleum Reserve monitor.

Displays US SPR levels, international government stocks (CN, JP, DE, FR, IT, KR),
days-of-cover, cumulative war drawdown, and a cross-country snapshot comparison.
"""

from datetime import date, timedelta
import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table

from config import DEFAULT_TIMELINE_DAYS, SPR_COUNTRIES, WAR_START_DATE

today = date.today()
default_start = date(2026, 2, 28)

# ─── Shared DataTable styles (mirror futures.py) ──────────────────────────────
_CELL = {
    "backgroundColor": "#1a1a2e",
    "color": "#e0e0e0",
    "border": "1px solid #333",
    "textAlign": "right",
    "padding": "5px 10px",
    "fontSize": "0.82rem",
    "fontFamily": "monospace",
}
_CELL_COND = [{"if": {"column_id": "date"}, "textAlign": "left"},
              {"if": {"column_id": "country"}, "textAlign": "left"},
              {"if": {"column_id": "source"}, "textAlign": "left"}]
_HEADER = {
    "backgroundColor": "#16213e",
    "color": "#aaa",
    "fontWeight": "600",
    "border": "1px solid #333",
    "textAlign": "right",
}
_HEADER_COND = [{"if": {"column_id": "date"}, "textAlign": "left"},
                {"if": {"column_id": "country"}, "textAlign": "left"},
                {"if": {"column_id": "source"}, "textAlign": "left"}]

_country_options = [{"label": v, "value": k} for k, v in SPR_COUNTRIES.items()]  # rebuilt on each import

layout = dbc.Container([

    # ─── Controls ──────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("Date Range:", className="fw-bold small"),
            dcc.DatePickerRange(
                id="spr-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width="auto"),
    ], className="mb-3 align-items-end"),

    # ─── Country selector (stats & levels chart) ───────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("Country (stats & chart):", className="fw-bold small me-2"),
            dbc.RadioItems(
                id="spr-chart-country",
                options=_country_options,
                value="US",
                inline=True,
                style={"fontSize": "0.85rem", "display": "inline-flex", "gap": "10px"},
            ),
        ], width=12, className="mb-2"),
    ]),

    # ─── Key Metrics ───────────────────────────────────────────────────────
    dbc.Row(id="spr-metrics-row", className="mb-3"),

    # ─── Top row: SPR Levels Over Time ──────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(id="spr-levels-chart-header", children="SPR Levels Over Time (Mbbl)"),
                dbc.CardBody(dcc.Graph(id="spr-levels-chart")),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Bottom row: US Stacked Bars + Country Snapshot ───────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("US SPR vs Commercial Stocks (Mbbl)"),
                dbc.CardBody(dcc.Graph(id="spr-us-stacked-chart")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Latest Country Snapshot (Mbbl)"),
                dbc.CardBody(dcc.Graph(id="spr-snapshot-chart")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Data Table ────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("SPR Data"),
                dbc.CardBody(
                    dash_table.DataTable(
                        id="spr-data-table",
                        columns=[
                            {"name": "Date",         "id": "date"},
                            {"name": "Country",      "id": "country"},
                            {"name": "SPR (Mbbl)",   "id": "spr_mbbl"},
                            {"name": "Comm. (Mbbl)", "id": "commercial_mbbl"},
                            {"name": "Total (Mbbl)", "id": "total_mbbl"},
                            {"name": "Days at Rate", "id": "days_at_rate"},
                            {"name": "Δ 1W (Mbbl)",  "id": "delta_1w"},
                            {"name": "Δ 1M (Mbbl)",  "id": "delta_1m"},
                            {"name": "Source",       "id": "source"},
                        ],
                        page_size=20,
                        sort_action="native",
                        sort_by=[{"column_id": "date", "direction": "desc"}],
                        filter_action="native",
                        style_table={"overflowY": "auto", "maxHeight": "420px"},
                        style_cell=_CELL,
                        style_cell_conditional=_CELL_COND,
                        style_header=_HEADER,
                        style_header_conditional=_HEADER_COND,
                        style_data_conditional=[
                            {
                                "if": {
                                    "filter_query": "{days_at_rate} < 365 && {days_at_rate} > 0",
                                    "column_id": "days_at_rate",
                                },
                                "color": "#e74c3c",
                                "fontWeight": "bold",
                            },
                            {
                                "if": {
                                    "filter_query": "{delta_1w} < 0",
                                    "column_id": "delta_1w",
                                },
                                "color": "#e74c3c",
                            },
                            {
                                "if": {
                                    "filter_query": "{delta_1w} > 0",
                                    "column_id": "delta_1w",
                                },
                                "color": "#2ecc71",
                            },
                        ],
                    ),
                ),
            ]),
        ], width=12),
    ]),

], fluid=True)
