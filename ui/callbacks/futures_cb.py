"""
Futures Tab Callbacks — query DB for curves & spreads, render Plotly charts.
"""

from datetime import date, datetime, timedelta
import calendar
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, no_update, dash_table
from dateutil.relativedelta import relativedelta

from db.database import get_session, FuturesCurve, Spread

# ─── Contract label helpers ───────────────────────────────────────────────────
_MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J",  5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}


def _biz_days_before(d: date, n: int) -> date:
    result = d
    counted = 0
    while counted < n:
        result -= timedelta(days=1)
        if result.weekday() < 5:
            counted += 1
    return result


def _contract_expiry(sym: str, contract_month: str) -> date | None:
    """
    Estimated last trading day for a contract.
      CL   — 3 biz days before the 25th of the prior calendar month
      COIL — last biz day of the 2nd calendar month before delivery
    """
    try:
        year  = int(contract_month[:4])
        month = int(contract_month[5:7])
        if sym == "CL":
            prev_month = month - 1 if month > 1 else 12
            prev_year  = year if month > 1 else year - 1
            return _biz_days_before(date(prev_year, prev_month, 25), 3)
        else:
            base  = date(year, month, 1) - relativedelta(months=2)
            last  = calendar.monthrange(base.year, base.month)[1]
            expiry = date(base.year, base.month, last)
            while expiry.weekday() >= 5:
                expiry -= timedelta(days=1)
            return expiry
    except Exception:
        return None


def _contract_label(sym: str, contract_month: str) -> str:
    """
    Return 'CLK6 2026-04-21' from symbol and 'YYYY-MM' contract_month.
    """
    try:
        year  = int(contract_month[:4])
        month = int(contract_month[5:7])
        ticker = f"{sym}{_MONTH_CODES.get(month, '?')}{str(year)[-1]}"
        expiry = _contract_expiry(sym, contract_month)
        return f"{ticker} {expiry.isoformat()}" if expiry else contract_month
    except Exception:
        return contract_month


# ─── Populate contract-month dropdowns from DB ────────────────────────────

@callback(
    Output("futures-contract-cl", "options"),
    Output("futures-contract-cl", "value"),
    Output("futures-contract-coil", "options"),
    Output("futures-contract-coil", "value"),
    Input("auto-refresh", "n_intervals"),
)
def populate_contract_dropdowns(_n):
    session = get_session()
    try:
        from sqlalchemy import func as sa_func
        opts = {}
        defaults = {}
        for sym in ("CL", "COIL"):
            months = [
                r[0] for r in session.query(FuturesCurve.contract_month)
                .filter(FuturesCurve.symbol == sym)
                .distinct()
                .order_by(FuturesCurve.contract_month)
                .all()
            ]
            opts[sym] = [{"label": _contract_label(sym, m), "value": m} for m in months]
            # Default to front month (min contract_month on most recent date)
            front = (
                session.query(sa_func.min(FuturesCurve.contract_month))
                .filter(
                    FuturesCurve.symbol == sym,
                    FuturesCurve.date == session.query(sa_func.max(FuturesCurve.date))
                        .filter(FuturesCurve.symbol == sym).scalar_subquery(),
                )
                .scalar()
            )
            defaults[sym] = front or (months[0] if months else None)
        return opts["CL"], defaults["CL"], opts["COIL"], defaults["COIL"]
    finally:
        session.close()


