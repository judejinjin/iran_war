"""
Physical Crude Tab Callbacks — Dubai (DUB) spot price history and differentials.
"""

from datetime import date, datetime
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output

from db.database import get_session, FuturesCurve
from sqlalchemy import func as sa_func

# ─── Colour palette ──────────────────────────────────────────────────────────
_COLORS = {
    "DUB":  "#F9CA24",   # gold — Dubai
    "CL":   "#FF6B35",   # orange — WTI
    "COIL": "#1E90FF",   # blue — Brent
}
_LABELS = {
    "DUB":  "Dubai (DUB)",
    "CL":   "WTI (CL)",
    "COIL": "Brent (COIL)",
}


def _empty(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="oil_dark",
        title=title,
        annotations=[dict(
            text="No data available — run backfill to populate",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#888"),
        )],
    )
    return fig


def _front_month_series(session, symbol: str, start: date, end: date):
    """Return [(date, price)] for the front contract month of *symbol*."""
    subq = session.query(
        FuturesCurve.date,
        sa_func.min(FuturesCurve.contract_month).label("front"),
    ).filter(
        FuturesCurve.symbol == symbol,
        FuturesCurve.date >= start,
        FuturesCurve.date <= end,
    ).group_by(FuturesCurve.date).subquery()

    rows = session.query(FuturesCurve).join(
        subq,
        (FuturesCurve.date == subq.c.date) &
        (FuturesCurve.contract_month == subq.c.front) &
        (FuturesCurve.symbol == symbol),
    ).order_by(FuturesCurve.date).all()

    return [(r.date, r.settlement_price) for r in rows if r.settlement_price]


@callback(
    Output("physical-metrics-row",     "children"),
    Output("physical-dubai-chart",     "figure"),
    Output("physical-diff-chart",      "figure"),
    Input("physical-date-range",       "start_date"),
    Input("physical-date-range",       "end_date"),
    Input("physical-benchmark-toggle", "value"),
    Input("auto-refresh",              "n_intervals"),
)
def update_physical(start_date, end_date, benchmarks, _n):
    session = get_session()

    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        benchmarks = benchmarks or []

        # ── Summary metric cards ──────────────────────────────────────────
        metrics = []
        for sym in ["DUB", "CL", "COIL"]:
            latest = (
                session.query(FuturesCurve)
                .filter(FuturesCurve.symbol == sym)
                .order_by(FuturesCurve.date.desc(), FuturesCurve.contract_month)
                .first()
            )
            price_str = (
                f"${latest.settlement_price:.2f}" if latest and latest.settlement_price else "N/A"
            )
            date_str = latest.date.strftime("%b %d") if latest else ""
            metrics.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(_LABELS[sym], className="text-muted"),
                html.H4(price_str, style={"color": _COLORS[sym]}),
                html.Small(date_str, className="text-muted"),
            ])), width=4))

        # ── Dubai chart + benchmark overlays ─────────────────────────────
        dub_pts = _front_month_series(session, "DUB", start_date, end_date)
        dubai_fig = go.Figure()
        dubai_fig.update_layout(
            template="oil_dark",
            title="Dubai Crude Monthly Spot vs WTI / Brent",
            xaxis_title="Date",
            yaxis_title="Price ($/bbl)",
            height=380,
            hovermode="x unified",
        )
        if dub_pts:
            dubai_fig.add_trace(go.Scatter(
                x=[p[0] for p in dub_pts], y=[p[1] for p in dub_pts],
                mode="lines+markers", name="Dubai (DUB)",
                line=dict(color=_COLORS["DUB"], width=2),
                marker=dict(symbol="circle", size=5),
            ))
            for sym in benchmarks:
                pts = _front_month_series(session, sym, start_date, end_date)
                if pts:
                    dubai_fig.add_trace(go.Scatter(
                        x=[p[0] for p in pts], y=[p[1] for p in pts],
                        mode="lines", name=_LABELS[sym],
                        line=dict(color=_COLORS[sym], width=1.5, dash="dot"),
                    ))
        else:
            dubai_fig = _empty("Dubai Crude — no data (run FRED backfill)")

        # ── Dubai differentials (Dubai − WTI and Dubai − Brent) ──────────
        dub_map = dict(dub_pts)
        diff_fig = go.Figure()
        diff_fig.update_layout(
            template="oil_dark",
            title="Physical Differentials — Dubai minus Benchmark",
            xaxis_title="Date",
            yaxis_title="Differential ($/bbl)",
            height=350,
            hovermode="x unified",
        )
        diff_fig.add_hline(y=0, line_dash="dash", line_color="#666", line_width=1)

        for sym in ["CL", "COIL"]:
            bench_pts = _front_month_series(session, sym, start_date, end_date)
            bench_map = dict(bench_pts)
            common = sorted(set(dub_map) & set(bench_map))
            if common:
                diffs = [dub_map[d] - bench_map[d] for d in common]
                diff_fig.add_trace(go.Scatter(
                    x=common, y=diffs,
                    mode="lines+markers",
                    name=f"Dubai \u2212 {_LABELS[sym]}",
                    line=dict(
                        color=_COLORS["DUB"] if sym == "CL" else "#C0392B",
                        width=1.5,
                    ),
                    marker=dict(size=4),
                ))

        if not dub_map:
            diff_fig = _empty("Dubai Differentials — no Dubai data")

        return metrics, dubai_fig, diff_fig

    finally:
        session.close()



def _empty(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="oil_dark",
        title=title,
        annotations=[dict(
            text="No data available — run backfill to populate",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#888"),
        )],
    )
    return fig


def _front_month_series(session, symbol: str, start: date, end: date):
    """Return [(date, price)] for the front contract month of *symbol*."""
    subq = session.query(
        FuturesCurve.date,
        sa_func.min(FuturesCurve.contract_month).label("front"),
    ).filter(
        FuturesCurve.symbol == symbol,
        FuturesCurve.date >= start,
        FuturesCurve.date <= end,
    ).group_by(FuturesCurve.date).subquery()

    rows = session.query(FuturesCurve).join(
        subq,
        (FuturesCurve.date == subq.c.date) &
        (FuturesCurve.contract_month == subq.c.front) &
        (FuturesCurve.symbol == symbol),
    ).order_by(FuturesCurve.date).all()

    return [(r.date, r.settlement_price) for r in rows if r.settlement_price]

