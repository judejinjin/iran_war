"""
Infrastructure Tab Callbacks — damage map, timeline, supply impact, events,
country production, facility status table, waterfall, Hormuz panel.
"""

from datetime import date, datetime
import re as _re
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, ALL, ctx, no_update

from db.database import (
    get_session, GeopoliticalEvent, DailySummary,
    Facility, FacilityStatus, CountryProduction, HormuzStatus,
    ChokepointStatus, RegionSupplySummary,
)
from ui.components.map_view import create_infrastructure_map
from config import CHOKEPOINT_BASELINES

_HTML_TAG_RE = _re.compile(r"<[^>]+>")
_HTML_ENT_RE = _re.compile(r"&\w+;")
def _clean(text: str) -> str:
    if not text:
        return ""
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = _HTML_ENT_RE.sub("", text)
    return text.strip()


_COUNTRY_NAMES = {
    "IR": "Iran", "SA": "Saudi Arabia", "IQ": "Iraq", "AE": "UAE",
    "KW": "Kuwait", "QA": "Qatar", "OM": "Oman", "BH": "Bahrain",
}
_COUNTRY_ORDER = ["IR", "SA", "IQ", "AE", "KW", "QA", "OM", "BH"]

# ─── Facility keyword sets for filtering ─────────────────────────────────────
_FACILITY_KEYWORDS = {
    "refinery":    ["refinery", "refining", "cracker", "distillation"],
    "pipeline":    ["pipeline", "pipe", "conduit", "trunkline"],
    "terminal":    ["terminal", "port", "export terminal", "loading", "jetty", "dock"],
    "storage":     ["storage", "tank farm", "tank", "cavern", "spr", "stockpile"],
    "field":       ["field", "wellhead", "well", "production site", "platform", "rig"],
    "processing":  ["processing", "processor", "separation", "NGL"],
    "lng_plant":   ["lng", "liquefaction", "liquefied"],
}


def _matches_facility(event, facility_type):
    if facility_type == "ALL":
        return True
    keywords = _FACILITY_KEYWORDS.get(facility_type, [])
    text = ((event.headline or "") + " " + (event.summary or "") + " " +
            (event.location_name or "")).lower()
    return any(kw in text for kw in keywords)


# ─── Status colors ───────────────────────────────────────────────────────────
_STATUS_COLORS = {
    "operational": "success",
    "shut_in": "warning",
    "partial": "info",
    "damaged": "danger",
    "destroyed": "dark",
}
_STATUS_FG = {
    "operational": "#66BB6A",
    "shut_in": "#FFD600",
    "partial": "#4FC3F7",
    "damaged": "#FF5252",
    "destroyed": "#888888",
}


