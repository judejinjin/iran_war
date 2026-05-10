"""
SPR Tab Callbacks — query spr_levels, build all charts and the data table.
"""

from datetime import date, datetime, timedelta

import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, dash_table

from config import SPR_COUNTRIES, WAR_START_DATE, IEA_COLLECTIVE_ACTION
from db.database import get_session, SprLevel

# Colour palette — one per country
_COLORS = {
    "US":   "#2E86DE",
    "CN":   "#E74C3C",
    "JP":   "#F39C12",
    "DE":   "#27AE60",
    "FR":   "#8E44AD",
    "IT":   "#16A085",
    "KR":   "#D35400",
}

_WAR_START = datetime.strptime(WAR_START_DATE, "%Y-%m-%d").date()

# IEA collective action constants
_IEA_START      = datetime.strptime(IEA_COLLECTIVE_ACTION["agreed_date"], "%Y-%m-%d").date()
_IEA_DAYS       = IEA_COLLECTIVE_ACTION["release_days"]
_IEA_END        = _IEA_START + timedelta(days=_IEA_DAYS)
_IEA_COMMITTED  = IEA_COLLECTIVE_ACTION["commitments_mbbl"]   # {code: Mbbl}
# Implied daily release rate per country (Mbbl/day, positive = releasing)
_IEA_RATES      = {code: round(mbbl / _IEA_DAYS, 4) for code, mbbl in _IEA_COMMITTED.items()}


def _fmt(val, decimals=1):
    """Format a float or return 'N/A'."""
    if val is None:
        return "N/A"
    return f"{val:,.{decimals}f}"


def _compute_days_at_rate(rlist: list, window_weeks: int = 4) -> list:
    """
    For each row in rlist (sorted ascending by date) compute how many days
    the current SPR level can sustain releases at the rolling average rate:
      days_at_rate = spr_mbbl / |avg_daily_drawdown_over_window|
    Returns None when the SPR is flat or being refilled.
    """
    result = []
    for i, r in enumerate(rlist):
        if r.spr_mbbl is None:
            result.append(None)
            continue
        cutoff = r.date - timedelta(weeks=window_weeks)
        prior = [x for x in rlist[:i] if x.date >= cutoff and x.spr_mbbl is not None]
        if not prior:
            result.append(None)
            continue
        oldest = prior[0]
        elapsed = (r.date - oldest.date).days
        if elapsed == 0:
            result.append(None)
            continue
        rate_per_day = (r.spr_mbbl - oldest.spr_mbbl) / elapsed  # Mbbl/day; negative = drawdown
        if rate_per_day >= 0:
            result.append(None)  # flat or refilling
        else:
            result.append(round(r.spr_mbbl / abs(rate_per_day), 1))
    return result


