"""
Physical Crude Tab Callbacks â€” Dated Brent (multi-source) and Dubai spot prices.

Outputs:
  physical-metrics-row   â€” 4 metric cards: Dated Brent, WTI, ICE Brent, Dubai
  physical-brent-header  â€” dynamic card header showing chosen source
  physical-brent-chart   â€” Dated Brent price history from selected source
  physical-basis-chart   â€” Dated Brent minus ICE Brent futures (COIL) basis
  physical-dubai-chart   â€” Dubai monthly spot vs benchmark overlays
  physical-diff-chart    â€” Dubai minus WTI / Dubai minus COIL differentials
"""

from datetime import date, datetime
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output

from db.database import get_session, FuturesCurve, PhysicalPrice
from sqlalchemy import func as sa_func

# â”€â”€â”€ Colour / label palettes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_COLORS = {
    "DATED_BRENT_FRED": "#00D2FF",   # cyan  â€” FRED Dated Brent
    "DATED_BRENT_EIA":  "#00FF88",   # green â€” EIA Dated Brent
    "DATED_BRENT_IMF":  "#FF9F43",   # amber â€” IMF Dated Brent
    "DUB":              "#F9CA24",   # gold  â€” Dubai
    "CL":               "#FF6B35",   # orange â€” WTI
    "COIL":             "#1E90FF",   # blue  â€” ICE Brent futures
    "BASIS":            "#E84393",   # pink  â€” Brent basis
}

_SOURCE_LABELS = {
    "FRED": "Dated Brent â€” FRED (DCOILBRENTEU, daily 1987+)",
    "EIA":  "Dated Brent â€” EIA direct (RBRTED, daily, lower lag)",
    "IMF":  "Dated Brent â€” IMF (POILBREUSDM, monthly 1990+)",
}
_SOURCE_COLOR = {
    "FRED": _COLORS["DATED_BRENT_FRED"],
    "EIA":  _COLORS["DATED_BRENT_EIA"],
    "IMF":  _COLORS["DATED_BRENT_IMF"],
}
_LABELS = {
    "DUB":  "Dubai (DUB)",
    "CL":   "WTI (CL)",
    "COIL": "ICE Brent (COIL)",
}


# â”€â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _empty(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="oil_dark",
        title=title,
        annotations=[dict(
            text="No data available â€” run backfill to populate",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#888"),
        )],
    )
    return fig


def _physical_series(session, source: str, start: date, end: date):
    """Return [(date, price)] from physical_prices for DATED_BRENT / chosen source."""
    rows = (
        session.query(PhysicalPrice)
        .filter(
            PhysicalPrice.symbol == "DATED_BRENT",
            PhysicalPrice.source == source,
            PhysicalPrice.date >= start,
            PhysicalPrice.date <= end,
        )
        .order_by(PhysicalPrice.date)
        .all()
    )
    return [(r.date, r.price) for r in rows if r.price is not None]


def _front_month_series(session, symbol: str, start: date, end: date):
    """Return [(date, price)] for the front contract month of *symbol*."""
    subq = (
        session.query(
            FuturesCurve.date,
            sa_func.min(FuturesCurve.contract_month).label("front"),
        )
        .filter(
            FuturesCurve.symbol == symbol,
            FuturesCurve.date >= start,
            FuturesCurve.date <= end,
        )
        .group_by(FuturesCurve.date)
        .subquery()
    )
    rows = (
        session.query(FuturesCurve)
        .join(
            subq,
            (FuturesCurve.date == subq.c.date)
            & (FuturesCurve.contract_month == subq.c.front)
            & (FuturesCurve.symbol == symbol),
        )
        .order_by(FuturesCurve.date)
        .all()
    )
    return [(r.date, r.settlement_price) for r in rows if r.settlement_price]


