"""
Futures Tab Callbacks — query DB for curves & spreads, render Plotly charts.
"""

from datetime import date, datetime, timedelta
import calendar
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, no_update
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


def _contract_label(sym: str, contract_month: str) -> str:
    """
    Return 'CLK6 2026-04-21' from symbol and 'YYYY-MM' contract_month.
    Expiry estimated:
      CL   — 3 biz days before the 25th of the prior calendar month
      COIL — last biz day of the 2nd calendar month before delivery
    """
    try:
        year  = int(contract_month[:4])
        month = int(contract_month[5:7])
        ticker = f"{sym}{_MONTH_CODES.get(month, '?')}{str(year)[-1]}"

        if sym == "CL":
            prev_month = month - 1 if month > 1 else 12
            prev_year  = year if month > 1 else year - 1
            expiry = _biz_days_before(date(prev_year, prev_month, 25), 3)
        else:
            base  = date(year, month, 1) - relativedelta(months=2)
            last  = calendar.monthrange(base.year, base.month)[1]
            expiry = date(base.year, base.month, last)
            while expiry.weekday() >= 5:
                expiry -= timedelta(days=1)

        return f"{ticker} {expiry.isoformat()}"
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
    Output("futures-price-history", "figure"),
    Output("futures-spread-chart", "figure"),
    Input("futures-date-range", "start_date"),
    Input("futures-date-range", "end_date"),
    Input("futures-symbol-toggle", "value"),
    Input("futures-contract-cl", "value"),
    Input("futures-contract-coil", "value"),
    Input("futures-spread-toggle", "value"),
    Input("futures-cal-6m-toggle", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_futures(start_date, end_date, symbol_filter, cl_contract, coil_contract, show_spread, show_6m, _n):
    session = get_session()
    today = date.today()

    try:
        # Parse dates
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

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

        # ─── Term Structure Chart — always both WTI & Brent ─────────
        curve_fig = go.Figure()
        curve_fig.update_layout(
            template="oil_dark",
            title="Current Futures Term Structure",
            xaxis_title="Contract Month",
            yaxis_title="Price ($/bbl)",
            height=400,
        )

        colors = {"CL": "#FF6B35", "COIL": "#1E90FF"}
        has_curve = False
        curve_details = {}  # {sym: [(month, price), ...]}

        for sym in ["CL", "COIL"]:
            latest_date_row = session.query(FuturesCurve.date).filter(
                FuturesCurve.symbol == sym,
            ).order_by(FuturesCurve.date.desc()).first()

            if latest_date_row:
                curves = session.query(FuturesCurve).filter(
                    FuturesCurve.symbol == sym,
                    FuturesCurve.date == latest_date_row[0],
                ).order_by(FuturesCurve.contract_month).all()

                if curves and len(curves) > 1:
                    has_curve = True
                    label = "WTI (CL)" if sym == "CL" else "Brent (COIL)"
                    curve_details[sym] = [
                        (c.contract_month, c.settlement_price) for c in curves
                    ]
                    curve_fig.add_trace(go.Scatter(
                        x=[c.contract_month for c in curves],
                        y=[c.settlement_price for c in curves],
                        mode="lines+markers",
                        name=label,
                        line=dict(color=colors[sym]),
                        marker=dict(color=colors[sym]),
                    ))

        if not has_curve:
            curve_fig.update_layout(
                title="Recent Spot Prices (term structure requires IB data)",
                xaxis_title="Date",
            )
            for sym in ["CL", "COIL"]:
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
        for sym, pairs in curve_details.items():
            label = "WTI (CL)" if sym == "CL" else "Brent (COIL)"
            line = f"{label}: " + ", ".join(
                f"{m} ${p:.2f}" if p else f"{m} N/A" for m, p in pairs
            )
            footnote_children.append(
                html.P(line, style={"fontSize": "0.7rem", "color": "#888",
                                    "margin": "2px 0", "lineHeight": "1.3"})
            )

        # ─── Price History Chart ──────────────────────────────────────
        history_fig = go.Figure()

        from sqlalchemy import func as sa_func
        contract_picks = {"CL": cl_contract, "COIL": coil_contract}

        def _fetch_series(sym):
            picked = contract_picks.get(sym)
            if picked:
                return session.query(FuturesCurve).filter(
                    FuturesCurve.symbol == sym,
                    FuturesCurve.contract_month == picked,
                    FuturesCurve.date >= start_date,
                    FuturesCurve.date <= end_date,
                ).order_by(FuturesCurve.date).all()
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

        # Calendar spreads — compute on-the-fly from FuturesCurve data
        # For each date & symbol, rank contracts by contract_month and compute
        # M1-M6 and M1-M12 spreads (M1-M2 is often ~0, so skip it)
        from sqlalchemy import func as sa_f2
        for sym in ["CL", "COIL"]:
            curve_rows = session.query(FuturesCurve).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.date >= start_date,
                FuturesCurve.date <= end_date,
            ).order_by(FuturesCurve.date, FuturesCurve.contract_month).all()

            # Group by date
            by_date = {}
            for r in curve_rows:
                by_date.setdefault(r.date, []).append(r)

            cal_offsets = [(11, "M1-M12")]
            if show_6m:
                cal_offsets.insert(0, (5, "M1-M6"))

            cal_data = {}  # {offset_label: [(date, spread_val), ...]}
            for dt in sorted(by_date):
                contracts = by_date[dt]
                if len(contracts) < 2:
                    continue
                m1_price = contracts[0].settlement_price
                if m1_price is None:
                    continue
                for offset, lbl in cal_offsets:
                    if len(contracts) > offset and contracts[offset].settlement_price is not None:
                        spread_val = m1_price - contracts[offset].settlement_price
                        cal_data.setdefault(lbl, []).append((dt, spread_val))

            sym_label = "WTI" if sym == "CL" else "Brent"
            cal_colors = {"M1-M6": "#FF9F43" if sym == "CL" else "#48DBFB",
                          "M1-M12": "#EE5A24" if sym == "CL" else "#0ABDE3"}
            for lbl, points in cal_data.items():
                if points:
                    spread_fig.add_trace(go.Scatter(
                        x=[p[0] for p in points],
                        y=[p[1] for p in points],
                        mode="lines+markers",
                        name=f"{sym_label} {lbl}",
                        line=dict(color=cal_colors[lbl]),
                    ))

        # Also add any spread types from Spread table that have meaningful data
        spread_types = session.query(Spread.spread_type).filter(
            Spread.date >= start_date,
            Spread.date <= end_date,
        ).distinct().all()

        # Only add from Spread table types not already computed above
        skip_types = {"COIL-CL", "CL_M1-M2", "COIL_M1-M2", "CL_M1-M6", "COIL_M1-M6",
                      "CL_M1-M12", "COIL_M1-M12",
                      }
        for (st,) in spread_types:
            if st in skip_types:
                continue
            spread_rows = session.query(Spread).filter(
                Spread.spread_type == st,
                Spread.date >= start_date,
                Spread.date <= end_date,
            ).order_by(Spread.date).all()
            if spread_rows:
                spread_fig.add_trace(go.Scatter(
                    x=[r.date for r in spread_rows],
                    y=[r.spread_value for r in spread_rows],
                    mode="lines+markers",
                    name=st,
                ))

        return metrics, curve_fig, footnote_children, history_fig, spread_fig

    finally:
        session.close()


