"""
Futures Tab Callbacks — query DB for curves & spreads, render Plotly charts.
"""

from datetime import date, datetime
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, no_update

from db.database import get_session, FuturesCurve, Spread


@callback(
    Output("futures-metrics-row", "children"),
    Output("futures-curve-chart", "figure"),
    Output("futures-price-history", "figure"),
    Output("futures-spread-chart", "figure"),
    Input("futures-date-range", "start_date"),
    Input("futures-date-range", "end_date"),
    Input("futures-symbol-toggle", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_futures(start_date, end_date, symbol_filter, _n):
    session = get_session()
    today = date.today()

    try:
        # Parse dates
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        symbols = ["CL", "BZ"] if symbol_filter == "BOTH" else [symbol_filter]

        # ─── Key Metrics ──────────────────────────────────────────────
        metrics = []
        for sym in ["CL", "BZ"]:
            latest = session.query(FuturesCurve).filter(
                FuturesCurve.symbol == sym,
            ).order_by(FuturesCurve.date.desc(), FuturesCurve.contract_month).first()

            label = "WTI (CL)" if sym == "CL" else "Brent (BZ)"
            price = f"${latest.settlement_price:.2f}" if latest and latest.settlement_price else "N/A"
            metrics.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(label, className="text-muted"),
                html.H4(price),
            ])), width=2))

        # Brent-WTI spread
        latest_spread = session.query(Spread).filter(
            Spread.spread_type == "BZ-CL"
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

        colors = {"CL": "#FF6B35", "BZ": "#1E90FF"}
        has_curve = False

        for sym in ["CL", "BZ"]:
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
                    label = "WTI (CL)" if sym == "CL" else "Brent (BZ)"
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
            for sym in ["CL", "BZ"]:
                rows = session.query(FuturesCurve).filter(
                    FuturesCurve.symbol == sym,
                ).order_by(FuturesCurve.date.desc()).limit(20).all()
                rows = list(reversed(rows))
                if rows:
                    label = "WTI (CL)" if sym == "CL" else "Brent (BZ)"
                    curve_fig.add_trace(go.Scatter(
                        x=[r.date for r in rows],
                        y=[r.settlement_price for r in rows],
                        mode="lines+markers",
                        name=label,
                        line=dict(color=colors[sym]),
                    ))

        # ─── Price History Chart ──────────────────────────────────────
        history_fig = go.Figure()
        history_fig.update_layout(
            template="oil_dark",
            title="Front-Month Price History",
            xaxis_title="Date",
            yaxis_title="Price ($/bbl)",
            height=400,
        )

        from sqlalchemy import func as sa_func
        for sym in symbols:
            subq = session.query(
                FuturesCurve.date,
                sa_func.min(FuturesCurve.contract_month).label("front_month"),
            ).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.date >= start_date,
                FuturesCurve.date <= end_date,
            ).group_by(FuturesCurve.date).subquery()

            rows = session.query(FuturesCurve).join(
                subq,
                (FuturesCurve.date == subq.c.date) &
                (FuturesCurve.contract_month == subq.c.front_month) &
                (FuturesCurve.symbol == sym),
            ).order_by(FuturesCurve.date).all()

            if rows:
                label = "WTI (CL)" if sym == "CL" else "Brent (BZ)"
                history_fig.add_trace(go.Scatter(
                    x=[r.date for r in rows],
                    y=[r.settlement_price for r in rows],
                    mode="lines",
                    name=label,
                ))

        # ─── Spread Chart ─────────────────────────────────────────────
        spread_fig = go.Figure()
        spread_fig.update_layout(
            template="oil_dark",
            title="Spreads Over Time",
            xaxis_title="Date",
            yaxis_title="Spread ($/bbl)",
            height=400,
        )

        # Always compute Brent-WTI spread on the fly from front-month prices
        cl_front = {}
        bz_front = {}
        for sym in ["CL", "BZ"]:
            subq = session.query(
                FuturesCurve.date,
                sa_func.min(FuturesCurve.contract_month).label("front_month"),
            ).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.date >= start_date,
                FuturesCurve.date <= end_date,
            ).group_by(FuturesCurve.date).subquery()

            rows = session.query(FuturesCurve).join(
                subq,
                (FuturesCurve.date == subq.c.date) &
                (FuturesCurve.contract_month == subq.c.front_month) &
                (FuturesCurve.symbol == sym),
            ).order_by(FuturesCurve.date).all()

            if sym == "CL":
                cl_front = {r.date: r.settlement_price for r in rows}
            else:
                bz_front = {r.date: r.settlement_price for r in rows}

        common_dates = sorted(set(cl_front) & set(bz_front))
        if common_dates:
            bz_cl_spreads = [bz_front[d] - cl_front[d] for d in common_dates]
            spread_fig.add_trace(go.Scatter(
                x=common_dates, y=bz_cl_spreads,
                mode="lines+markers", name="Brent-WTI",
            ))

        # Calendar spreads — compute on-the-fly from FuturesCurve data
        # For each date & symbol, rank contracts by contract_month and compute
        # M1-M6 and M1-M12 spreads (M1-M2 is often ~0, so skip it)
        from sqlalchemy import func as sa_f2
        for sym in ["CL", "BZ"]:
            curve_rows = session.query(FuturesCurve).filter(
                FuturesCurve.symbol == sym,
                FuturesCurve.date >= start_date,
                FuturesCurve.date <= end_date,
            ).order_by(FuturesCurve.date, FuturesCurve.contract_month).all()

            # Group by date
            by_date = {}
            for r in curve_rows:
                by_date.setdefault(r.date, []).append(r)

            cal_data = {}  # {offset_label: [(date, spread_val), ...]}
            for dt in sorted(by_date):
                contracts = by_date[dt]
                if len(contracts) < 2:
                    continue
                m1_price = contracts[0].settlement_price
                if m1_price is None:
                    continue
                for offset, lbl in [(5, "M1-M6"), (11, "M1-M12")]:
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
        skip_types = {"BZ-CL", "CL_M1-M2", "BZ_M1-M2", "CL_M1-M6", "BZ_M1-M6",
                      "CL_M1-M12", "BZ_M1-M12"}
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

        return metrics, curve_fig, history_fig, spread_fig

    finally:
        session.close()