@callback(
    Output("infra-metrics-row", "children"),
    Output("infra-chokepoint-panels", "children"),
    Output("infra-chokepoint-timeline-chart", "figure"),
    Output("infra-country-production-chart", "figure"),
    Output("infra-waterfall-chart", "figure"),
    Output("infra-map-container", "children"),
    Output("infra-timeline-chart", "figure"),
    Output("infra-supply-impact-chart", "figure"),
    Output("infra-facility-table", "children"),
    Output("infra-events-list", "children"),
    Output("infra-daily-summary", "children"),
    Output("infra-data-quality-panel", "children"),
    Input("infra-date-range", "start_date"),
    Input("infra-date-range", "end_date"),
    Input("infra-facility-filter", "value"),
    Input("infra-severity-slider", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_infrastructure(start_date, end_date, facility_filter, min_severity, _n):
    session = get_session()

    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        # ─── Query infrastructure_damage events ──────────────────────
        events = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.category == "infrastructure_damage",
            GeopoliticalEvent.timestamp >= datetime.combine(start_date, datetime.min.time()),
            GeopoliticalEvent.timestamp <= datetime.combine(end_date, datetime.max.time()),
            GeopoliticalEvent.severity >= min_severity,
        ).order_by(GeopoliticalEvent.timestamp.desc()).all()

        filtered = [e for e in events if _matches_facility(e, facility_filter)]

        # ─── Metrics ─────────────────────────────────────────────────
        total = len(filtered)
        critical = sum(1 for e in filtered if (e.severity or 0) >= 7)
        avg_sev = sum(e.severity or 0 for e in filtered) / total if total else 0
        total_impact = sum(e.supply_impact_mbd or 0 for e in filtered)

        # Get latest region summary for headline metric
        rss = session.query(RegionSupplySummary).filter(
            RegionSupplySummary.date <= end_date
        ).order_by(RegionSupplySummary.date.desc()).first()

        offline_mbd = rss.total_offline_oil_mbd if rss else total_impact
        pct_global = rss.pct_global_supply_offline * 100 if rss else 0
        data_confidence = (rss.data_confidence or "model_only") if rss else "model_only"

        _CONFIDENCE_BADGE = {
            "eia_current":    ("success", "🟢 EIA Actuals"),
            "eia_calibrated": ("warning", "🟡 EIA Calibrated"),
            "model_only":     ("danger",  "🔴 Model Estimate"),
        }
        badge_color, badge_label = _CONFIDENCE_BADGE.get(
            data_confidence, ("secondary", "Unknown")
        )

        metrics = dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Damage Events", className="text-muted"),
                html.H4(str(total)),
            ]), color="dark"), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Critical (≥7)", className="text-muted"),
                html.H4(str(critical), className="text-danger"),
            ]), color="dark"), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Avg Severity", className="text-muted"),
                html.H4(f"{avg_sev:.1f}"),
            ]), color="dark"), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Oil Offline (mbd)", className="text-muted"),
                html.H4(f"{offline_mbd:.2f}", className="text-warning"),
                dbc.Badge(badge_label, color=badge_color,
                          className="mt-1", style={"fontSize": "0.7rem"}),
            ]), color="dark"), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("% Global Supply", className="text-muted"),
                html.H4(f"{pct_global:.1f}%", className="text-danger" if pct_global > 2 else ""),
            ]), color="dark"), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Facilities Hit", className="text-muted"),
                html.H4(str(len(set(
                    e.location_name for e in filtered if e.location_name
                )))),
            ]), color="dark"), width=2),
        ])

        # ─── Chokepoint Panels (all three) ──────────────────────────
        cp_cards = []
        _cp_status_colors = {
            "open": "success", "restricted": "warning",
            "partial_blockade": "danger", "full_blockade": "dark",
        }
        for cp_key, cp_cfg in CHOKEPOINT_BASELINES.items():
            cp_row = session.query(ChokepointStatus).filter(
                ChokepointStatus.chokepoint == cp_key,
                ChokepointStatus.date <= end_date,
            ).order_by(ChokepointStatus.date.desc()).first()

            if cp_row:
                color = _cp_status_colors.get(cp_row.status, "secondary")
                reduction_pct = (cp_row.reduction_pct or 0) * 100
                cape_text = ""
                if cp_row.cape_diversion_active:
                    cape_text = f" | Cape diversion: +{cp_row.effective_delay_days}d, +${cp_row.extra_freight_cost_per_bbl:.2f}/bbl"

                card = dbc.Card([
                    dbc.CardHeader([
                        dbc.Badge(cp_row.status.replace("_", " ").title(),
                                  color=color, className="me-2"),
                        html.Strong(cp_cfg["label"]),
                    ]),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Small("Oil Transit", className="text-muted d-block"),
                                html.Span(
                                    f"{cp_row.oil_transit_mbd or 0:.1f} / {cp_row.normal_oil_mbd or cp_cfg['normal_oil_mbd']:.0f} mbd",
                                    className="fw-bold",
                                ),
                            ], width=3),
                            dbc.Col([
                                html.Small("LNG Transit", className="text-muted d-block"),
                                html.Span(f"{cp_row.lng_transit_bcfd or 0:.1f} bcf/d"),
                            ], width=2),
                            dbc.Col([
                                html.Small("Reduction", className="text-muted d-block"),
                                html.Span(
                                    f"{reduction_pct:.0f}%",
                                    className="text-danger fw-bold" if reduction_pct > 10 else "",
                                ),
                            ], width=2),
                            dbc.Col([
                                html.Small("Incidents", className="text-muted d-block"),
                                html.Span(str(cp_row.naval_incidents or 0)),
                            ], width=2),
                            dbc.Col([
                                html.Small("Date", className="text-muted d-block"),
                                html.Span(str(cp_row.date)),
                            ], width=3),
                        ]),
                        html.Small(cape_text, className="text-info mt-1") if cape_text else html.Span(),
                    ]),
                ], color="dark", className="mb-2")
            else:
                card = dbc.Card([
                    dbc.CardHeader([
                        dbc.Badge("No Data", color="secondary", className="me-2"),
                        html.Strong(cp_cfg["label"]),
                    ]),
                    dbc.CardBody(html.P("No status data.", className="text-muted mb-0")),
                ], color="dark", className="mb-2")

            cp_cards.append(dbc.Col(card, width=4))

        chokepoint_panels = dbc.Row(cp_cards)

        # ─── Chokepoint Timeline Chart ───────────────────────────────
        cp_timeline_fig = go.Figure()
        cp_timeline_fig.update_layout(
            template="oil_dark",
            title="Chokepoint Transit Reduction Over Time (%)",
            xaxis_title="Date",
            yaxis_title="Reduction %",
            height=350,
            yaxis=dict(range=[0, 60]),
        )
        _cp_colors = {"hormuz": "#FF5252", "bab_el_mandeb": "#FFD600", "suez": "#4FC3F7"}
        for cp_key, cp_cfg in CHOKEPOINT_BASELINES.items():
            cp_rows = session.query(ChokepointStatus).filter(
                ChokepointStatus.chokepoint == cp_key,
                ChokepointStatus.date >= start_date,
                ChokepointStatus.date <= end_date,
            ).order_by(ChokepointStatus.date).all()
            if cp_rows:
                cp_timeline_fig.add_trace(go.Scatter(
                    x=[r.date for r in cp_rows],
                    y=[(r.reduction_pct or 0) * 100 for r in cp_rows],
                    mode="lines+markers",
                    name=cp_cfg["label"],
                    line=dict(color=_cp_colors.get(cp_key, "#888"), width=2),
                    marker=dict(size=5),
                ))

        # ─── Country Production Chart ────────────────────────────────
        country_fig = go.Figure()
        country_fig.update_layout(
            template="oil_dark",
            title="Country Oil Production — Baseline vs Current (mbd)",
            xaxis_title="Country",
            yaxis_title="Oil Production (mbd)",
            height=400,
            barmode="group",
        )

        cp_rows = session.query(CountryProduction).filter(
            CountryProduction.date <= end_date
        ).order_by(CountryProduction.date.desc()).all()

        # Get latest date per country
        latest_cp = {}
        for r in cp_rows:
            if r.country not in latest_cp:
                latest_cp[r.country] = r

        if latest_cp:
            countries = [c for c in _COUNTRY_ORDER if c in latest_cp]
            names = [_COUNTRY_NAMES.get(c, c) for c in countries]
            baselines = [latest_cp[c].baseline_oil_mbd for c in countries]
            currents = [latest_cp[c].current_oil_mbd for c in countries]
            shut_ins = [latest_cp[c].shut_in_oil_mbd or 0 for c in countries]
            damaged = [latest_cp[c].damaged_oil_mbd or 0 for c in countries]

            country_fig.add_trace(go.Bar(
                x=names, y=baselines, name="Baseline",
                marker_color="#4FC3F7", opacity=0.5,
            ))
            country_fig.add_trace(go.Bar(
                x=names, y=currents, name="Model Current",
                marker_color=[
                    "#FF8800" if abs((latest_cp[c].blended_oil_mbd or 0) - (latest_cp[c].current_oil_mbd or 0)) /
                    max(latest_cp[c].current_oil_mbd or 1, 0.001) > 0.15
                    else "#66BB6A"
                    for c in countries
                ],
            ))
            country_fig.add_trace(go.Bar(
                x=names, y=shut_ins, name="Shut-in",
                marker_color="#FFD600",
            ))
            country_fig.add_trace(go.Bar(
                x=names, y=damaged, name="Damaged",
                marker_color="#FF5252",
            ))

            # EIA actual overlay — diamond markers where data exists
            eia_names, eia_vals, eia_dates = [], [], []
            for c in countries:
                cp_r = latest_cp[c]
                if cp_r.eia_actual_oil_mbd is not None:
                    eia_names.append(_COUNTRY_NAMES.get(c, c))
                    eia_vals.append(cp_r.eia_actual_oil_mbd)
                    lag = f"{cp_r.eia_lag_days}d ago" if cp_r.eia_lag_days is not None else ""
                    eia_dates.append(
                        f"EIA {cp_r.eia_source_date} ({lag})" if cp_r.eia_source_date else "EIA"
                    )
            if eia_vals:
                country_fig.add_trace(go.Scatter(
                    x=eia_names, y=eia_vals,
                    mode="markers",
                    name="EIA Actual",
                    marker=dict(symbol="diamond", size=12, color="#FFFFFF",
                                line=dict(color="#1E90FF", width=2)),
                    text=eia_dates,
                    hovertemplate="%{x}: %{y:.2f} mbd<br>%{text}<extra>EIA Actual</extra>",
                ))

        # ─── Supply Waterfall Chart ──────────────────────────────────
        waterfall_fig = go.Figure()
        waterfall_fig.update_layout(
            template="oil_dark",
            title="Regional Supply Waterfall (mbd)",
            yaxis_title="Oil (mbd)",
            height=400,
        )

        if rss:
            waterfall_fig.add_trace(go.Waterfall(
                x=["Baseline", "Shut-in", "Damaged", "Sanctions", "Hormuz", "Bab el-Mandeb", "Current"],
                measure=["absolute", "relative", "relative", "relative", "relative", "relative", "total"],
                y=[
                    rss.total_baseline_oil_mbd,
                    -(rss.total_shut_in_oil_mbd or 0),
                    -(rss.total_damaged_oil_mbd or 0),
                    -(rss.total_sanctions_oil_mbd or 0),
                    -(rss.total_hormuz_blocked_mbd or 0),
                    -(rss.total_bab_el_mandeb_blocked_mbd or 0),
                    0,  # total computed automatically
                ],
                connector=dict(line=dict(color="#888")),
                increasing=dict(marker=dict(color="#66BB6A")),
                decreasing=dict(marker=dict(color="#FF5252")),
                totals=dict(marker=dict(color="#4FC3F7")),
                text=[
                    f"{rss.total_baseline_oil_mbd:.1f}",
                    f"-{rss.total_shut_in_oil_mbd or 0:.1f}",
                    f"-{rss.total_damaged_oil_mbd or 0:.1f}",
                    f"-{rss.total_sanctions_oil_mbd or 0:.1f}",
                    f"-{rss.total_hormuz_blocked_mbd or 0:.1f}",
                    f"-{rss.total_bab_el_mandeb_blocked_mbd or 0:.1f}",
                    f"{rss.total_current_oil_mbd:.1f}",
                ],
                textposition="outside",
            ))

        # ─── Infrastructure Map ──────────────────────────────────────
        infra_map = create_infrastructure_map(filtered, height="500px")

        # ─── Damage Timeline Chart ───────────────────────────────────
        timeline_fig = go.Figure()
        timeline_fig.update_layout(
            template="oil_dark",
            title="Infrastructure Damage Events Over Time",
            xaxis_title="Date",
            yaxis_title="Severity",
            height=350,
        )

        if filtered:
            colors = []
            for e in filtered:
                s = e.severity or 0
                if s >= 7:
                    colors.append("#FF4444")
                elif s >= 4:
                    colors.append("#FF8800")
                else:
                    colors.append("#4488CC")

            timeline_fig.add_trace(go.Scatter(
                x=[e.timestamp for e in filtered],
                y=[e.severity or 0 for e in filtered],
                mode="markers",
                marker=dict(
                    size=[max(8, (e.severity or 1) * 2.5) for e in filtered],
                    color=colors,
                    line=dict(width=1, color="#FFF"),
                ),
                text=[f"{(e.headline or '')[:60]}<br>Impact: {e.supply_impact_mbd or 0:.2f} mbd"
                      for e in filtered],
                hovertemplate="%{text}<br>Severity: %{y}<extra></extra>",
                name="Damage Events",
            ))

        # ─── Cumulative Supply Impact Chart ──────────────────────────
        impact_fig = go.Figure()
        impact_fig.update_layout(
            template="oil_dark",
            title="Cumulative Supply Impact",
            xaxis_title="Date",
            yaxis_title="Supply Offline (mbd)",
            height=350,
        )

        if filtered:
            sorted_events = sorted(filtered, key=lambda e: e.timestamp)
            cum_impact = []
            running = 0
            dates = []
            for e in sorted_events:
                running += (e.supply_impact_mbd or 0)
                dates.append(e.timestamp)
                cum_impact.append(running)

            impact_fig.add_trace(go.Scatter(
                x=dates, y=cum_impact,
                mode="lines+markers",
                fill="tozeroy",
                fillcolor="rgba(255,68,68,0.15)",
                line=dict(color="#FF4444", width=2),
                marker=dict(size=6, color="#FF6B6B"),
                name="Cumulative mbd offline",
            ))

        # ─── Facility Status Table ───────────────────────────────────
        facility_table = _build_facility_table(session, end_date, facility_filter)

        # ─── Event List ──────────────────────────────────────────────
        if not filtered:
            event_items = [html.P("No infrastructure damage events found.",
                                  className="text-muted")]
        else:
            event_items = []
            for e in filtered:
                sev = e.severity or 0
                badge_color = "danger" if sev >= 7 else "warning" if sev >= 4 else "info"
                impact_txt = f" | {e.supply_impact_mbd:.2f} mbd" if e.supply_impact_mbd else ""

                event_items.append(
                    dbc.ListGroupItem(
                        [
                            dbc.Badge(f"{sev}", color=badge_color, className="me-2"),
                            html.Small(
                                e.timestamp.strftime("%m/%d %H:%M") if e.timestamp else "",
                                className="text-muted me-2",
                            ),
                            html.Span(
                                _clean((e.headline or "No headline")[:100]),
                                className="fw-bold",
                            ),
                            html.Small(
                                f" ({e.location_name or 'Unknown location'}{impact_txt})",
                                className="text-warning",
                            ),
                        ],
                        id={"type": "infra-event-item", "index": e.id},
                        action=True,
                        style={"cursor": "pointer"},
                    )
                )
            event_items = dbc.ListGroup(event_items, flush=True)

        # ─── Daily Summary ───────────────────────────────────────────
        summaries = session.query(DailySummary).filter(
            DailySummary.category == "infrastructure_damage",
            DailySummary.date >= start_date,
            DailySummary.date <= end_date,
        ).order_by(DailySummary.date.desc()).all()

        if summaries:
            summary_content = []
            for s in summaries:
                summary_content.append(html.Div([
                    html.H6(f"{s.date} — Avg Severity: {s.severity_avg or 'N/A'}, "
                            f"Supply Impact: {s.total_supply_impact_mbd or 0:.2f} mbd",
                            className="text-warning"),
                    html.P(_clean(s.summary_text or "No summary available."),
                           style={"whiteSpace": "pre-wrap"}),
                    html.Hr(),
                ]))
            daily = html.Div(summary_content, style={
                "maxHeight": "400px", "overflowY": "auto"
            })
        else:
            daily = html.P("No daily summaries yet.", className="text-muted")

        return (
            metrics, chokepoint_panels, cp_timeline_fig,
            country_fig, waterfall_fig,
            infra_map, timeline_fig, impact_fig, facility_table,
            event_items, daily,
            _build_data_quality_panel(latest_cp),
        )

    finally:
        session.close()