@callback(
    Output("futures-metrics-row", "children"),
    Output("futures-curve-chart", "figure"),
    Output("futures-curve-footnotes", "children"),
    Output("futures-term-structure-tables", "children"),
    Output("futures-price-history", "figure"),
    Output("futures-spread-chart", "figure"),
    Output("futures-spread-contracts", "children"),
    Output("futures-spread-percentile-row", "children"),
    Input("futures-date-range", "start_date"),
    Input("futures-date-range", "end_date"),
    Input("futures-symbol-toggle", "value"),
    Input("futures-contract-cl", "value"),
    Input("futures-contract-coil", "value"),
    Input("futures-spread-toggle", "value"),
    Input("futures-cal-spread-toggle", "value"),
    Input("futures-term-structure-overlays", "value"),
    Input("futures-term-structure-symbol", "value"),
    Input("futures-spread-date-range", "start_date"),
    Input("futures-spread-date-range", "end_date"),
    Input("auto-refresh", "n_intervals"),
)
def update_futures(start_date, end_date, symbol_filter, cl_contract, coil_contract, show_spread, cal_spread_mode, term_structure_overlays, term_structure_symbol, spread_start_date, spread_end_date, _n):
    session = get_session()
    today = date.today()

    try:
        # Parse dates
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        # Parse spread-specific date range (defaults to 1-year window)
        if isinstance(spread_start_date, str):
            spread_start_date = datetime.strptime(spread_start_date[:10], "%Y-%m-%d").date()
        elif spread_start_date is None:
            spread_start_date = today - timedelta(days=365)
        if isinstance(spread_end_date, str):
            spread_end_date = datetime.strptime(spread_end_date[:10], "%Y-%m-%d").date()
        elif spread_end_date is None:
            spread_end_date = today

        symbols = ["CL", "COIL"] if symbol_filter == "BOTH" else [symbol_filter]

        # ─── Key Metrics ──────────────────────────────────────────────
        metrics = []
        for sym in ["CL", "COIL"]:
            latest = session.query(FuturesCurve).filter(
                FuturesCurve.symbol == sym,
            ).order_by(FuturesCurve.date.desc(), FuturesCurve.contract_month).first()

            label = "WTI (CL)" if sym == "CL" else "Brent (COIL)"
            price = f"${latest.settlement_price:.2f}" if latest and latest.settlement_price else "N/A"
            metrics.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(label, className="text-muted"),
                html.H4(price),
            ])), width=2))

        # Brent-WTI spread
        latest_spread = session.query(Spread).filter(
            Spread.spread_type == "COIL-CL"
        ).order_by(Spread.date.desc()).first()
        spread_val = f"${latest_spread.spread_value:.2f}" if latest_spread and latest_spread.spread_value else "N/A"
        metrics.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Brent-WTI Spread", className="text-muted"),
            html.H4(spread_val),
        ])), width=2))

        # ─── Term Structure Chart — current + selected historical snapshots ───
        curve_fig = go.Figure()
        curve_fig.update_layout(
            template="oil_dark",
            title="Futures Term Structure",
            xaxis_title="Contract Month",
            yaxis_title="Price ($/bbl)",
            height=400,
        )

        colors = {"CL": "#2E86DE", "COIL": "#E74C3C"}
        line_styles = {
            "CURRENT": "solid",
            "INCEPTION": "dash",
            "1W": "dot",
            "1M": "dashdot",
            "3M": "longdash",
            "6M": "longdashdot",
            "12M": "dash",
        }
        has_curve = False
        curve_details = []  # ["WTI 1M: 2026-03-24", ...]

        inception_date = date(2026, 3, 2)

        if term_structure_overlays is None:
            term_structure_overlays = []

        # Only show the selected symbol on term structure chart
        term_structure_symbols = [term_structure_symbol]

        def _curve_on_or_before(sym: str, target_date: date):
            date_row = session.query(FuturesCurve.date).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.date <= target_date,
            ).order_by(FuturesCurve.date.desc()).first()
            if not date_row:
                return None, []
            rows = session.query(FuturesCurve).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.date == date_row[0],
            ).order_by(FuturesCurve.contract_month).all()
            return date_row[0], rows

        # Track contract data for separate tables
        term_structure_tables = []

        for sym in term_structure_symbols:
            latest_date_row = session.query(FuturesCurve.date).filter(
                FuturesCurve.symbol == sym,
            ).order_by(FuturesCurve.date.desc()).first()

            if not latest_date_row:
                continue

            base_date = latest_date_row[0]
            snapshot_specs = [("CURRENT", "Current", base_date)]
            if "INCEPTION" in term_structure_overlays:
                snapshot_specs.append(("INCEPTION", "Inception", inception_date))
            if "1W" in term_structure_overlays:
                snapshot_specs.append(("1W", "1W Ago", base_date - timedelta(weeks=1)))
            if "1M" in term_structure_overlays:
                snapshot_specs.append(("1M", "1M Ago", base_date - relativedelta(months=1)))
            if "3M" in term_structure_overlays:
                snapshot_specs.append(("3M", "3M Ago", base_date - relativedelta(months=3)))
            if "6M" in term_structure_overlays:
                snapshot_specs.append(("6M", "6M Ago", base_date - relativedelta(months=6)))
            if "12M" in term_structure_overlays:
                snapshot_specs.append(("12M", "12M Ago", base_date - relativedelta(months=12)))

            sym_label = "WTI" if sym == "CL" else "Brent"
            for key, tag, target_date in snapshot_specs:
                snap_date, curves = _curve_on_or_before(sym, target_date)
                if not curves or len(curves) < 2:
                    continue
                has_curve = True
                curve_fig.add_trace(go.Scatter(
                    x=[c.contract_month for c in curves],
                    y=[c.settlement_price for c in curves],
                    mode="lines+markers",
                    name=f"{sym_label} {tag}",
                    line=dict(color=colors[sym], dash=line_styles[key]),
                    marker=dict(color=colors[sym], size=5),
                ))
                if snap_date:
                    curve_details.append(f"{sym_label} {tag}: {snap_date.isoformat()}")
                    # Create a separate table for this curve
                    table_data = []
                    for c in curves:
                        table_data.append({
                            "contract": _contract_label(sym, c.contract_month),
                            "price": f"${c.settlement_price:.2f}" if c.settlement_price else "N/A",
                        })
                    
                    term_structure_tables.append(
                        dbc.Col([
                            html.H6(f"{sym_label} {tag}", style={"fontSize": "0.85rem", "marginBottom": "4px"}),
                            html.P(snap_date.isoformat(), style={"fontSize": "0.72rem", "color": "#888", "marginBottom": "8px"}),
                            dash_table.DataTable(
                                columns=[
                                    {"name": "Contract", "id": "contract"},
                                    {"name": "Price", "id": "price"},
                                ],
                                data=table_data,
                                style_cell={
                                    "backgroundColor": "#1a1a2e",
                                    "color": "#e0e0e0",
                                    "border": "1px solid #333",
                                    "textAlign": "left",
                                    "padding": "4px 8px",
                                    "fontSize": "0.75rem",
                                    "fontFamily": "monospace",
                                },
                                style_header={
                                    "backgroundColor": "#16213e",
                                    "color": "#aaa",
                                    "fontWeight": "600",
                                    "border": "1px solid #333",
                                    "textAlign": "left",
                                    "fontSize": "0.75rem",
                                },
                                style_table={"maxHeight": "400px", "overflowY": "auto"},
                            ),
                        ], width="auto", style={"minWidth": "200px", "marginRight": "16px"}),
                    )

        if not has_curve:
            curve_fig.update_layout(
                title="Recent Spot Prices (term structure requires IB data)",
                xaxis_title="Date",
            )
            for sym in term_structure_symbols:
                rows = session.query(FuturesCurve).filter(
                    FuturesCurve.symbol == sym,
                ).order_by(FuturesCurve.date.desc()).limit(20).all()
                rows = list(reversed(rows))
                if rows:
                    label = "WTI (CL)" if sym == "CL" else "Brent (COIL)"
                    curve_fig.add_trace(go.Scatter(
                        x=[r.date for r in rows],
                        y=[r.settlement_price for r in rows],
                        mode="lines+markers",
                        name=label,
                        line=dict(color=colors[sym]),
                    ))

        # ─── Term Structure Footnotes ─────────────────────────────────
        footnote_children = []
        if curve_details:
            footnote_children.append(
                html.P(
                    " | ".join(curve_details),
                    style={"fontSize": "0.72rem", "color": "#888", "margin": "2px 0", "lineHeight": "1.3"},
                )
            )

        # ─── Arrange term structure tables horizontally ───────────────
        term_structure_tables_component = dbc.Row(
            term_structure_tables,
            style={"display": "flex", "flexWrap": "nowrap", "overflowX": "auto"},
        ) if term_structure_tables else html.Div("No term structure data available")

        # ─── Price History Chart ──────────────────────────────────────
        history_fig = go.Figure()

        from sqlalchemy import func as sa_func
        contract_picks = {"CL": cl_contract, "COIL": coil_contract}

        def _fetch_series(sym):
            picked = contract_picks.get(sym)
            if picked:
                # Cap at expiry date for specific contracts
                expiry = _contract_expiry(sym, picked)
                query = session.query(FuturesCurve).filter(
                    FuturesCurve.symbol == sym,
                    FuturesCurve.contract_month == picked,
                )
                if expiry:
                    query = query.filter(FuturesCurve.date <= expiry)
                return query.order_by(FuturesCurve.date).all()
            subq = session.query(
                FuturesCurve.date,
                sa_func.min(FuturesCurve.contract_month).label("front_month"),
            ).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.date >= start_date,
                FuturesCurve.date <= end_date,
            ).group_by(FuturesCurve.date).subquery()
            return session.query(FuturesCurve).join(
                subq,
                (FuturesCurve.date == subq.c.date) &
                (FuturesCurve.contract_month == subq.c.front_month) &
                (FuturesCurve.symbol == sym),
            ).order_by(FuturesCurve.date).all()

        if show_spread:
            # Spread mode: Brent selected − WTI selected
            cl_rows = _fetch_series("CL")
            coil_rows = _fetch_series("COIL")
            cl_map = {r.date: r.settlement_price for r in cl_rows if r.settlement_price}
            coil_map = {r.date: r.settlement_price for r in coil_rows if r.settlement_price}
            common = sorted(set(cl_map) & set(coil_map))
            cl_cm = cl_contract or "front"
            coil_cm = coil_contract or "front"
            if common:
                history_fig.add_trace(go.Scatter(
                    x=common,
                    y=[coil_map[d] - cl_map[d] for d in common],
                    mode="lines",
                    name=f"Brent {coil_cm} − WTI {cl_cm}",
                    line=dict(color="#2ED573"),
                ))
            history_fig.update_layout(
                template="oil_dark",
                title=f"Spread: Brent ({coil_cm}) − WTI ({cl_cm})",
                xaxis_title="Date",
                yaxis_title="Spread ($/bbl)",
                height=400,
            )
        else:
            # Normal price mode
            for sym in symbols:
                rows = _fetch_series(sym)
                if rows:
                    sym_label = "WTI (CL)" if sym == "CL" else "Brent (COIL)"
                    cm_label = contract_picks.get(sym) or "front"
                    history_fig.add_trace(go.Scatter(
                        x=[r.date for r in rows],
                        y=[r.settlement_price for r in rows],
                        mode="lines",
                        name=f"{sym_label} {cm_label}",
                    ))
            history_fig.update_layout(
                template="oil_dark",
                title="Price History",
                xaxis_title="Date",
                yaxis_title="Price ($/bbl)",
                height=400,
            )

        # ─── Spread Chart ─────────────────────────────────────────────
        spread_fig = go.Figure()
        spread_fig.update_layout(
            template="oil_dark",
            title="Spreads Over Time",
            xaxis_title="Date",
            yaxis_title="Spread ($/bbl)",
            height=400,
        )

        # ─── Calendar spreads ─────────────────────────────────────────
        # Strategy:
        #   1. Primary — read from pre-computed Spread table (covers full history).
        #   2. Fallback — compute on-the-fly from FuturesCurve for any dates
        #      more recent than the last Spread cache entry (cache may lag by a day).
        # The spread-specific date range (spread_start_date / spread_end_date)
        # is used here instead of the global price-history range so users can
        # view a year or more of spread history regardless of the main date range.

        _offset_map  = {"M1-M2": 1, "M1-M6": 5, "M1-M12": 11}
        _suffix_map  = {"M1-M2": "M1M2", "M1-M6": "M1M6", "M1-M12": "M1M12"}
        selected_offset = _offset_map.get(cal_spread_mode or "M1-M12", 11)
        spread_suffix   = _suffix_map.get(cal_spread_mode or "M1-M12", "M1M12")
        _cal_colors = {"CL": "#EE5A24", "COIL": "#0ABDE3"}

        spread_contract_info = {}  # {sym: (m1_label, mn_label)}
        spread_points_by_sym = {}  # {sym: [(date, value, front_month, back_month)]}

        for sym in ["CL", "COIL"]:
            spread_type = f"{sym}_{spread_suffix}"

            # ── 1. Query the pre-computed Spread cache ──────────────────
            cached_rows = (
                session.query(Spread)
                .filter(
                    Spread.spread_type == spread_type,
                    Spread.date >= spread_start_date,
                    Spread.date <= spread_end_date,
                )
                .order_by(Spread.date)
                .all()
            )
            cached_dates = {r.date for r in cached_rows}
            last_cached_date = max(cached_dates) if cached_dates else None

            points = [(r.date, r.spread_value, r.front_month, r.back_month)
                      for r in cached_rows
                      if r.spread_value is not None]

            # ── 2. On-the-fly fallback for any gap at the recent end ────
            # If cache is missing today or yesterday, compute from FuturesCurve.
            gap_start = (last_cached_date + timedelta(days=1)) if last_cached_date else spread_start_date
            if gap_start <= spread_end_date:
                curve_rows = (
                    session.query(FuturesCurve)
                    .filter(
                        FuturesCurve.symbol == sym,
                        FuturesCurve.date   >= gap_start,
                        FuturesCurve.date   <= spread_end_date,
                    )
                    .order_by(FuturesCurve.date, FuturesCurve.contract_month)
                    .all()
                )
                by_date = {}
                for r in curve_rows:
                    by_date.setdefault(r.date, []).append(r)

                for dt in sorted(by_date):
                    if dt in cached_dates:
                        continue
                    contracts = by_date[dt]
                    prices = [c for c in contracts if c.settlement_price is not None]
                    if len(prices) <= selected_offset:
                        continue
                    m1 = prices[0]
                    mn = prices[selected_offset]
                    points.append((dt, m1.settlement_price - mn.settlement_price,
                                   m1.contract_month, mn.contract_month))

            # Sort by date (cache + fallback may be interleaved)
            points.sort(key=lambda x: x[0])
            spread_points_by_sym[sym] = points

            # Record the latest contract labels for the info bar
            if points:
                last = points[-1]
                spread_contract_info[sym] = (
                    _contract_label(sym, last[2]) if last[2] else "—",
                    _contract_label(sym, last[3]) if last[3] else "—",
                )

            sym_label = "WTI" if sym == "CL" else "Brent"
            if points:
                spread_fig.add_trace(go.Scatter(
                    x=[p[0] for p in points],
                    y=[p[1] for p in points],
                    mode="lines+markers",
                    marker=dict(size=3),
                    name=f"{sym_label} {cal_spread_mode}",
                    line=dict(color=_cal_colors[sym]),
                ))

        spread_fig.update_layout(
            title=f"Calendar Spread: {cal_spread_mode} (M1 − Mn)",
            yaxis_title="$/bbl",
        )

        # ── Contract label row shown below the chart ────────────────────
        contract_label_parts = []
        for sym, sym_label in [("CL", "WTI"), ("COIL", "Brent")]:
            if sym in spread_contract_info:
                m1_lbl, mn_lbl = spread_contract_info[sym]
                contract_label_parts.append(
                    html.Span(
                        f"{sym_label}: {m1_lbl}  −  {mn_lbl}",
                        style={"marginRight": "24px"},
                    )
                )
        spread_contracts_children = contract_label_parts or "No data"

        # ── Spread percentile metrics row ───────────────────────────────
        # For each symbol, compute:
        #   current value, 3-year percentile rank, 52-week min/max
        # All from the pre-computed Spread table (fast single query per sym).
        pct_cards = []
        for sym, sym_label in [("CL", "WTI"), ("COIL", "Brent")]:
            spread_type = f"{sym}_{spread_suffix}"
            three_yr_ago  = today - timedelta(days=3 * 365)
            fifty_two_ago = today - timedelta(days=365)

            all_rows_3yr = (
                session.query(Spread)
                .filter(
                    Spread.spread_type == spread_type,
                    Spread.date >= three_yr_ago,
                    Spread.spread_value.isnot(None),
                )
                .order_by(Spread.date)
                .all()
            )
            if not all_rows_3yr:
                # Fall back to spread_points_by_sym if cache is empty
                all_vals_3yr = [v for (_, v, _, _) in spread_points_by_sym.get(sym, [])]
                curr_val = all_vals_3yr[-1] if all_vals_3yr else None
            else:
                all_vals_3yr = [r.spread_value for r in all_rows_3yr]
                curr_val = all_vals_3yr[-1]

            if not all_vals_3yr or curr_val is None:
                pct_cards.append(
                    dbc.Col(
                        dbc.Card(dbc.CardBody(
                            html.Span(f"{sym_label} {cal_spread_mode}: no data",
                                      style={"color": "#888", "fontSize": "0.82rem"})
                        ), className="text-center"),
                        width=6,
                    )
                )
                continue

            # Percentile rank: how many values ≤ curr_val?
            pct_rank = int(100 * sum(1 for v in all_vals_3yr if v <= curr_val) / len(all_vals_3yr))

            # 52-week range from Spread table
            rows_52w = [r.spread_value for r in all_rows_3yr
                        if r.date >= fifty_two_ago]
            w52_min = min(rows_52w) if rows_52w else None
            w52_max = max(rows_52w) if rows_52w else None

            val_color = "#2ed573" if curr_val >= 0 else "#ff6b81"
            pct_color = "#f0c040" if 20 <= pct_rank <= 80 else ("#2ed573" if pct_rank < 20 else "#ff6b81")

            w52_str = (
                f"52W: {w52_min:+.2f} → {w52_max:+.2f}"
                if w52_min is not None else "52W: —"
            )

            pct_cards.append(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody([
                            html.Div(f"{sym_label} {cal_spread_mode}",
                                     style={"fontSize": "0.75rem", "color": "#aaa",
                                            "marginBottom": "2px"}),
                            html.Div([
                                html.Span(f"{curr_val:+.2f} $/bbl",
                                          style={"fontWeight": "700", "fontSize": "1.1rem",
                                                 "color": val_color, "marginRight": "10px"}),
                                html.Span(f"3yr pct: {pct_rank}th",
                                          style={"fontSize": "0.85rem", "color": pct_color,
                                                 "marginRight": "10px"}),
                                html.Span(w52_str,
                                          style={"fontSize": "0.82rem", "color": "#aaa"}),
                            ]),
                        ], style={"padding": "8px 12px"}),
                        style={"backgroundColor": "#1a1a2e", "border": "1px solid #333"},
                    ),
                    width=6,
                )
            )

        spread_percentile_row = dbc.Row(pct_cards, className="g-2") if pct_cards else ""

        return (metrics, curve_fig, footnote_children, term_structure_tables_component,
                history_fig, spread_fig, spread_contracts_children, spread_percentile_row)

    finally:
        session.close()


