"""
Crack Spread Tab Callbacks — US diesel crack spread vs WTI/Brent, 3-2-1 crack,
seasonal patterns, component prices, and distribution analysis.

Outputs:
  crack-metrics-row       — 4 KPI cards: diesel crack, 3-2-1, ULSD spot, 5yr avg
  crack-main-chart        — time series of all selected crack types
  crack-seasonal-chart    — current year vs 5-yr seasonal band (DOY basis)
  crack-components-chart  — ULSD $/bbl + WTI $/bbl price history
  crack-distribution-chart— histogram of diesel crack + current percentile marker
  crack-recent-table      — last 20 trading days tabular
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output

from db.database import get_session, CrackSpreadPrice, FuturesCurve, Spread
from sqlalchemy import func as sa_func

# ─── Colours ─────────────────────────────────────────────────────────────────
_COLORS = {
    "DIESEL_CRACK_WTI":   "#FF6B35",   # orange
    "DIESEL_CRACK_BRENT": "#1E90FF",   # blue
    "CRACK_321_WTI":      "#00D26A",   # green
    "ULSD":               "#F9CA24",   # gold
    "CL":                 "#FF6B35",   # orange (WTI)
    "COIL":               "#1E90FF",   # blue  (Brent)
    "BAND":               "rgba(255,107,53,0.15)",
    "BAND_LINE":          "rgba(255,107,53,0.4)",
}

_LABELS = {
    "DIESEL_CRACK_WTI":   "Diesel Crack vs WTI",
    "DIESEL_CRACK_BRENT": "Diesel Crack vs Brent",
    "CRACK_321_WTI":      "3-2-1 Crack vs WTI",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _empty(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="oil_dark",
        title=title,
        annotations=[dict(
            text="No data — run crack spread backfill to populate",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#888"),
        )],
    )
    return fig


def _crack_series(session, spread_type: str, start: date, end: date):
    """Return [(date, value)] for a given spread_type within the date range."""
    rows = (
        session.query(Spread)
        .filter(
            Spread.spread_type == spread_type,
            Spread.date >= start,
            Spread.date <= end,
        )
        .order_by(Spread.date)
        .all()
    )
    return [(r.date, r.spread_value) for r in rows if r.spread_value is not None]


def _crack_all(session, spread_type: str):
    """Return all historical [(date, value)] for distribution/seasonal calcs."""
    rows = (
        session.query(Spread)
        .filter(Spread.spread_type == spread_type)
        .order_by(Spread.date)
        .all()
    )
    return [(r.date, r.spread_value) for r in rows if r.spread_value is not None]


def _product_series(session, symbol: str, start: date, end: date):
    """Return [(date, price_per_bbl)] for ULSD or RBOB."""
    rows = (
        session.query(CrackSpreadPrice)
        .filter(
            CrackSpreadPrice.symbol == symbol,
            CrackSpreadPrice.date >= start,
            CrackSpreadPrice.date <= end,
        )
        .order_by(CrackSpreadPrice.date)
        .all()
    )
    return [(r.date, r.price_per_bbl) for r in rows if r.price_per_bbl is not None]


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


def _latest_spread(session, spread_type: str):
    """Return (value, date) of most recent row for spread_type."""
    row = (
        session.query(Spread)
        .filter(Spread.spread_type == spread_type)
        .order_by(Spread.date.desc())
        .first()
    )
    return (row.spread_value, row.date) if row else (None, None)


def _latest_product(session, symbol: str):
    """Return (price_per_bbl, date) of most recent CrackSpreadPrice row."""
    row = (
        session.query(CrackSpreadPrice)
        .filter(CrackSpreadPrice.symbol == symbol)
        .order_by(CrackSpreadPrice.date.desc())
        .first()
    )
    return (row.price_per_bbl, row.date) if row else (None, None)


def _seasonal_band(all_pts: list, current_year: int, lookback_years: int = 5):
    """
    Build day-of-year seasonal band from the past *lookback_years* of data.
    Returns (doy_list, p25_list, p75_list, median_list, current_pts).
    current_pts: [(doy, value)] for *current_year* only.
    """
    by_doy = defaultdict(list)
    current_pts = []
    cutoff = date(current_year - lookback_years, 1, 1)

    for dt, val in all_pts:
        doy = dt.timetuple().tm_yday
        if cutoff <= dt < date(current_year, 1, 1):
            by_doy[doy].append(val)
        elif dt.year == current_year:
            current_pts.append((doy, val))

    doys = sorted(by_doy.keys())
    p25, p75, median = [], [], []
    for doy in doys:
        vals = sorted(by_doy[doy])
        n = len(vals)
        p25.append(vals[max(0, int(n * 0.25))])
        p75.append(vals[min(n - 1, int(n * 0.75))])
        median.append(vals[n // 2])

    return doys, p25, p75, median, current_pts


def _percentile_rank(all_pts: list, current_val: float) -> float:
    """Return 0–100 percentile rank of current_val within all_pts values."""
    vals = [v for _, v in all_pts]
    if not vals:
        return 50.0
    below = sum(1 for v in vals if v < current_val)
    return round(100.0 * below / len(vals), 1)


# ─── Main Callback ────────────────────────────────────────────────────────────

@callback(
    Output("crack-metrics-row",        "children"),
    Output("crack-main-chart",         "figure"),
    Output("crack-seasonal-chart",     "figure"),
    Output("crack-components-chart",   "figure"),
    Output("crack-distribution-chart", "figure"),
    Output("crack-recent-table",       "children"),
    Input("crack-date-range",          "start_date"),
    Input("crack-date-range",          "end_date"),
    Input("crack-type-toggle",         "value"),
    Input("crack-seasonal-toggle",     "value"),
    Input("auto-refresh",              "n_intervals"),
)
def update_crack(start_date, end_date, crack_types, seasonal_opts, _n):
    session = get_session()
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        crack_types = crack_types or ["DIESEL_CRACK_WTI"]
        show_seasonal = "seasonal" in (seasonal_opts or [])

        # ── Metric Cards ─────────────────────────────────────────────────────
        metrics = []

        diesel_val, diesel_date = _latest_spread(session, "DIESEL_CRACK_WTI")
        crack321_val, _ = _latest_spread(session, "CRACK_321_WTI")
        ulsd_bbl, ulsd_date = _latest_product(session, "ULSD")

        # 5-year average diesel crack
        five_yr_ago = date.today() - timedelta(days=5 * 365)
        all_diesel = _crack_all(session, "DIESEL_CRACK_WTI")
        hist_vals = [v for dt, v in all_diesel if dt >= five_yr_ago]
        avg_5yr = round(sum(hist_vals) / len(hist_vals), 2) if hist_vals else None

        card_defs = [
            ("Diesel Crack (WTI)", diesel_val, diesel_date, "#FF6B35",
             f"${diesel_val:.2f}/bbl" if diesel_val else "N/A"),
            ("3-2-1 Crack (WTI)", crack321_val, None, "#00D26A",
             f"${crack321_val:.2f}/bbl" if crack321_val else "N/A"),
            ("ULSD Spot", ulsd_bbl, ulsd_date, "#F9CA24",
             f"${ulsd_bbl:.2f}/bbl" if ulsd_bbl else "N/A"),
            ("5-yr Avg Crack", avg_5yr, None, "#AAAAAA",
             f"${avg_5yr:.2f}/bbl" if avg_5yr else "N/A"),
        ]
        for label, val, dt_val, color, display in card_defs:
            date_str = dt_val.strftime("%b %d") if dt_val else ""
            metrics.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(label, className="text-muted"),
                html.H4(display, style={"color": color}),
                html.Small(date_str, className="text-muted"),
            ])), width=3))

        # ── Main Chart ────────────────────────────────────────────────────────
        main_fig = go.Figure()
        main_fig.update_layout(
            template="oil_dark",
            title="Crack Spreads — Historical Time Series",
            xaxis_title="Date",
            yaxis_title="Crack Spread ($/bbl)",
            height=400,
            hovermode="x unified",
        )
        main_fig.add_hline(y=0, line_dash="dash", line_color="#444", line_width=1)

        has_data = False
        for ct in crack_types:
            pts = _crack_series(session, ct, start_date, end_date)
            if pts:
                has_data = True
                main_fig.add_trace(go.Scatter(
                    x=[p[0] for p in pts],
                    y=[p[1] for p in pts],
                    mode="lines",
                    name=_LABELS[ct],
                    line=dict(color=_COLORS[ct], width=2),
                    hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f} $/bbl<extra></extra>",
                ))

        if not has_data:
            main_fig = _empty("Crack Spreads — no data (run crack_spread backfill)")

        # ── Seasonal Chart ────────────────────────────────────────────────────
        seasonal_fig = go.Figure()
        seasonal_fig.update_layout(
            template="oil_dark",
            title="Diesel Crack Seasonal Pattern — Current Year vs 5-Year Band (25th–75th pct)",
            xaxis_title="Day of Year",
            yaxis_title="Crack Spread ($/bbl)",
            height=300,
            hovermode="x unified",
        )

        if all_diesel:
            doys, p25, p75, median, current_pts = _seasonal_band(
                all_diesel, date.today().year
            )
            if doys:
                # 25–75 band
                seasonal_fig.add_trace(go.Scatter(
                    x=doys + doys[::-1],
                    y=p75 + p25[::-1],
                    fill="toself",
                    fillcolor=_COLORS["BAND"],
                    line=dict(color=_COLORS["BAND_LINE"], width=0),
                    name="5-yr 25th–75th pct",
                    hoverinfo="skip",
                    showlegend=show_seasonal,
                    visible=True if show_seasonal else "legendonly",
                ))
                # Median
                seasonal_fig.add_trace(go.Scatter(
                    x=doys,
                    y=median,
                    mode="lines",
                    name="5-yr Median",
                    line=dict(color=_COLORS["BAND_LINE"], width=1.5, dash="dot"),
                    visible=True if show_seasonal else "legendonly",
                ))
            # Current year
            if current_pts:
                seasonal_fig.add_trace(go.Scatter(
                    x=[p[0] for p in current_pts],
                    y=[p[1] for p in current_pts],
                    mode="lines",
                    name=f"{date.today().year} (current)",
                    line=dict(color=_COLORS["DIESEL_CRACK_WTI"], width=2.5),
                ))
        else:
            seasonal_fig = _empty("Seasonal Pattern — no historical data")

        # ── Components Chart ──────────────────────────────────────────────────
        comp_fig = go.Figure()
        comp_fig.update_layout(
            template="oil_dark",
            title="Crack Spread Components — ULSD Spot vs WTI Front Month ($/bbl)",
            xaxis_title="Date",
            yaxis_title="Price ($/bbl)",
            height=300,
            hovermode="x unified",
        )
        ulsd_pts = _product_series(session, "ULSD", start_date, end_date)
        wti_pts = _front_month_series(session, "CL", start_date, end_date)
        if ulsd_pts:
            comp_fig.add_trace(go.Scatter(
                x=[p[0] for p in ulsd_pts],
                y=[p[1] for p in ulsd_pts],
                mode="lines",
                name="ULSD ($/bbl)",
                line=dict(color=_COLORS["ULSD"], width=2),
            ))
        if wti_pts:
            comp_fig.add_trace(go.Scatter(
                x=[p[0] for p in wti_pts],
                y=[p[1] for p in wti_pts],
                mode="lines",
                name="WTI front-month ($/bbl)",
                line=dict(color=_COLORS["CL"], width=2, dash="dot"),
            ))
        if not ulsd_pts and not wti_pts:
            comp_fig = _empty("Components — no data (run crack_spread + fred backfill)")

        # ── Distribution Chart ────────────────────────────────────────────────
        dist_fig = go.Figure()
        dist_fig.update_layout(
            template="oil_dark",
            title="Diesel Crack vs WTI — Historical Distribution (Full History)",
            xaxis_title="Crack Spread ($/bbl)",
            yaxis_title="Frequency",
            height=280,
            hovermode="x",
        )
        if all_diesel:
            vals = [v for _, v in all_diesel]
            dist_fig.add_trace(go.Histogram(
                x=vals,
                nbinsx=60,
                name="Distribution",
                marker_color=_COLORS["DIESEL_CRACK_WTI"],
                opacity=0.7,
                hovertemplate="Crack: %{x:.1f} $/bbl<br>Count: %{y}<extra></extra>",
            ))
            if diesel_val is not None:
                pct = _percentile_rank(all_diesel, diesel_val)
                dist_fig.add_vline(
                    x=diesel_val,
                    line_color="#FFFFFF",
                    line_width=2,
                    line_dash="dash",
                    annotation_text=f"Current ${diesel_val:.1f} ({pct}th pct)",
                    annotation_position="top right",
                    annotation_font_color="#FFFFFF",
                )
        else:
            dist_fig = _empty("Distribution — no historical data")

        # ── Recent Table ──────────────────────────────────────────────────────
        recent_rows = (
            session.query(Spread)
            .filter(Spread.spread_type == "DIESEL_CRACK_WTI")
            .order_by(Spread.date.desc())
            .limit(20)
            .all()
        )
        if recent_rows:
            header = html.Thead(html.Tr([
                html.Th("Date"),
                html.Th("Diesel Crack vs WTI ($/bbl)"),
                html.Th("D/D Change"),
            ]))
            rows_html = []
            for i, r in enumerate(recent_rows):
                val = r.spread_value
                if i + 1 < len(recent_rows):
                    prev_val = recent_rows[i + 1].spread_value
                    chg = (val - prev_val) if (val is not None and prev_val is not None) else None
                    chg_color = "#00D26A" if (chg and chg > 0) else ("#FF4757" if (chg and chg < 0) else "#888")
                    chg_str = f"{'+' if chg and chg > 0 else ''}{chg:.2f}" if chg is not None else "—"
                else:
                    chg_color, chg_str = "#888", "—"
                rows_html.append(html.Tr([
                    html.Td(r.date.strftime("%Y-%m-%d")),
                    html.Td(f"${val:.2f}" if val is not None else "—"),
                    html.Td(chg_str, style={"color": chg_color}),
                ]))
            recent_table = dbc.Table(
                [header, html.Tbody(rows_html)],
                striped=True, hover=True, size="sm",
                style={"fontSize": "0.85rem"},
            )
        else:
            recent_table = html.P(
                "No crack spread data — run crack_spread backfill to populate.",
                className="text-muted",
            )

        return (
            metrics,
            main_fig,
            seasonal_fig,
            comp_fig,
            dist_fig,
            recent_table,
        )

    finally:
        session.close()