def _build_data_quality_panel(latest_cp: dict) -> html.Div:
    """Build the per-country EIA vs model data quality table."""
    _CONF_ICONS = {
        "eia_actual":    ("🟢", "success"),
        "eia_calibrated": ("🟡", "warning"),
        "model_only":    ("🔴", "danger"),
    }
    _COUNTRY_NAMES_DQ = {
        "IR": "Iran", "SA": "Saudi Arabia", "IQ": "Iraq", "AE": "UAE",
        "KW": "Kuwait", "QA": "Qatar", "OM": "Oman", "BH": "Bahrain",
    }

    if not latest_cp:
        return html.P("No country production data available.", className="text-muted")

    rows = []
    for country in ["IR", "SA", "IQ", "AE", "KW", "QA", "OM", "BH"]:
        cp_r = latest_cp.get(country)
        if cp_r is None:
            continue

        conf = cp_r.blended_confidence or "model_only"
        icon, color = _CONF_ICONS.get(conf, ("⚪", "secondary"))

        eia_str = f"{cp_r.eia_actual_oil_mbd:.2f} mbd" if cp_r.eia_actual_oil_mbd else "—"
        model_str = f"{cp_r.current_oil_mbd:.2f} mbd" if cp_r.current_oil_mbd else "—"
        blended_str = f"{cp_r.blended_oil_mbd:.2f} mbd" if cp_r.blended_oil_mbd else "—"

        # Divergence %
        if cp_r.eia_actual_oil_mbd and cp_r.current_oil_mbd and cp_r.current_oil_mbd > 0:
            delta = cp_r.eia_actual_oil_mbd - cp_r.current_oil_mbd
            delta_pct = delta / cp_r.current_oil_mbd * 100
            delta_str = f"{'+' if delta > 0 else ''}{delta:.2f} ({delta_pct:+.0f}%)"
            delta_color = "#FF8800" if abs(delta_pct) > 15 else "#888"
        else:
            delta_str, delta_color = "—", "#888"

        eia_date_str = str(cp_r.eia_source_date) if cp_r.eia_source_date else "—"
        lag_str = f"{cp_r.eia_lag_days}d" if cp_r.eia_lag_days is not None else "—"

        baseline_src = "EIA 6-mo avg" if cp_r.calibration_ratio else "Hardcoded"

        rows.append(html.Tr([
            html.Td(_COUNTRY_NAMES_DQ.get(country, country)),
            html.Td(baseline_src),
            html.Td(eia_str),
            html.Td(model_str),
            html.Td(delta_str, style={"color": delta_color}),
            html.Td(blended_str),
            html.Td(lag_str),
            html.Td([
                html.Span(icon + " "),
                dbc.Badge(conf.replace("_", " ").title(), color=color,
                          style={"fontSize": "0.7rem"}),
            ]),
        ]))

    if not rows:
        return html.P("No calibration data yet — run production tracker.", className="text-muted")

    table = dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Country"), html.Th("Baseline Source"),
                html.Th("EIA Actual"), html.Th("Model Est."),
                html.Th("Δ (EIA − Model)"), html.Th("Blended"),
                html.Th("EIA Lag"), html.Th("Confidence"),
            ])),
            html.Tbody(rows),
        ],
        bordered=True, hover=True, responsive=True, size="sm",
        className="table-dark",
        style={"fontSize": "0.83rem"},
    )
    return html.Div([
        html.P(
            "Baseline oil production is derived from the 6-month EIA monthly average where "
            "available. Blended estimate combines EIA actuals (when lag ≤90 days) with a "
            "model calibration ratio beyond that window. Orange bars on the chart indicate "
            ">15% divergence between EIA actual and model estimate.",
            className="text-muted small mb-2",
        ),
        table,
    ])