def _latest_physical(session, source: str):
    """Return (price, date) of most recent DATED_BRENT row for the given source."""
    row = (
        session.query(PhysicalPrice)
        .filter(
            PhysicalPrice.symbol == "DATED_BRENT",
            PhysicalPrice.source == source,
        )
        .order_by(PhysicalPrice.date.desc())
        .first()
    )
    return (row.price, row.date) if row else (None, None)


def _latest_futures(session, symbol: str):
    """Return (price, date) of most recent front-month price for *symbol*."""
    row = (
        session.query(FuturesCurve)
        .filter(FuturesCurve.symbol == symbol)
        .order_by(FuturesCurve.date.desc(), FuturesCurve.contract_month)
        .first()
    )
    return (row.settlement_price, row.date) if row else (None, None)


# â”€â”€â”€ Main callback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@callback(
    Output("physical-metrics-row",  "children"),
    Output("physical-brent-header", "children"),
    Output("physical-brent-chart",  "figure"),
    Output("physical-basis-chart",  "figure"),
    Output("physical-dubai-chart",  "figure"),
    Output("physical-diff-chart",   "figure"),
    Input("physical-date-range",       "start_date"),
    Input("physical-date-range",       "end_date"),
    Input("physical-benchmark-toggle", "value"),
    Input("physical-brent-source",     "value"),
    Input("auto-refresh",              "n_intervals"),
)
def update_physical(start_date, end_date, benchmarks, brent_source, _n):
    session = get_session()
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        benchmarks = benchmarks or []
        brent_source = brent_source or "FRED"

        # â”€â”€ Metric cards â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        metrics = []

        bp, bd = _latest_physical(session, brent_source)
        metrics.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.H6(f"Dated Brent ({brent_source})", className="text-muted"),
            html.H4(f"${bp:.2f}" if bp else "N/A",
                    style={"color": _SOURCE_COLOR[brent_source]}),
            html.Small(bd.strftime("%b %d") if bd else "", className="text-muted"),
        ])), width=3))

        for sym in ["CL", "COIL", "DUB"]:
            p, d = _latest_futures(session, sym)
            metrics.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(_LABELS[sym], className="text-muted"),
                html.H4(f"${p:.2f}" if p else "N/A",
                        style={"color": _COLORS[sym]}),
                html.Small(d.strftime("%b %d") if d else "", className="text-muted"),
            ])), width=3))

        # â”€â”€ Dated Brent chart â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        brent_pts = _physical_series(session, brent_source, start_date, end_date)
        brent_color = _SOURCE_COLOR[brent_source]
        # Monthly IMF data looks better with markers; daily = lines only
        mode = "lines+markers" if brent_source == "IMF" else "lines"

        brent_fig = go.Figure()
        brent_fig.update_layout(
            template="oil_dark",
            title=_SOURCE_LABELS[brent_source],
            xaxis_title="Date",
            yaxis_title="Price ($/bbl)",
            height=380,
            hovermode="x unified",
        )

        if brent_pts:
            brent_fig.add_trace(go.Scatter(
                x=[p[0] for p in brent_pts],
                y=[p[1] for p in brent_pts],
                mode=mode,
                name=f"Dated Brent ({brent_source})",
                line=dict(color=brent_color, width=2),
                marker=dict(symbol="circle",
                            size=5 if brent_source == "IMF" else 3),
            ))
            for sym in benchmarks:
                pts = _front_month_series(session, sym, start_date, end_date)
                if pts:
                    brent_fig.add_trace(go.Scatter(
                        x=[p[0] for p in pts],
                        y=[p[1] for p in pts],
                        mode="lines",
                        name=_LABELS[sym],
                        line=dict(color=_COLORS[sym], width=1.5, dash="dot"),
                    ))
        else:
            brent_fig = _empty(
                f"Dated Brent ({brent_source}) â€” no data (run dated_brent backfill)"
            )

        # â”€â”€ Brent Physical Basis (Dated Brent âˆ’ COIL) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        basis_fig = go.Figure()
        basis_fig.update_layout(
            template="oil_dark",
            title="Brent Physical Basis â€” Dated Brent minus ICE Futures (COIL)",
            xaxis_title="Date",
            yaxis_title="Basis ($/bbl)",
            height=280,
            hovermode="x unified",
        )
        basis_fig.add_hline(y=0, line_dash="dash", line_color="#555", line_width=1)

        if brent_pts:
            coil_pts = _front_month_series(session, "COIL", start_date, end_date)
            if coil_pts:
                brent_map = dict(brent_pts)
                coil_map = dict(coil_pts)
                common = sorted(set(brent_map) & set(coil_map))
                if common:
                    basis = [brent_map[d] - coil_map[d] for d in common]
                    basis_fig.add_trace(go.Scatter(
                        x=common,
                        y=basis,
                        mode="lines",
                        name=f"Basis ({brent_source} \u2212 COIL)",
                        line=dict(color=_COLORS["BASIS"], width=2),
                        fill="tozeroy",
                        fillcolor="rgba(232,67,147,0.12)",
                    ))
                else:
                    basis_fig = _empty("Brent Basis â€” no overlapping dates between sources")
            else:
                basis_fig = _empty("Brent Basis â€” no COIL futures data")
        else:
            basis_fig = _empty("Brent Basis â€” no Dated Brent data (run dated_brent backfill)")

        # â”€â”€ Dubai chart + benchmark overlays â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        dub_pts = _front_month_series(session, "DUB", start_date, end_date)
        dubai_fig = go.Figure()
        dubai_fig.update_layout(
            template="oil_dark",
            title="Dubai Crude Monthly Spot vs WTI / Brent",
            xaxis_title="Date",
            yaxis_title="Price ($/bbl)",
            height=350,
            hovermode="x unified",
        )
        if dub_pts:
            dubai_fig.add_trace(go.Scatter(
                x=[p[0] for p in dub_pts],
                y=[p[1] for p in dub_pts],
                mode="lines+markers",
                name="Dubai (DUB)",
                line=dict(color=_COLORS["DUB"], width=2),
                marker=dict(symbol="circle", size=5),
            ))
            for sym in benchmarks:
                pts = _front_month_series(session, sym, start_date, end_date)
                if pts:
                    dubai_fig.add_trace(go.Scatter(
                        x=[p[0] for p in pts],
                        y=[p[1] for p in pts],
                        mode="lines",
                        name=_LABELS[sym],
                        line=dict(color=_COLORS[sym], width=1.5, dash="dot"),
                    ))
        else:
            dubai_fig = _empty("Dubai Crude â€” no data (run FRED backfill)")

        # â”€â”€ Dubai differentials â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        dub_map = dict(dub_pts)
        diff_fig = go.Figure()
        diff_fig.update_layout(
            template="oil_dark",
            title="Physical Differentials â€” Dubai minus Benchmark",
            xaxis_title="Date",
            yaxis_title="Differential ($/bbl)",
            height=280,
            hovermode="x unified",
        )
        diff_fig.add_hline(y=0, line_dash="dash", line_color="#555", line_width=1)

        for sym in ["CL", "COIL"]:
            bench_pts = _front_month_series(session, sym, start_date, end_date)
            bench_map = dict(bench_pts)
            common = sorted(set(dub_map) & set(bench_map))
            if common:
                diffs = [dub_map[d] - bench_map[d] for d in common]
                diff_fig.add_trace(go.Scatter(
                    x=common,
                    y=diffs,
                    mode="lines+markers",
                    name=f"Dubai \u2212 {_LABELS[sym]}",
                    line=dict(
                        color=_COLORS["DUB"] if sym == "CL" else "#C0392B",
                        width=1.5,
                    ),
                    marker=dict(size=4),
                ))

        if not dub_map:
            diff_fig = _empty("Dubai Differentials â€” no Dubai data")

        return (
            metrics,
            _SOURCE_LABELS[brent_source],
            brent_fig,
            basis_fig,
            dubai_fig,
            diff_fig,
        )

    finally:
        session.close()
