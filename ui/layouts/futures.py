"""
Futures Tab Layout — curve charts, spread charts, key metrics.
"""

from datetime import date, timedelta
import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table

from config import DEFAULT_TIMELINE_DAYS

today = date.today()
default_start = today - timedelta(days=DEFAULT_TIMELINE_DAYS)

# ─── Shared DataTable style dicts (reused across all tables on this tab) ──────
_CELL = {
    "backgroundColor": "#1a1a2e",
    "color": "#e0e0e0",
    "border": "1px solid #333",
    "textAlign": "right",
    "padding": "5px 10px",
    "fontSize": "0.82rem",
    "fontFamily": "monospace",
}
_CELL_COND = [{"if": {"column_id": "date"}, "textAlign": "left"}]
_HEADER = {
    "backgroundColor": "#16213e",
    "color": "#aaa",
    "fontWeight": "600",
    "border": "1px solid #333",
    "textAlign": "right",
}
_HEADER_COND = [{"if": {"column_id": "date"}, "textAlign": "left"}]

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
                dbc.CardHeader([
                    "Term Structure",
                    dbc.RadioItems(
                        id="futures-term-structure-symbol",
                        options=[
                            {"label": "WTI", "value": "CL"},
                            {"label": "Brent", "value": "COIL"},
                        ],
                        value="CL",
                        inline=True,
                        style={"marginLeft": "12px", "fontSize": "0.82rem"},
                    ),
                    dbc.Checklist(
                        id="futures-term-structure-overlays",
                        options=[
                            {"label": "Inception (03/02/2026)", "value": "INCEPTION"},
                            {"label": "1W", "value": "1W"},
                            {"label": "1M", "value": "1M"},
                            {"label": "3M", "value": "3M"},
                            {"label": "6M", "value": "6M"},
                            {"label": "12M", "value": "12M"},
                        ],
                        value=["INCEPTION", "1M"],
                        inline=True,
                        style={"marginLeft": "12px", "fontSize": "0.82rem"},
                    ),
                ], style={"display": "flex", "alignItems": "center"}),
                dbc.CardBody([
                    dcc.Graph(id="futures-curve-chart"),
                    html.Div(id="futures-curve-footnotes"),
                    html.Div(id="futures-term-structure-tables", style={"marginTop": "16px"}),
                ]),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Price History (left) + Calendar Spreads (right) ────────────────
    dbc.Row([

        # ── LEFT col: price history chart + simplified settlement tables ──
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    "Price History — ",
                    dcc.Dropdown(
                        id="futures-contract-cl",
                        placeholder="WTI contract…",
                        clearable=True,
                        style={"width": "220px", "display": "inline-block",
                               "verticalAlign": "middle", "marginRight": "12px"},
                    ),
                    dcc.Dropdown(
                        id="futures-contract-coil",
                        placeholder="Brent contract…",
                        clearable=True,
                        style={"width": "220px", "display": "inline-block",
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
            # Settlement tables below the price history chart
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            "WTI (CL) Settlements",
                            html.Span(id="futures-table-cl-label",
                                     style={"marginLeft": "8px", "fontSize": "0.82rem",
                                            "color": "#aaa", "fontWeight": "400"}),
                        ]),
                        dbc.CardBody(
                            dash_table.DataTable(
                                id="futures-table-cl",
                                columns=[
                                    {"name": "Date",           "id": "date"},
                                    {"name": "Settlement ($)", "id": "price"},
                                ],
                                page_size=15,
                                sort_action="native",
                                sort_by=[{"column_id": "date", "direction": "desc"}],
                                style_table={"overflowY": "auto", "maxHeight": "320px"},
                                style_cell=_CELL,
                                style_cell_conditional=_CELL_COND,
                                style_header=_HEADER,
                                style_header_conditional=_HEADER_COND,
                            ),
                        ),
                    ]),
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            "Brent (COIL) Settlements",
                            html.Span(id="futures-table-coil-label",
                                     style={"marginLeft": "8px", "fontSize": "0.82rem",
                                            "color": "#aaa", "fontWeight": "400"}),
                        ]),
                        dbc.CardBody(
                            dash_table.DataTable(
                                id="futures-table-coil",
                                columns=[
                                    {"name": "Date",           "id": "date"},
                                    {"name": "Settlement ($)", "id": "price"},
                                ],
                                page_size=15,
                                sort_action="native",
                                sort_by=[{"column_id": "date", "direction": "desc"}],
                                style_table={"overflowY": "auto", "maxHeight": "320px"},
                                style_cell=_CELL,
                                style_cell_conditional=_CELL_COND,
                                style_header=_HEADER,
                                style_header_conditional=_HEADER_COND,
                            ),
                        ),
                    ]),
                ], width=6),
            ], className="mt-2"),
        ], width=6),

        # ── RIGHT col: calendar spread chart + inspection tables on click ─
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    "Calendar Spreads ",
                    dbc.RadioItems(
                        id="futures-cal-spread-toggle",
                        options=[
                            {"label": "M1-M2",  "value": "M1-M2"},
                            {"label": "M1-M6",  "value": "M1-M6"},
                            {"label": "M1-M12", "value": "M1-M12"},
                        ],
                        value="M1-M12",
                        inline=True,
                        style={"marginLeft": "16px", "fontSize": "0.85rem"},
                    ),
                    html.Span(style={"flex": "1"}),
                    dcc.DatePickerRange(
                        id="futures-spread-date-range",
                        start_date=today - timedelta(days=365),
                        end_date=today,
                        display_format="YYYY-MM-DD",
                        style={"fontSize": "0.8rem"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "6px"}),
                dbc.CardBody([
                    dcc.Graph(id="futures-spread-chart"),
                    html.Div(
                        id="futures-spread-contracts",
                        style={"fontSize": "0.78rem", "color": "#888",
                               "marginTop": "4px", "paddingLeft": "4px"},
                    ),
                    # Spread percentile metrics row (populated by callback)
                    html.Div(id="futures-spread-percentile-row", style={"marginTop": "8px"}),
                ]),
            ]),
            # Inspection tables — populated on click
            html.Div(
                id="futures-spread-inspect-hint",
                children="",
                style={"fontSize": "0.78rem", "color": "#666",
                       "marginTop": "6px", "paddingLeft": "4px"},
            ),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(
                            html.Span(id="futures-spread-inspect-cl-label",
                                      children="WTI — click chart to load"),
                        ),
                        dbc.CardBody(
                            dash_table.DataTable(
                                id="futures-spread-inspect-cl",
                                columns=[
                                    {"name": "Date",        "id": "date"},
                                    {"name": "M1 ($)",      "id": "m1"},
                                    {"name": "Mn ($)",      "id": "mn"},
                                    {"name": "Spread ($)",  "id": "spread"},
                                ],
                                page_size=15,
                                sort_action="native",
                                sort_by=[{"column_id": "date", "direction": "desc"}],
                                style_table={"overflowY": "auto", "maxHeight": "320px"},
                                style_cell=_CELL,
                                style_cell_conditional=_CELL_COND,
                                style_header=_HEADER,
                                style_header_conditional=_HEADER_COND,
                            ),
                        ),
                    ]),
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(
                            html.Span(id="futures-spread-inspect-coil-label",
                                      children="Brent — click chart to load"),
                        ),
                        dbc.CardBody(
                            dash_table.DataTable(
                                id="futures-spread-inspect-coil",
                                columns=[
                                    {"name": "Date",        "id": "date"},
                                    {"name": "M1 ($)",      "id": "m1"},
                                    {"name": "Mn ($)",      "id": "mn"},
                                    {"name": "Spread ($)",  "id": "spread"},
                                ],
                                page_size=15,
                                sort_action="native",
                                sort_by=[{"column_id": "date", "direction": "desc"}],
                                style_table={"overflowY": "auto", "maxHeight": "320px"},
                                style_cell=_CELL,
                                style_cell_conditional=_CELL_COND,
                                style_header=_HEADER,
                                style_header_conditional=_HEADER_COND,
                            ),
                        ),
                    ]),
                ], width=6),
            ], className="mt-2"),
        ], width=6),

    ], className="mb-3"),
], fluid=True)