def _build_facility_table(session, as_of_date, facility_filter):
    """Build a Bootstrap table of facility statuses."""
    facilities = session.query(Facility).all()
    if facility_filter != "ALL":
        facilities = [f for f in facilities if f.facility_type == facility_filter]

    if not facilities:
        return html.P("No facilities match filter.", className="text-muted")

    # Get latest status for each facility on or before as_of_date
    rows = []
    for fac in facilities:
        fs = session.query(FacilityStatus).filter(
            FacilityStatus.facility_id == fac.id,
            FacilityStatus.date <= as_of_date,
        ).order_by(FacilityStatus.date.desc()).first()

        status = fs.status if fs else "operational"
        oil_off = fs.oil_offline_mbd if fs else 0
        gas_off = fs.gas_offline_bcfd if fs else 0
        dmg = fs.damage_pct if fs else 0
        recovery = fs.estimated_recovery_date if fs else None

        badge_color = _STATUS_COLORS.get(status, "secondary")

        rows.append(html.Tr([
            html.Td(_COUNTRY_NAMES.get(fac.country, fac.country)),
            html.Td(fac.name),
            html.Td(fac.facility_type.replace("_", " ").title()),
            html.Td(dbc.Badge(status.replace("_", " ").title(), color=badge_color)),
            html.Td(f"{fac.capacity_oil_mbd or 0:.2f}"),
            html.Td(f"{oil_off or 0:.2f}", className="text-danger" if oil_off else ""),
            html.Td(f"{(dmg or 0)*100:.0f}%", className="text-warning" if dmg else ""),
            html.Td(str(recovery) if recovery else "—"),
        ]))

    return dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Country"), html.Th("Facility"), html.Th("Type"),
                html.Th("Status"), html.Th("Cap (mbd)"), html.Th("Oil Off"),
                html.Th("Damage %"), html.Th("Recovery"),
            ])),
            html.Tbody(rows),
        ],
        bordered=True, hover=True, responsive=True, size="sm",
        className="table-dark",
    )