# ─── Populate table contract dropdowns ───────────────────────────────────────

@callback(
    Output("futures-table-cl-contract",   "options"),
    Output("futures-table-cl-contract",   "value"),
    Output("futures-table-coil-contract", "options"),
    Output("futures-table-coil-contract", "value"),
    Input("auto-refresh", "n_intervals"),
)
def populate_table_dropdowns(_n):
    session = get_session()
    try:
        from sqlalchemy import func as sa_func
        opts, defaults = {}, {}
        for sym in ("CL", "COIL"):
            months = [
                r[0] for r in session.query(FuturesCurve.contract_month)
                .filter(FuturesCurve.symbol == sym)
                .distinct()
                .order_by(FuturesCurve.contract_month)
                .all()
            ]
            opts[sym] = [{"label": _contract_label(sym, m), "value": m} for m in months]
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


# ─── Fill price history tables ────────────────────────────────────────────────

@callback(
    Output("futures-table-cl",   "data"),
    Output("futures-table-coil", "data"),
    Input("futures-table-cl-contract",   "value"),
    Input("futures-table-coil-contract", "value"),
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
            rows = (
                session.query(FuturesCurve)
                .filter(
                    FuturesCurve.symbol == sym,
                    FuturesCurve.contract_month == contract,
                    FuturesCurve.date >= start_date,
                    FuturesCurve.date <= end_date,
                )
                .order_by(FuturesCurve.date.desc())
                .all()
            )
            return [
                {
                    "date":   r.date.strftime("%Y-%m-%d"),
                    "price":  f"{r.settlement_price:.2f}" if r.settlement_price is not None else "\u2014",
                    "volume": f"{r.volume:,}"        if r.volume        is not None else "\u2014",
                    "oi":     f"{r.open_interest:,}" if r.open_interest is not None else "\u2014",
                }
                for r in rows
            ]

        return _rows("CL", cl_contract), _rows("COIL", coil_contract)
    finally:
        session.close()