@callback(
    Output("spr-metrics-row",      "children"),
    Output("spr-levels-chart",     "figure"),
    Output("spr-us-stacked-chart", "figure"),
    Output("spr-snapshot-chart",   "figure"),
    Output("spr-data-table",       "data"),
    Input("spr-date-range",       "start_date"),
    Input("spr-date-range",       "end_date"),
    Input("spr-chart-country",    "value"),
    Input("auto-refresh",         "n_intervals"),
)
def update_spr(start_date, end_date, chart_country, _n):
    session = get_session()
    all_countries = list(SPR_COUNTRIES.keys())
    # Single toggle drives stats, levels chart, and data table
    stats_code  = chart_country if chart_country else "US"
    chart_codes = [stats_code]
    try:
        # ── Parse dates ──────────────────────────────────────────────────
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        table_codes = [stats_code]

        # stats_code already set above from chart_country

        # ── Fetch all rows in date range for ALL countries (time-series charts) ───
        rows = (
            session.query(SprLevel)
            .filter(
                SprLevel.date >= start_date,
                SprLevel.date <= end_date,
                SprLevel.country_code.in_(all_countries),
            )
            .order_by(SprLevel.date)
            .all()
        )

        # ── Latest row per country up to end_date (ignores start_date) ───
        # Needed so international annual data (last point Dec 2025) always appears
        # in the snapshot chart and data table regardless of the chosen start.
        from sqlalchemy import func
        subq = (
            session.query(
                SprLevel.country_code,
                func.max(SprLevel.date).label("max_date"),
            )
            .filter(
                SprLevel.date <= end_date,
                SprLevel.country_code.in_(all_countries),
            )
            .group_by(SprLevel.country_code)
            .subquery()
        )
        latest_rows = (
            session.query(SprLevel)
            .join(subq, (SprLevel.country_code == subq.c.country_code) &
                        (SprLevel.date == subq.c.max_date))
            .all()
        )
        latest_by_country: dict[str, SprLevel] = {r.country_code: r for r in latest_rows}

        # Group by country
        by_country: dict[str, list[SprLevel]] = {}
        for r in rows:
            by_country.setdefault(r.country_code, []).append(r)

        # ── Full history per country up to end_date (for DAR + table) ────
        all_hist: dict[str, list[SprLevel]] = {}
        for code in all_countries:
            all_hist[code] = (
                session.query(SprLevel)
                .filter(SprLevel.country_code == code, SprLevel.date <= end_date)
                .order_by(SprLevel.date)
                .all()
            )
        _dar_map: dict[str, list] = {
            code: _compute_days_at_rate(rlist)
            for code, rlist in all_hist.items()
        }

        # ── Helper: latest row per country ────────────────────────────────
        def _latest(code: str) -> SprLevel | None:
            rlist = by_country.get(code, [])
            return rlist[-1] if rlist else None

        def _row_at_delta(code: str, days: int) -> SprLevel | None:
            """Return the row closest to (today - days)."""
            target = end_date - timedelta(days=days)
            rlist = by_country.get(code, [])
            candidates = [r for r in rlist if r.date <= target]
            return candidates[-1] if candidates else None

        # ── Key Metrics — driven by stats_code (= spr-table-country toggle) ─
        sc_latest  = _latest(stats_code)
        sc_1w      = _row_at_delta(stats_code, 7)
        sc_1m      = _row_at_delta(stats_code, 30)
        sc_war_start = (
            session.query(SprLevel)
            .filter(SprLevel.country_code == stats_code, SprLevel.date >= _WAR_START)
            .order_by(SprLevel.date)
            .first()
        )

        def _metric_card(title, value, subtitle=None, alert=False):
            color = "#e74c3c" if alert else "#e0e0e0"
            return dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(title, className="text-muted", style={"fontSize": "0.78rem"}),
                html.H4(value, style={"color": color}),
                html.Small(subtitle or "", style={"color": "#888"}),
            ])), width=2)

        # For US use full weekly history for DAR; for intl use all_hist monthly
        if stats_code == "US":
            sc_rows_full = all_hist.get("US", [])
            sc_dar_full  = _dar_map.get("US", [])
        else:
            sc_rows_full = all_hist.get(stats_code, [])
            sc_dar_full  = _dar_map.get(stats_code, [])

        us_rows      = by_country.get("US", [])  # always needed for stacked chart
        us_all_rows  = all_hist.get("US", [])
        us_dar_full  = _dar_map.get("US", [])

        sc_spr_val      = sc_latest.spr_mbbl if sc_latest else None
        sc_delta_1w     = (sc_spr_val - sc_1w.spr_mbbl)    if (sc_latest and sc_1w and sc_1w.spr_mbbl)    else None
        sc_delta_1m     = (sc_spr_val - sc_1m.spr_mbbl)    if (sc_latest and sc_1m and sc_1m.spr_mbbl)    else None
        sc_war_draw     = (sc_spr_val - sc_war_start.spr_mbbl) if (sc_latest and sc_war_start and sc_war_start.spr_mbbl) else None
        sc_days_at_rate = sc_dar_full[-1] if sc_dar_full else None

        # For intl countries: override all derived stats using IEA announced rate
        sc_est_val   = sc_spr_val
        sc_est_label = sc_latest.date.isoformat() if sc_latest else "—"
        if stats_code != "US" and stats_code in _IEA_RATES:
            rate     = _IEA_RATES[stats_code]
            rlist    = sc_rows_full
            today_dt_metric = date.today()
            if rlist:
                last_r = rlist[-1]
                if last_r.spr_mbbl is not None:
                    def _proj_val(at_date):
                        """Estimate SPR level at a given date using IEA rate from last actual."""
                        d_releasing = max(0, (min(at_date, _IEA_END) - max(last_r.date, _IEA_START)).days)
                        return round(last_r.spr_mbbl - rate * d_releasing, 1)

                    # Estimated current level
                    if last_r.date < today_dt_metric:
                        sc_est_val   = _proj_val(today_dt_metric)
                        sc_est_label = f"~{today_dt_metric.isoformat()} (est.)"

                    # Days at release rate: est. current / IEA daily rate
                    sc_days_at_rate = round(sc_est_val / rate, 0) if (sc_est_val and rate) else None

                    # Δ 1M: change over last 30 days at IEA rate
                    # If release started < 30 days ago, use partial; if not started, zero
                    days_in_last_30 = max(0, (min(today_dt_metric, _IEA_END) - max(today_dt_metric - timedelta(days=30), _IEA_START)).days)
                    sc_delta_1m = round(-rate * days_in_last_30, 2)

                    # War drawdown: from war start to now
                    war_val_at_start = _proj_val(_WAR_START) if last_r.date <= _WAR_START else last_r.spr_mbbl
                    sc_war_draw = round(sc_est_val - war_val_at_start, 1)

        # IEA release progress
        iea_days_elapsed    = max(0, (end_date - _IEA_START).days) if end_date >= _IEA_START else 0
        iea_days_elapsed    = min(iea_days_elapsed, _IEA_DAYS)
        iea_total_committed = sum(_IEA_COMMITTED.values())
        iea_est_released    = round(sum(rate * iea_days_elapsed for rate in _IEA_RATES.values()), 1)
        iea_pct             = round(iea_est_released / iea_total_committed * 100, 0) if iea_total_committed else 0

        country_label = SPR_COUNTRIES.get(stats_code, stats_code)

        def _sign(v):
            if v is None:
                return "N/A"
            return f"+{v:.1f}" if v > 0 else f"{v:.1f}"

        # IEA commitment for this country (if any)
        sc_iea_committed = _IEA_COMMITTED.get(stats_code)
        sc_iea_rate      = _IEA_RATES.get(stats_code)
        iea_subtitle     = (f"IEA pledge: {sc_iea_committed} Mbbl @ {sc_iea_rate:.3f} Mbbl/d"
                            if sc_iea_committed else "No IEA pledge")

        metrics = [
            _metric_card(f"{country_label} SPR",       f"{_fmt(sc_est_val)} Mbbl",         f"as of {sc_est_label}"),
            _metric_card("Days at Release Rate",        f"{_fmt(sc_days_at_rate, 0)} days", f"{country_label} SPR ÷ {'IEA rate' if stats_code != 'US' else 'avg weekly rate'}", alert=bool(sc_days_at_rate and sc_days_at_rate < 365)),
            _metric_card("Δ 1M",                        f"{_sign(sc_delta_1m)} Mbbl",       f"{'IEA rate × 30d' if (stats_code != 'US' and stats_code in _IEA_RATES) else 'monthly change'}"),
            _metric_card("War Drawdown",                f"{_sign(sc_war_draw)} Mbbl",       f"{country_label} since {WAR_START_DATE}", alert=bool(sc_war_draw and sc_war_draw < -50)),
            _metric_card("IEA Release Progress",        f"{iea_est_released:.0f} / {iea_total_committed:.0f} Mbbl",
                                                                                            f"{iea_pct:.0f}% pledged · {iea_days_elapsed}d elapsed · {iea_subtitle}"),
        ]


        # ── SPR Levels Over Time — line chart ─────────────────────────────
        # For intl countries (monthly, last data Jan 2026) build a forward
        # projection using the IEA committed release rate from _IEA_START to today.
        today_dt = date.today()
        projected: dict[str, tuple[list, list]] = {}   # code → (dates, values)
        for code, rate in _IEA_RATES.items():
            if code == "US":
                continue  # US has live weekly data, no projection needed
            if code not in chart_codes:
                continue  # only project visible countries
            rlist = all_hist.get(code, [])
            if not rlist:
                continue
            last_r = rlist[-1]
            # Only project if last known point is before today
            if last_r.date >= today_dt or last_r.spr_mbbl is None:
                continue
            proj_dates = [last_r.date]
            proj_vals  = [last_r.spr_mbbl]
            # Step day-by-day in coarse steps (weekly) for performance
            step = timedelta(days=7)
            cur = last_r.date + step
            while cur <= today_dt:
                days_releasing = max(0, (min(cur, _IEA_END) - max(last_r.date, _IEA_START)).days)
                proj_vals.append(round(last_r.spr_mbbl - rate * days_releasing, 2))
                proj_dates.append(cur)
                cur += step
            projected[code] = (proj_dates, proj_vals)

        levels_fig = go.Figure()
        levels_fig.update_layout(
            template="oil_dark",
            title="Strategic Petroleum Reserve Levels",
            xaxis_title="Date",
            yaxis_title="Mbbl",
            height=380,
            legend=dict(orientation="h", y=-0.2),
        )
        for code in all_countries:
            rlist = by_country.get(code, [])
        for code in all_countries:
            if code not in chart_codes:
                continue
            rlist = by_country.get(code, [])
            # Actual historical trace (only if data falls within the date range)
            if rlist:
                levels_fig.add_trace(go.Scatter(
                    x=[r.date for r in rlist],
                    y=[r.spr_mbbl for r in rlist],
                    mode="lines+markers",
                    name=SPR_COUNTRIES.get(code, code),
                    line=dict(color=_COLORS.get(code, "#ccc")),
                    marker=dict(size=4),
                ))
            # Dotted projection line — drawn even when actual data is outside date range
            if code in projected:
                pdates, pvals = projected[code]
                levels_fig.add_trace(go.Scatter(
                    x=pdates,
                    y=pvals,
                    mode="lines",
                    name=f"{SPR_COUNTRIES.get(code, code)} (est.)",
                    line=dict(color=_COLORS.get(code, "#ccc"), dash="dot", width=1.5),
                    showlegend=True,
                ))
        # War start + IEA release vertical lines
        for vdate, label, color in [
            (_WAR_START, "War Start",   "#e74c3c"),
            (_IEA_START, "IEA Release", "#f39c12"),
        ]:
            levels_fig.add_shape(type="line", x0=vdate, x1=vdate,
                y0=0, y1=1, yref="paper",
                line=dict(color=color, dash="dash", width=1))
            levels_fig.add_annotation(x=vdate, y=0.97, yref="paper",
                text=label, showarrow=False,
                font=dict(size=10, color=color), xanchor="left")

        # ── US SPR vs Commercial Stocks — stacked bars ────────────────────
        us_stacked_fig = go.Figure()
        us_stacked_fig.update_layout(
            template="oil_dark",
            title="US SPR vs. Commercial Crude Stocks",
            xaxis_title="Date",
            yaxis_title="Mbbl",
            barmode="stack",
            height=380,
        )
        if us_rows:
            us_stacked_fig.add_trace(go.Bar(
                x=[r.date for r in us_rows],
                y=[r.spr_mbbl for r in us_rows],
                name="SPR",
                marker_color=_COLORS["US"],
            ))
            us_stacked_fig.add_trace(go.Bar(
                x=[r.date for r in us_rows],
                y=[r.commercial_mbbl for r in us_rows if r.commercial_mbbl is not None],
                name="Commercial",
                marker_color="#5DADE2",
            ))
        us_stacked_fig.add_shape(type="line", x0=_WAR_START, x1=_WAR_START,
            y0=0, y1=1, yref="paper",
            line=dict(color="#e74c3c", dash="dash", width=1))
        us_stacked_fig.add_annotation(x=_WAR_START, y=1, yref="paper",
            text="War Start", showarrow=False,
            font=dict(size=10, color="#e74c3c"), xanchor="left")

        # ── Country Snapshot — latest value horizontal bars ───────────────
        snapshot_countries = []
        snapshot_values    = []
        snapshot_colors    = []
        for code in all_countries:
            latest = latest_by_country.get(code)
            if latest and latest.spr_mbbl:
                snapshot_countries.append(SPR_COUNTRIES.get(code, code))
                snapshot_values.append(latest.spr_mbbl)
                snapshot_colors.append(_COLORS.get(code, "#ccc"))

        # Sort descending by value
        paired = sorted(zip(snapshot_values, snapshot_countries, snapshot_colors), reverse=True)
        if paired:
            snapshot_values, snapshot_countries, snapshot_colors = zip(*paired)
        else:
            snapshot_values, snapshot_countries, snapshot_colors = [], [], []

        snapshot_fig = go.Figure(go.Bar(
            x=list(snapshot_values),
            y=list(snapshot_countries),
            orientation="h",
            marker_color=list(snapshot_colors),
            text=[f"{v:.0f} Mbbl" for v in snapshot_values],
            textposition="outside",
        ))
        snapshot_fig.update_layout(
            template="oil_dark",
            title="Latest SPR by Country",
            xaxis_title="Mbbl",
            height=380,
            margin=dict(l=110),
        )

        # ── Data Table — all rows for selected country (all_hist + _dar_map already computed) ──

        table_data = []
        for code in table_codes:
            rlist    = all_hist.get(code, [])
            dar_list = _dar_map.get(code, [])
            for real_idx, r in enumerate(rlist):

                def _prev_val(days, _r=r, _rlist=rlist):
                    target = _r.date - timedelta(days=days)
                    cands  = [x for x in _rlist if x.date <= target and x.spr_mbbl is not None]
                    return cands[-1].spr_mbbl if cands else None

                prev_entry = rlist[real_idx - 1].spr_mbbl if real_idx > 0 and rlist[real_idx - 1].spr_mbbl is not None else None
                prev_1w = _prev_val(7)
                prev_1m = _prev_val(30) or prev_entry
                d1w = round(r.spr_mbbl - prev_1w, 2) if (r.spr_mbbl is not None and prev_1w is not None) else None
                d1m = round(r.spr_mbbl - prev_1m, 2) if (r.spr_mbbl is not None and prev_1m is not None) else None
                days_at_rate = dar_list[real_idx] if dar_list and real_idx < len(dar_list) else None

                table_data.append({
                    "date":            r.date.isoformat(),
                    "country":         SPR_COUNTRIES.get(code, code),
                    "spr_mbbl":        round(r.spr_mbbl, 1) if r.spr_mbbl is not None else None,
                    "commercial_mbbl": round(r.commercial_mbbl, 1) if r.commercial_mbbl is not None else None,
                    "total_mbbl":      round(r.total_mbbl, 1) if r.total_mbbl is not None else None,
                    "days_at_rate":    days_at_rate,
                    "delta_1w":        d1w,
                    "delta_1m":        d1m,
                    "source":          r.source,
                })

        # Newest first
        table_data.sort(key=lambda x: x["date"], reverse=True)

        # ── Append projected "estimated current" rows for stale intl countries ──
        for code in table_codes:
            if code not in _IEA_RATES or code == "US":
                continue
            if code not in projected:
                continue
            pdates, pvals = projected[code]
            if not pdates:
                continue
            # Last projected point = estimated stocks as of today
            est_date = pdates[-1]
            est_val  = pvals[-1]
            last_actual = all_hist.get(code, [])
            last_actual_val = last_actual[-1].spr_mbbl if last_actual else None
            d1m_est = round(est_val - last_actual_val, 2) if (est_val is not None and last_actual_val is not None) else None
            table_data.insert(0, {
                "date":            f"{est_date.isoformat()} (est.)",
                "country":         SPR_COUNTRIES.get(code, code),
                "spr_mbbl":        round(est_val, 1),
                "commercial_mbbl": None,
                "total_mbbl":      round(est_val, 1),
                "days_at_rate":    None,
                "delta_1w":        None,
                "delta_1m":        d1m_est,
                "source":          f"IEA-Proj ({_IEA_RATES[code]:.3f} Mbbl/d)",
            })

        return metrics, levels_fig, us_stacked_fig, snapshot_fig, table_data

    finally:
        session.close()
