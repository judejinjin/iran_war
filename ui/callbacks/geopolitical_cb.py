"""
Geopolitical Tab Callbacks — master-detail event list, map, summary.
"""

from datetime import date, datetime
import re as _re
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, State, no_update, ALL, ctx
import dash

from db.database import get_session, GeopoliticalEvent, DailySummary

_HTML_TAG_RE = _re.compile(r"<[^>]+>")
_HTML_ENT_RE = _re.compile(r"&\w+;")
def _clean(text: str) -> str:
    """Strip HTML tags and common entities from text."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = _HTML_ENT_RE.sub("", text)
    return text.strip()


@callback(
    Output("geo-metrics-row", "children"),
    Output("geo-events-list", "children"),
    Output("geo-daily-summary", "children"),
    Output("geo-map-container", "children"),
    Input("geo-date-range", "start_date"),
    Input("geo-date-range", "end_date"),
    Input("geo-category-filter", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_geopolitical(start_date, end_date, category, _n):
    session = get_session()
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        # ─── Query events ─────────────────────────────────────────────
        q = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.timestamp >= datetime.combine(start_date, datetime.min.time()),
            GeopoliticalEvent.timestamp <= datetime.combine(end_date, datetime.max.time()),
        )
        if category and category != "ALL":
            q = q.filter(GeopoliticalEvent.category == category)
        events = q.order_by(GeopoliticalEvent.timestamp.desc()).all()

        # ─── Metrics ─────────────────────────────────────────────────
        total = len(events)
        high_sev = sum(1 for e in events if e.severity and e.severity >= 7)
        avg_sev = sum(e.severity or 0 for e in events) / max(total, 1)
        total_impact = sum(e.supply_impact_mbd or 0 for e in events)

        metrics = [
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Small("Total Events", className="text-muted"),
                html.P(str(total), className="fw-bold mb-0"),
            ], className="p-2"), className="border-0"), width="auto"),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Small("High Sev (7+)", className="text-muted"),
                html.P(str(high_sev), className="fw-bold mb-0"),
            ], className="p-2"), className="border-0"), width="auto"),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Small("Avg Severity", className="text-muted"),
                html.P(f"{avg_sev:.1f}", className="fw-bold mb-0"),
            ], className="p-2"), className="border-0"), width="auto"),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Small("Impact (mbd)", className="text-muted"),
                html.P(f"{total_impact:.2f}", className="fw-bold mb-0"),
            ], className="p-2"), className="border-0"), width="auto"),
        ]

        # ─── Events list (master panel) ──────────────────────────────
        event_items = []
        for e in events[:100]:
            sev = e.severity or 0
            color = "danger" if sev >= 7 else "warning" if sev >= 4 else "info"
            cat_short = (e.category or "unknown").replace("_", " ").title()[:20]
            ts = e.timestamp.strftime("%m/%d %H:%M") if e.timestamp else ""
            event_items.append(
                dbc.ListGroupItem(
                    [
                        html.Div([
                            dbc.Badge(f"S:{sev}", color=color, className="me-2"),
                            html.Small(ts, className="text-muted me-2"),
                            html.Small(cat_short, className="text-muted"),
                        ]),
                        html.Div(
                            _clean((e.headline or "No headline")[:120]),
                            className="fw-bold mt-1",
                            style={"fontSize": "0.9rem"},
                        ),
                    ],
                    id={"type": "geo-event-item", "index": e.id},
                    action=True,
                    style={"cursor": "pointer", "padding": "8px 12px"},
                )
            )

        if not event_items:
            event_items = [html.P("No events found in this date range.", className="text-muted")]
        event_list = dbc.ListGroup(event_items, flush=True)

        # ─── Daily summary ───────────────────────────────────────────
        summaries = session.query(DailySummary).filter(
            DailySummary.date >= start_date,
            DailySummary.date <= end_date,
        ).order_by(DailySummary.date.desc()).limit(30).all()

        if summaries:
            summary_content = []
            for s in summaries:
                summary_content.append(html.Div([
                    html.Div(
                        f"{s.date} — {s.category.replace('_', ' ').title()}",
                        className="text-info fw-bold",
                        style={"fontSize": "0.85rem"},
                    ),
                    html.P(
                        _clean(s.summary_text),
                        style={"fontSize": "0.85rem", "marginBottom": "4px"},
                    ),
                    html.Hr(style={"margin": "6px 0"}),
                ]))
            daily_summary = html.Div(summary_content)
        else:
            daily_summary = html.P("No daily summaries available. Run the AI summarizer to generate.",
                                    className="text-muted")

        # ─── Map ─────────────────────────────────────────────────────
        geo_events = [e for e in events if e.latitude and e.longitude]
        if geo_events:
            try:
                from ui.components.map_view import create_event_map
                map_component = create_event_map(geo_events)
            except Exception:
                map_component = html.P("Map unavailable.", className="text-muted")
        else:
            map_component = html.P("No geolocated events found.", className="text-muted")

        return metrics, event_list, daily_summary, map_component

    finally:
        session.close()


# ─── Detail panel (pattern-matching callback) ────────────────────────────────
@callback(
    Output("geo-detail-header", "children"),
    Output("geo-detail-body", "children"),
    Input({"type": "geo-event-item", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def show_event_detail(n_clicks):
    if not ctx.triggered_id or not any(n_clicks):
        return no_update, no_update

    event_id = ctx.triggered_id["index"]
    session = get_session()
    try:
        event = session.query(GeopoliticalEvent).get(event_id)
        if not event:
            return "Event not found", html.P("Could not load event.")

        header = _clean((event.headline or "No headline")[:150])
        ts = event.timestamp.strftime("%Y-%m-%d %H:%M") if event.timestamp else "Unknown"
        cat = (event.category or "unknown").replace("_", " ").title()
        sev = event.severity or 0
        impact = event.supply_impact_mbd or 0
        loc = event.location_name or "Unknown"

        body = html.Div([
            dbc.Row([
                dbc.Col([
                    dbc.Badge(f"Severity: {sev}/10",
                              color="danger" if sev >= 7 else "warning" if sev >= 4 else "info"),
                    dbc.Badge(f"Impact: {impact:.1f} mbd", color="secondary", className="ms-2"),
                    dbc.Badge(cat, color="primary", className="ms-2"),
                ]),
            ], className="mb-2"),
            html.P([html.Strong("Date: "), ts], className="mb-1"),
            html.P([html.Strong("Location: "), loc], className="mb-1"),
            html.Hr(),
            html.P(_clean(event.summary or "No detailed summary available."),
                    style={"whiteSpace": "pre-wrap", "fontSize": "0.9rem"}),
            html.Hr(),
            html.A("Source", href=event.source_url, target="_blank",
                    className="btn btn-sm btn-outline-info") if event.source_url else html.Span(),
        ])
        return header, body

    finally:
        session.close()