# ─── Event Detail Panel ──────────────────────────────────────────────────────
@callback(
    Output("infra-detail-header", "children"),
    Output("infra-detail-body", "children"),
    Input({"type": "infra-event-item", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def show_infra_detail(all_clicks):
    if not ctx.triggered_id or not any(all_clicks):
        return no_update, no_update

    event_id = ctx.triggered_id.get("index")
    if not event_id:
        return no_update, no_update

    session = get_session()
    try:
        event = session.query(GeopoliticalEvent).get(event_id)
        if not event:
            return "Not Found", html.P("Event not found.")

        sev = event.severity or 0
        badge_color = "danger" if sev >= 7 else "warning" if sev >= 4 else "info"

        header = html.Span([
            dbc.Badge(f"Severity {sev}", color=badge_color, className="me-2"),
            (event.headline or "Infrastructure Event")[:100],
        ])

        body = html.Div([
            dbc.Row([
                dbc.Col([
                    html.Strong("Date: "),
                    html.Span(event.timestamp.strftime("%Y-%m-%d %H:%M") if event.timestamp else "N/A"),
                ], width=4),
                dbc.Col([
                    html.Strong("Location: "),
                    html.Span(event.location_name or "Unknown"),
                ], width=4),
                dbc.Col([
                    html.Strong("Supply Impact: "),
                    html.Span(f"{event.supply_impact_mbd:.2f} mbd" if event.supply_impact_mbd else "N/A",
                              className="text-warning"),
                ], width=4),
            ], className="mb-3"),

            dbc.Row([
                dbc.Col([
                    html.Strong("Coordinates: "),
                    html.Span(f"{event.latitude:.4f}, {event.longitude:.4f}"
                              if event.latitude and event.longitude else "N/A"),
                ], width=4),
            ], className="mb-3"),

            html.Hr(),
            html.P(_clean(event.summary or "No detailed summary available."),
                   style={"whiteSpace": "pre-wrap"}),

            html.A("Source →", href=event.source_url, target="_blank",
                   className="btn btn-outline-warning btn-sm mt-2")
            if event.source_url else html.Span(),
        ])

        return header, body

    finally:
        session.close()
