"""
Military Tab Callbacks — losses, escalation, deployments, map.
"""

from datetime import date, datetime
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, no_update

from db.database import (
    get_session, MilitaryEvent, MilitaryDeployment, MilitaryDailySummary,
)


@callback(
    Output("mil-metrics-row", "children"),
    Output("mil-losses-chart", "figure"),
    Output("mil-escalation-chart", "figure"),
    Output("mil-deployments-table", "children"),
    Output("mil-events-table", "children"),
    Output("mil-map-container", "children"),
    Input("mil-date-range", "start_date"),
    Input("mil-date-range", "end_date"),
    Input("mil-side-toggle", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_military(start_date, end_date, side_filter, _n):
    session = get_session()
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        sides = ["Iran", "Opposing"] if side_filter == "BOTH" else [side_filter]

        # ─── Daily Summaries ──────────────────────────────────────────
        q = session.query(MilitaryDailySummary).filter(
            MilitaryDailySummary.date >= start_date,
            MilitaryDailySummary.date <= end_date,
        )
        if side_filter != "BOTH":
            q = q.filter(MilitaryDailySummary.side == side_filter)
        summaries = q.order_by(MilitaryDailySummary.date).all()

        # ─── Metrics ─────────────────────────────────────────────────
        total_personnel = sum(s.total_personnel_losses or 0 for s in summaries)
        total_aircraft = sum(s.total_aircraft_losses or 0 for s in summaries)
        total_naval = sum(s.total_naval_losses or 0 for s in summaries)
        latest_escalation = summaries[-1].escalation_score if summaries and summaries[-1].escalation_score else 0
        active_deployed = sum(s.active_personnel_deployed or 0 for s in summaries[-2:]) if summaries else 0

        metrics = [
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Personnel Losses", className="text-muted"),
                html.H4(f"{total_personnel:,}"),
            ])), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Aircraft Losses", className="text-muted"),
                html.H4(str(total_aircraft)),
            ])), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Naval Losses", className="text-muted"),
                html.H4(str(total_naval)),
            ])), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Escalation Score", className="text-muted"),
                html.H4(str(latest_escalation)),
            ])), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("Active Deployed", className="text-muted"),
                html.H4(f"{active_deployed:,}"),
            ])), width=2),
        ]

        # ─── Losses Chart ────────────────────────────────────────────
        losses_fig = go.Figure()
        losses_fig.update_layout(
            template="oil_dark", title="Daily Losses",
            xaxis_title="Date", yaxis_title="Losses", height=400,
        )
        for side in sides:
            side_data = [s for s in summaries if s.side == side]
            if side_data:
                losses_fig.add_trace(go.Bar(
                    x=[s.date for s in side_data],
                    y=[s.total_personnel_losses or 0 for s in side_data],
                    name=f"{side} Personnel",
                ))

        # ─── Escalation Chart ────────────────────────────────────────
        esc_fig = go.Figure()
        esc_fig.update_layout(
            template="oil_dark", title="Escalation Score Over Time",
            xaxis_title="Date", yaxis_title="Score (1-10)", height=400,
        )
        for side in sides:
            side_data = [s for s in summaries if s.side == side]
            if side_data:
                esc_fig.add_trace(go.Scatter(
                    x=[s.date for s in side_data],
                    y=[s.escalation_score or 0 for s in side_data],
                    mode="lines+markers",
                    name=side,
                ))

        # ─── Deployments Table ───────────────────────────────────────
        dep_q = session.query(MilitaryDeployment).filter(
            MilitaryDeployment.date >= start_date,
            MilitaryDeployment.date <= end_date,
        )
        if side_filter != "BOTH":
            dep_q = dep_q.filter(MilitaryDeployment.side == side_filter)
        deployments = dep_q.order_by(MilitaryDeployment.date.desc()).limit(50).all()

        if deployments:
            dep_rows = []
            for d in deployments:
                dep_rows.append(html.Tr([
                    html.Td(str(d.date)),
                    html.Td(d.side),
                    html.Td(d.force_type or ""),
                    html.Td(d.unit_name or ""),
                    html.Td(f"{d.personnel_count:,}" if d.personnel_count else "N/A"),
                    html.Td(d.deployment_status or ""),
                    html.Td(d.region or ""),
                ]))
            dep_table = dbc.Table(
                [html.Thead(html.Tr([
                    html.Th("Date"), html.Th("Side"), html.Th("Force"),
                    html.Th("Unit"), html.Th("Personnel"), html.Th("Status"),
                    html.Th("Region"),
                ]))] + [html.Tbody(dep_rows)],
                bordered=True, hover=True, responsive=True, color="dark",
            )
        else:
            dep_table = html.P("No deployment data available.", className="text-muted")

        # ─── Military Events Table ───────────────────────────────────
        evt_q = session.query(MilitaryEvent).filter(
            MilitaryEvent.date >= start_date,
            MilitaryEvent.date <= end_date,
        )
        if side_filter != "BOTH":
            evt_q = evt_q.filter(MilitaryEvent.side == side_filter)
        mil_events = evt_q.order_by(MilitaryEvent.date.desc()).limit(50).all()

        if mil_events:
            evt_rows = []
            for e in mil_events:
                evt_rows.append(html.Tr([
                    html.Td(str(e.date)),
                    html.Td(e.side),
                    html.Td(e.event_type or ""),
                    html.Td(e.loss_type or ""),
                    html.Td(str(e.quantity) if e.quantity else "N/A"),
                    html.Td((e.headline or "")[:60]),
                ]))
            events_table = dbc.Table(
                [html.Thead(html.Tr([
                    html.Th("Date"), html.Th("Side"), html.Th("Type"),
                    html.Th("Loss"), html.Th("Qty"), html.Th("Headline"),
                ]))] + [html.Tbody(evt_rows)],
                bordered=True, hover=True, responsive=True, color="dark",
            )
        else:
            events_table = html.P("No military events recorded.", className="text-muted")

        # ─── Map ─────────────────────────────────────────────────────
        geo_events = [e for e in mil_events if e.latitude and e.longitude]
        if geo_events:
            try:
                from ui.components.map_view import create_military_map
                map_component = create_military_map(geo_events)
            except Exception:
                map_component = html.P("Map unavailable.", className="text-muted")
        else:
            map_component = html.P("No geolocated military events.", className="text-muted")

        return metrics, losses_fig, esc_fig, dep_table, events_table, map_component

    finally:
        session.close()
