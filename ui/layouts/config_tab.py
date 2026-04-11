"""
Config Tab Layout — displays all news sources, market data sources, tickers,
LLM settings, schedule, and other operational configuration.
"""

import dash_bootstrap_components as dbc
from dash import html

layout = dbc.Container([
    dbc.Row(dbc.Col(html.H5("System Configuration", className="text-light mb-3"))),

    # ─── Row 1: LLM + War Parameters ────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("LLM Backend"),
                dbc.CardBody(html.Div(id="cfg-llm")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("War / Timeline Parameters"),
                dbc.CardBody(html.Div(id="cfg-war")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Row 2: News Sources ─────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("News Sources — RSS Feeds"),
                dbc.CardBody(html.Div(id="cfg-rss")),
            ]),
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("News Sources — APIs"),
                dbc.CardBody(html.Div(id="cfg-news-apis")),
            ]),
        ], width=6),
    ], className="mb-3"),

    # ─── Row 3: Market Data ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Futures Contracts"),
                dbc.CardBody(html.Div(id="cfg-futures")),
            ]),
        ], width=4),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Market Data APIs (FRED / EIA)"),
                dbc.CardBody(html.Div(id="cfg-market-apis")),
            ]),
        ], width=4),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("IB TWS Connection"),
                dbc.CardBody(html.Div(id="cfg-ib")),
            ]),
        ], width=4),
    ], className="mb-3"),

    # ─── Row 4: Scenarios ────────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Price Scenarios"),
                dbc.CardBody(html.Div(id="cfg-scenarios")),
            ]),
        ], width=12),
    ], className="mb-3"),

    # ─── Row 5: News Keywords + Schedule ────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("News Search Keywords"),
                dbc.CardBody(html.Div(id="cfg-keywords")),
            ]),
        ], width=7),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Scheduler"),
                dbc.CardBody(html.Div(id="cfg-schedule")),
            ]),
        ], width=5),
    ], className="mb-3"),

    # ─── Row 6: Chokepoints ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Chokepoint Definitions"),
                dbc.CardBody(html.Div(id="cfg-chokepoints")),
            ]),
        ], width=12),
    ]),
], fluid=True)
