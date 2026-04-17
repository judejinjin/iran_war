"""
Config Tab Callback — populates all configuration display panels from config.py.
Read-only; no DB access needed.
"""

import dash_bootstrap_components as dbc
from dash import html, callback, Output, Input

import config


def _kv(label, value, value_class="text-light"):
    """Single key-value row."""
    return html.Tr([
        html.Td(label, className="text-muted pe-3", style={"whiteSpace": "nowrap", "fontSize": "0.85rem"}),
        html.Td(str(value), className=f"{value_class} fw-bold", style={"fontSize": "0.85rem"}),
    ])


def _table(rows):
    return html.Table(html.Tbody(rows), className="table table-sm table-borderless mb-0")


def _badge(text, color="secondary"):
    return dbc.Badge(text, color=color, className="me-1 mb-1", style={"fontSize": "0.8rem"})


def _mask(key: str) -> str:
    """Show first 6 chars then asterisks, or '(not set)' if empty."""
    if not key:
        return html.Span("(not set)", className="text-danger")
    visible = key[:6]
    return html.Span([visible, "••••••••••"], className="text-warning font-monospace")


@callback(
    Output("cfg-llm", "children"),
    Output("cfg-war", "children"),
    Output("cfg-rss", "children"),
    Output("cfg-news-apis", "children"),
    Output("cfg-futures", "children"),
    Output("cfg-market-apis", "children"),
    Output("cfg-ib", "children"),
    Output("cfg-physical", "children"),
    Output("cfg-scenarios", "children"),
    Output("cfg-keywords", "children"),
    Output("cfg-schedule", "children"),
    Output("cfg-chokepoints", "children"),
    Input("cfg-init", "data"),
)
def populate_config(_):
    # ── LLM ──────────────────────────────────────────────────────────────
    backend = config.LLM_BACKEND
    if backend == "copilot_sdk":
        model_label = "Copilot Model"
        model_val = config.COPILOT_MODEL
        tokens_val = config.COPILOT_MAX_TOKENS
        color = "info"
    else:
        model_label = "Anthropic Model"
        model_val = config.CLAUDE_MODEL
        tokens_val = config.CLAUDE_MAX_TOKENS
        color = "warning"

    llm = _table([
        _kv("Backend", backend, f"text-{'info' if backend == 'copilot_sdk' else 'warning'}"),
        _kv(model_label, model_val),
        _kv("Max Tokens", tokens_val),
        _kv("Claude Key", _mask(config.CLAUDE_KEY)),
        _kv("OpenAI Key", _mask(config.OPENAI_KEY)),
        _kv("OpenRouter Key", _mask(config.OPENROUTER_KEY)),
    ])

    # ── War / Timeline ────────────────────────────────────────────────────
    war = _table([
        _kv("War Start Date", config.WAR_START_DATE, "text-danger"),
        _kv("Default Timeline", f"{config.DEFAULT_TIMELINE_DAYS} days"),
        _kv("Dashboard Refresh", f"{config.DASHBOARD_REFRESH_SECONDS}s"),
        _kv("Headline Dedup Threshold", config.HEADLINE_SIMILARITY_THRESHOLD),
        _kv("DB Path", str(config.DB_PATH).replace("\\", "/"), "text-muted"),
    ])

    # ── RSS Feeds ─────────────────────────────────────────────────────────
    rss_rows = []
    for name, url in config.RSS_FEEDS.items():
        rss_rows.append(html.Tr([
            html.Td(name.replace("_", " ").title(),
                    className="text-muted pe-3",
                    style={"fontSize": "0.85rem", "whiteSpace": "nowrap"}),
            html.Td(
                html.A(url, href=url, target="_blank",
                       className="text-info",
                       style={"fontSize": "0.78rem", "wordBreak": "break-all"}),
            ),
        ]))
    rss = html.Table(html.Tbody(rss_rows), className="table table-sm table-borderless mb-0")

    # ── News APIs ─────────────────────────────────────────────────────────
    news_apis = _table([
        _kv("NewsAPI Key", _mask(config.NEWSAPI_KEY)),
        _kv("Bing News Key", _mask(config.BING_NEWS_KEY)),
        _kv("Event Registry Key", _mask(config.EVENT_REGISTRY_KEY)),
        _kv("GDELT API", config.GDELT_DOC_API, "text-muted"),
        _kv("GDELT Rate Limit", f"{config.GDELT_RATE_LIMIT_SECONDS}s between requests"),
        html.Tr([
            html.Td("GDELT Query", className="text-muted pe-3", style={"fontSize": "0.85rem", "verticalAlign": "top"}),
            html.Td(config.GDELT_QUERY, style={"fontSize": "0.8rem", "wordBreak": "break-word"}),
        ]),
    ])

    # ── Futures ───────────────────────────────────────────────────────────
    futures_rows = []
    for sym in config.FUTURES_SYMBOLS:
        exch = config.FUTURES_EXCHANGE.get(sym, "")
        futures_rows.append(_kv(sym, f"{exch}"))
    futures_rows += [
        _kv("Months Ahead", config.FUTURES_MONTHS_AHEAD),
        _kv("Options Expiries Ahead", config.OPTIONS_EXPIRIES_AHEAD),
    ]
    futures = _table(futures_rows)

    # ── Market Data APIs ──────────────────────────────────────────────────
    market_apis = _table([
        _kv("EIA Key", _mask(config.EIA_API_KEY)),
        _kv("FRED Key", _mask(config.FRED_API_KEY)),
        _kv("EIA Crude Inventory", config.EIA_CRUDE_INVENTORY),
        _kv("EIA US Production", config.EIA_US_PRODUCTION),
        _kv("FRED WTI Series", config.FRED_WTI_SERIES),
        _kv("FRED Brent Series", config.FRED_BRENT_SERIES),
        _kv("FRED Dubai Series", config.FRED_DUBAI_SERIES),
    ])

    # ── Physical Crude Sources ────────────────────────────────────────────
    physical_rows = [
        html.Thead(html.Tr([
            html.Th("Symbol", style={"fontSize": "0.85rem", "width": "7%"}),
            html.Th("Grade", style={"fontSize": "0.85rem", "width": "15%"}),
            html.Th("Source", style={"fontSize": "0.85rem", "width": "12%"}),
            html.Th("Frequency", style={"fontSize": "0.85rem", "width": "10%"}),
            html.Th("History", style={"fontSize": "0.85rem", "width": "10%"}),
            html.Th("Series / Endpoint", style={"fontSize": "0.85rem"}),
        ])),
        html.Tbody([
            html.Tr([
                html.Td(dbc.Badge("DUB", color="primary", style={"fontSize": "0.82rem"})),
                html.Td("Dubai Crude (Middle East sour)", style={"fontSize": "0.85rem"}),
                html.Td("FRED / IMF", className="text-muted", style={"fontSize": "0.85rem"}),
                html.Td("Monthly", style={"fontSize": "0.85rem"}),
                html.Td("1992+", style={"fontSize": "0.85rem"}),
                html.Td(
                    html.Code(config.FRED_DUBAI_SERIES, style={"fontSize": "0.82rem"}),
                ),
            ]),
        ]),
    ]
    physical = html.Table(
        physical_rows,
        className="table table-sm table-borderless mb-0",
    )

    # ── IB TWS ────────────────────────────────────────────────────────────
    ib = _table([
        _kv("Host", config.TWS_HOST),
        _kv("Port", config.TWS_PORT),
        _kv("Client ID", config.TWS_CLIENT_ID),
    ])

    # ── Scenarios ─────────────────────────────────────────────────────────
    scenario_cols = [
        html.Thead(html.Tr([
            html.Th("Scenario", style={"fontSize": "0.85rem"}),
            html.Th("Brent Range", style={"fontSize": "0.85rem"}),
            html.Th("Description", style={"fontSize": "0.85rem"}),
        ])),
    ]
    colors = ["danger", "warning", "info", "primary", "success", "secondary"]
    s_rows = []
    for i, s in enumerate(config.SCENARIOS):
        c = colors[i % len(colors)]
        s_rows.append(html.Tr([
            html.Td(dbc.Badge(s["name"], color=c, style={"fontSize": "0.82rem"})),
            html.Td(f"${s['brent_low']}–${s['brent_high']}", style={"fontSize": "0.85rem", "fontWeight": "bold"}),
            html.Td(s["description"], className="text-muted", style={"fontSize": "0.82rem"}),
        ]))
    scenarios = html.Table(
        scenario_cols + [html.Tbody(s_rows)],
        className="table table-sm table-borderless mb-0",
    )

    # ── Keywords ─────────────────────────────────────────────────────────
    badges = [_badge(kw, "secondary") for kw in config.NEWS_KEYWORDS]
    keywords = html.Div(badges)

    # ── Schedule ──────────────────────────────────────────────────────────
    schedule = _table([
        _kv("Timezone", config.SCHEDULE_TIMEZONE),
        _kv("News Interval", f"Every {config.NEWS_INTERVAL_HOURS}h"),
        _kv("Market Data", ", ".join(f"{h:02d}:{m:02d}" for h, m in config.MARKET_DATA_TIMES)),
        _kv("EIA / FRED", f"{config.EIA_FRED_TIME[0]:02d}:{config.EIA_FRED_TIME[1]:02d}"),
        _kv("AI Summaries", ", ".join(f"{h:02d}:{m:02d}" for h, m in config.AI_SUMMARY_TIMES)),
        _kv("Scenario Analysis", f"{config.SCENARIO_ANALYSIS_TIME[0]:02d}:{config.SCENARIO_ANALYSIS_TIME[1]:02d}"),
    ])

    # ── Chokepoints ───────────────────────────────────────────────────────
    cp_cols = html.Thead(html.Tr([
        html.Th("Name", style={"fontSize": "0.85rem"}),
        html.Th("Oil (mbd)", style={"fontSize": "0.85rem"}),
        html.Th("LNG (bcfd)", style={"fontSize": "0.85rem"}),
        html.Th("Lat / Lon Bounds", style={"fontSize": "0.85rem"}),
        html.Th("Detection Keywords", style={"fontSize": "0.85rem"}),
    ]))
    cp_rows = []
    for key, baseline in config.CHOKEPOINT_BASELINES.items():
        bounds = config.CHOKEPOINT_BOUNDS.get(key, {})
        lat = f"{bounds.get('lat_min','?')}–{bounds.get('lat_max','?')}"
        lon = f"{bounds.get('lon_min','?')}–{bounds.get('lon_max','?')}"
        kws = [_badge(k, "dark") for k in bounds.get("keywords", [])]
        cp_rows.append(html.Tr([
            html.Td(baseline["label"], style={"fontSize": "0.85rem", "fontWeight": "bold", "whiteSpace": "nowrap"}),
            html.Td(f"{baseline['normal_oil_mbd']}", style={"fontSize": "0.85rem"}),
            html.Td(f"{baseline['normal_lng_bcfd']}", style={"fontSize": "0.85rem"}),
            html.Td(f"lat {lat} / lon {lon}", className="text-muted", style={"fontSize": "0.8rem", "whiteSpace": "nowrap"}),
            html.Td(html.Div(kws)),
        ]))
    chokepoints = html.Table(
        [cp_cols, html.Tbody(cp_rows)],
        className="table table-sm table-borderless mb-0",
        style={"tableLayout": "auto"},
    )

    return llm, war, rss, news_apis, futures, market_apis, ib, physical, scenarios, keywords, schedule, chokepoints