# ─── Fill price history tables (shares contract selection with chart dropdowns) ─

@callback(
    Output("futures-table-cl",         "data"),
    Output("futures-table-coil",       "data"),
    Output("futures-table-cl-label",   "children"),
    Output("futures-table-coil-label", "children"),
    Input("futures-contract-cl",   "value"),
    Input("futures-contract-coil", "value"),
    Input("futures-date-range", "start_date"),
    Input("futures-date-range", "end_date"),
)
def update_history_tables(cl_contract, coil_contract, start_date, end_date):
    session = get_session()
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        def _rows(sym, contract):
            if not contract:
                return []
            # Cap at expiry date to exclude delivery-month settlements
            expiry = _contract_expiry(sym, contract)
            query = session.query(FuturesCurve).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.contract_month == contract,
            )
            if expiry:
                query = query.filter(FuturesCurve.date <= expiry)
            rows = query.order_by(FuturesCurve.date.desc()).all()
            return [
                {
                    "date":   r.date.strftime("%Y-%m-%d"),
                    "price":  f"{r.settlement_price:.2f}" if r.settlement_price is not None else "\u2014",
                    "volume": f"{r.volume:,}"        if r.volume        is not None else "\u2014",
                    "oi":     f"{r.open_interest:,}" if r.open_interest is not None else "\u2014",
                }
                for r in rows
            ]

        def _label(sym, contract):
            if not contract:
                return ""
            label = _contract_label(sym, contract)  # e.g. "CLH6 2026-02-20"
            return f"— {label}"

        return (
            _rows("CL",   cl_contract),
            _rows("COIL", coil_contract),
            _label("CL",   cl_contract),
            _label("COIL", coil_contract),
        )
    finally:
        session.close()


