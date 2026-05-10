"""
Supply / Demand Tab Layout — global oil production and consumption.

Controls: date range, flow toggle (supply/demand/balance), product dropdown,
          country multi-select, YoY switch.

Outputs: KPI cards, trend line chart, ranked bar chart, choropleth map, data table.
"""

from datetime import date
import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table

from config import SD_PRODUCTS, SD_SUPPLY_PRODUCTS, SD_DEMAND_PRODUCTS, SD_COUNTRIES, SD_DEFAULT_COUNTRIES

today = date.today()
default_start = date(2024, 1, 1)

# ─── Shared DataTable styles ──────────────────────────────────────────────────
_CELL = {
    "backgroundColor": "#1a1a2e",
    "color": "#e0e0e0",
    "border": "1px solid #333",
    "textAlign": "right",
    "padding": "5px 10px",
    "fontSize": "0.82rem",
    "fontFamily": "monospace",
}
_CELL_COND = [
    {"if": {"column_id": "date"},    "textAlign": "left"},
    {"if": {"column_id": "country"}, "textAlign": "left"},
    {"if": {"column_id": "product"}, "textAlign": "left"},
]
_HEADER = {
    "backgroundColor": "#16213e",
    "color": "#aaa",
    "fontWeight": "600",
    "border": "1px solid #333",
    "textAlign": "right",
}
_HEADER_COND = [
    {"if": {"column_id": "date"},    "textAlign": "left"},
    {"if": {"column_id": "country"}, "textAlign": "left"},
    {"if": {"column_id": "product"}, "textAlign": "left"},
]

_product_options = []
for k, v in SD_SUPPLY_PRODUCTS.items():
    _product_options.append({"label": f"{v['label']} (supply)", "value": k, "disabled": False})
for k, v in SD_DEMAND_PRODUCTS.items():
    if k not in SD_SUPPLY_PRODUCTS:
        _product_options.append({"label": f"{v['label']} (demand)", "value": k, "disabled": False})
_product_options_supply = [{"label": v["label"], "value": k} for k, v in SD_SUPPLY_PRODUCTS.items()]
_product_options_demand = [{"label": v["label"], "value": k} for k, v in SD_DEMAND_PRODUCTS.items()]
_country_options = [{"label": v, "value": k} for k, v in SD_COUNTRIES.items()]

layout = dbc.Container([

    # ─── Controls ──────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.Label("Date Range:", className="fw-bold small"),
            dcc.DatePickerRange(
                id="sd-date-range",
                start_date=default_start,
                end_date=today,
                display_format="YYYY-MM-DD",
            ),
        ], width="auto"),

        dbc.Col([
            html.Label("Flow:", className="fw-bold small"),
            dbc.RadioItems(
                id="sd-flow",
                options=[
                    {"label": "Supply",  "value": "supply"},
                    {"label": "Demand",  "value": "demand"},
                    {"label": "Balance (Supply − Demand)", "value": "balance"},
                ],
                value="supply",
                inline=True,
                style={"fontSize": "0.85rem"},
            ),
        ], width="auto", className="ms-4"),

        dbc.Col([
            html.Label("Product:", className="fw-bold small"),
            dcc.Dropdown(
                id="sd-product",
                options=_product_options,
                value="total",
                clearable=False,
                style={"minWidth": "180px", "fontSize": "0.85rem"},
            ),
        ], width="auto", className="ms-4"),

        dbc.Col([
            html.Label("Countries:", className="fw-bold small"),
            dcc.Dropdown(
                id="sd-countries",
                options=_country_options,
                value=SD_DEFAULT_COUNTRIES,
                multi=True,
                style={"minWidth": "320px", "fontSize": "0.85rem"},
            ),
        ], width="auto", className="ms-4"),

        dbc.Col([
            html.Label("YoY %:", className="fw-bold small"),
            dbc.Switch(id="sd-yoy", value=False, label="", style={"marginTop": "4px"}),
        ], width="auto", className="ms-4"),
    ], className="mb-3 align-items-end flex-wrap"),

    # ─── KPI Cards ─────────────────────────────────────────────────────────
    dbc.Row(id="sd-kpi-row", className="mb-3"),

    # ─── Trend Chart ───────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader(id="sd-trend-header", children="Supply / Demand Trend"),
            dbc.CardBody(dcc.Graph(id="sd-trend-chart", config={"displayModeBar": False})),
        ], className="h-100")),
    ], className="mb-3"),

    # ─── Bar Chart + Choropleth Map ────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader(id="sd-bar-header", children="Latest Month — Country Ranking"),
            dbc.CardBody(dcc.Graph(id="sd-bar-chart", config={"displayModeBar": False})),
        ], className="h-100"), width=5),

        dbc.Col(dbc.Card([
            dbc.CardHeader(id="sd-map-header", children="World Map — Latest Month (kbd)"),
            dbc.CardBody(dcc.Graph(id="sd-map-chart", config={"displayModeBar": False})),
        ], className="h-100"), width=7),
    ], className="mb-3"),

    # ─── Data Table ────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("Supply / Demand Data"),
            dbc.CardBody(
                dash_table.DataTable(
                    id="sd-data-table",
                    columns=[
                        {"name": "Date",        "id": "date"},
                        {"name": "Country",     "id": "country"},
                        {"name": "Product",     "id": "product"},
                        {"name": "Supply kbd",  "id": "supply_kbd"},
                        {"name": "Demand kbd",  "id": "demand_kbd"},
                        {"name": "Balance kbd", "id": "balance_kbd"},
                    ],
                    data=[],
                    page_size=50,
                    sort_action="native",
                    filter_action="native",
                    style_table={"overflowX": "auto"},
                    style_cell=_CELL,
                    style_cell_conditional=_CELL_COND,
                    style_header=_HEADER,
                    style_header_conditional=_HEADER_COND,
                    style_data_conditional=[
                        {
                            "if": {"filter_query": "{balance_kbd} > 0", "column_id": "balance_kbd"},
                            "color": "#2ecc71",
                        },
                        {
                            "if": {"filter_query": "{balance_kbd} < 0", "column_id": "balance_kbd"},
                            "color": "#e74c3c",
                        },
                    ],
                ),
            ),
        ])),
    ]),

], fluid=True)
