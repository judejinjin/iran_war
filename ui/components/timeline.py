"""
Timeline Component — event timeline visualization.
"""

import plotly.graph_objects as go

from db.database import get_session, GeopoliticalEvent


def create_event_timeline(start_date, end_date, category=None):
    """
    Create a Plotly timeline of geopolitical events.

    Returns:
        go.Figure with events plotted by date and severity.
    """
    session = get_session()
    try:
        from datetime import datetime
        q = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.timestamp >= datetime.combine(start_date, datetime.min.time()),
            GeopoliticalEvent.timestamp <= datetime.combine(end_date, datetime.max.time()),
        )
        if category and category != "ALL":
            q = q.filter(GeopoliticalEvent.category == category)

        events = q.order_by(GeopoliticalEvent.timestamp).all()

        fig = go.Figure()
        fig.update_layout(
            template="oil_dark",
            title="Event Timeline",
            xaxis_title="Date",
            yaxis_title="Severity",
            height=300,
        )

        if events:
            colors = {
                "geopolitical_development": "#4488CC",
                "military_operations": "#CC4444",
                "infrastructure_damage": "#FF8800",
                "production_shutin": "#FFCC00",
                "shipment_disruption": "#CC44CC",
            }
            fig.add_trace(go.Scatter(
                x=[e.timestamp for e in events],
                y=[e.severity or 0 for e in events],
                mode="markers",
                marker=dict(
                    size=[max(5, (e.severity or 0) * 2) for e in events],
                    color=[colors.get(e.category, "#888") for e in events],
                ),
                text=[(e.headline or "")[:60] for e in events],
                hovertemplate="%{text}<br>Severity: %{y}<extra></extra>",
            ))

        return fig

    finally:
        session.close()


def create_supply_impact_timeline(start_date, end_date):
    """
    Create a Plotly chart showing cumulative supply impact over time.

    Returns:
        go.Figure with supply impact stacked by category.
    """
    session = get_session()
    try:
        from datetime import datetime
        from collections import defaultdict

        events = session.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.timestamp >= datetime.combine(start_date, datetime.min.time()),
            GeopoliticalEvent.timestamp <= datetime.combine(end_date, datetime.max.time()),
            GeopoliticalEvent.supply_impact_mbd > 0,
        ).order_by(GeopoliticalEvent.timestamp).all()

        fig = go.Figure()
        fig.update_layout(
            template="oil_dark",
            title="Cumulative Supply Impact (mbd)",
            xaxis_title="Date",
            yaxis_title="Supply Impact (mbd)",
            height=300,
        )

        if events:
            dates = [e.timestamp for e in events]
            impacts = [e.supply_impact_mbd or 0 for e in events]
            cumulative = []
            running = 0
            for i in impacts:
                running += i
                cumulative.append(running)

            fig.add_trace(go.Scatter(
                x=dates, y=cumulative,
                mode="lines+markers",
                name="Cumulative Impact",
                fill="tozeroy",
            ))

        return fig

    finally:
        session.close()