# ─── Spread inspection tables — auto-loaded on tab open / toggle change ──────

_OFFSET_MAP = {"M1-M2": 1, "M1-M6": 5, "M1-M12": 11}


@callback(
    Output("futures-spread-inspect-cl",         "data"),
    Output("futures-spread-inspect-coil",       "data"),
    Output("futures-spread-inspect-cl-label",   "children"),
    Output("futures-spread-inspect-coil-label", "children"),
    Output("futures-spread-inspect-hint",       "children"),
    Input("futures-cal-spread-toggle",          "value"),
    Input("futures-spread-chart",               "clickData"),
)
def update_spread_inspection(cal_spread_mode, click_data):
    offset = _OFFSET_MAP.get(cal_spread_mode or "M1-M12", 11)

    session = get_session()
    try:
        # Determine reference date: clicked point if available, else latest in DB
        clicked_date = None
        if click_data:
            try:
                clicked_date = datetime.strptime(
                    click_data["points"][0]["x"][:10], "%Y-%m-%d"
                ).date()
            except Exception:
                pass

        result_data   = {}
        result_labels = {}

        for sym in ["CL", "COIL"]:
            # Find the reference date for this symbol
            ref_date = clicked_date
            if ref_date is None:
                latest = (
                    session.query(FuturesCurve.date)
                    .filter(FuturesCurve.symbol == sym)
                    .order_by(FuturesCurve.date.desc())
                    .first()
                )
                if not latest:
                    result_data[sym]   = []
                    result_labels[sym] = f"{'WTI' if sym == 'CL' else 'Brent'} — no data"
                    continue
                ref_date = latest[0]

            # Find which contracts are M1 and Mn on ref_date
            contracts_on_date = (
                session.query(FuturesCurve)
                .filter(
                    FuturesCurve.symbol == sym,
                    FuturesCurve.date   == ref_date,
                )
                .order_by(FuturesCurve.contract_month)
                .all()
            )

            if len(contracts_on_date) <= offset:
                result_data[sym]   = []
                result_labels[sym] = (
                    f"{'WTI' if sym == 'CL' else 'Brent'} — "
                    f"not enough contracts on {ref_date}"
                )
                continue

            m1_month = contracts_on_date[0].contract_month
            mn_month = contracts_on_date[offset].contract_month
            m1_label = _contract_label(sym, m1_month)
            mn_label = _contract_label(sym, mn_month)

            # Fetch full price history for both contracts
            m1_rows = {
                r.date: r.settlement_price
                for r in session.query(FuturesCurve).filter(
                    FuturesCurve.symbol         == sym,
                    FuturesCurve.contract_month == m1_month,
                ).all()
            }
            mn_rows = {
                r.date: r.settlement_price
                for r in session.query(FuturesCurve).filter(
                    FuturesCurve.symbol         == sym,
                    FuturesCurve.contract_month == mn_month,
                ).all()
            }

            all_dates = sorted(m1_rows.keys() | mn_rows.keys(), reverse=True)
            rows = []
            for d in all_dates:
                m1_p = m1_rows.get(d)
                mn_p = mn_rows.get(d)
                sprd = (m1_p - mn_p) if (m1_p is not None and mn_p is not None) else None
                rows.append({
                    "date":   d.strftime("%Y-%m-%d"),
                    "m1":     f"{m1_p:.2f}" if m1_p is not None else "—",
                    "mn":     f"{mn_p:.2f}" if mn_p is not None else "—",
                    "spread": f"{sprd:.2f}" if sprd is not None else "—",
                })

            sym_label = "WTI" if sym == "CL" else "Brent"
            result_data[sym]   = rows
            result_labels[sym] = f"{sym_label}  M1={m1_label}  Mn={mn_label}"

        if clicked_date:
            hint = f"Contracts as of clicked date {clicked_date} · {cal_spread_mode}"
        else:
            hint = f"Contracts as of latest available date · {cal_spread_mode}  (click a chart point to change reference date)"

        return (
            result_data.get("CL",   []),
            result_data.get("COIL", []),
            result_labels.get("CL",   "WTI"),
            result_labels.get("COIL", "Brent"),
            hint,
        )
    finally:
        session.close()

