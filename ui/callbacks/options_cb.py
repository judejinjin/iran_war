"""
Options Tab Callbacks — vol surface, smile, risk reversal, open interest, straddles.
"""

from datetime import date, datetime
from collections import defaultdict
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output
from sqlalchemy import func

from db.database import get_session, OptionsChain, VolSurface, FuturesCurve


@callback(
    Output("opt-metrics-row", "children"),
    Output("opt-vol-surface", "figure"),
    Output("opt-vol-smile", "figure"),
    Output("opt-risk-reversal", "figure"),
    Output("opt-open-interest", "figure"),
    Input("opt-underlying-toggle", "value"),
    Input("opt-date-range", "start_date"),
    Input("opt-date-range", "end_date"),
    Input("auto-refresh", "n_intervals"),
)
def update_options(underlying, start_date, end_date, _n):
    session = get_session()
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date[:10], "%Y-%m-%d").date()

        # ─── Metrics ─────────────────────────────────────────────────
        latest_vol = session.query(VolSurface).filter(
            VolSurface.underlying == underlying,
        ).order_by(VolSurface.date.desc()).first()

        atm_vol = f"{latest_vol.atm_vol*100:.1f}%" if latest_vol and latest_vol.atm_vol else "N/A"
        skew = f"{latest_vol.skew_25d*100:.1f}%" if latest_vol and latest_vol.skew_25d else "N/A"

        metrics = [
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6(f"{underlying} ATM Vol", className="text-muted"),
                html.H4(atm_vol),
            ])), width=2),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("25d Skew", className="text-muted"),
                html.H4(skew),
            ])), width=2),
        ]

        # ─── IV Surface ─────────────────────────────────────────────
        vol_fig = go.Figure()
        vol_fig.update_layout(template="oil_dark", title="Implied Volatility Surface", height=400)

        options = session.query(OptionsChain).filter(
            OptionsChain.underlying == underlying,
            OptionsChain.date >= start_date,
            OptionsChain.date <= end_date,
            OptionsChain.implied_vol.isnot(None),
        ).order_by(OptionsChain.expiry_date, OptionsChain.strike).all()

        if options:
            from collections import defaultdict
            by_expiry = defaultdict(list)
            for o in options:
                by_expiry[o.expiry_date].append(o)

            for expiry, opts in sorted(by_expiry.items())[:6]:
                vol_fig.add_trace(go.Scatter(
                    x=[o.strike for o in opts],
                    y=[o.implied_vol for o in opts],
                    mode="lines+markers",
                    name=str(expiry),
                ))
            vol_fig.update_layout(
                xaxis_title="Strike", yaxis_title="Implied Vol",
            )
        else:
            vol_fig.add_annotation(text="No options data available",
                                    xref="paper", yref="paper", x=0.5, y=0.5,
                                    showarrow=False, font=dict(size=16))

        # ─── Vol Smile ───────────────────────────────────────────────
        smile_fig = go.Figure()
        smile_fig.update_layout(template="oil_dark", title="Volatility Smile", height=400)

        latest_date_row = session.query(OptionsChain.date).filter(
            OptionsChain.underlying == underlying,
            OptionsChain.implied_vol.isnot(None),
        ).order_by(OptionsChain.date.desc()).first()

        if latest_date_row:
            latest_opts = session.query(OptionsChain).filter(
                OptionsChain.underlying == underlying,
                OptionsChain.date == latest_date_row[0],
                OptionsChain.implied_vol.isnot(None),
            ).order_by(OptionsChain.strike).all()

            calls = [o for o in latest_opts if o.option_type == "CALL"]
            puts = [o for o in latest_opts if o.option_type == "PUT"]
            for data, name in [(calls, "Calls"), (puts, "Puts")]:
                if data:
                    smile_fig.add_trace(go.Scatter(
                        x=[o.strike for o in data],
                        y=[o.implied_vol for o in data],
                        mode="lines+markers", name=name,
                    ))
            smile_fig.update_layout(xaxis_title="Strike", yaxis_title="IV")
        else:
            smile_fig.add_annotation(text="No data", xref="paper", yref="paper",
                                      x=0.5, y=0.5, showarrow=False, font=dict(size=16))

        # ─── Risk Reversal ───────────────────────────────────────────
        rr_fig = go.Figure()
        rr_fig.update_layout(
            template="oil_dark", title="25-Delta Risk Reversal",
            xaxis_title="Date", yaxis_title="RR (vol points)", height=400,
        )

        vol_data = session.query(VolSurface).filter(
            VolSurface.underlying == underlying,
            VolSurface.date >= start_date,
            VolSurface.date <= end_date,
            VolSurface.skew_25d.isnot(None),
        ).order_by(VolSurface.date).all()

        if vol_data:
            rr_fig.add_trace(go.Scatter(
                x=[v.date for v in vol_data],
                y=[v.skew_25d for v in vol_data],
                mode="lines+markers", name="25d RR",
            ))
        else:
            rr_fig.add_annotation(text="No vol surface data", xref="paper", yref="paper",
                                    x=0.5, y=0.5, showarrow=False, font=dict(size=16))

        # ─── Open Interest / Volume by Strike ─────────────────────────
        oi_fig = go.Figure()

        if latest_date_row:
            oi_data = session.query(OptionsChain).filter(
                OptionsChain.underlying == underlying,
                OptionsChain.date == latest_date_row[0],
                OptionsChain.open_interest.isnot(None),
                OptionsChain.open_interest > 0,
            ).order_by(OptionsChain.strike).all()

            if oi_data:
                # Use OI data
                calls_oi = [o for o in oi_data if o.option_type == "CALL"]
                puts_oi = [o for o in oi_data if o.option_type == "PUT"]
                if calls_oi:
                    oi_fig.add_trace(go.Bar(
                        x=[o.strike for o in calls_oi],
                        y=[o.open_interest for o in calls_oi],
                        name="Calls OI",
                    ))
                if puts_oi:
                    oi_fig.add_trace(go.Bar(
                        x=[o.strike for o in puts_oi],
                        y=[o.open_interest for o in puts_oi],
                        name="Puts OI",
                    ))
                oi_fig.update_layout(
                    template="oil_dark", title="Open Interest by Strike",
                    xaxis_title="Strike", yaxis_title="Open Interest",
                    barmode="group", height=400,
                )
            else:
                # Fallback: show IV by strike (always available)
                iv_data = session.query(OptionsChain).filter(
                    OptionsChain.underlying == underlying,
                    OptionsChain.date == latest_date_row[0],
                    OptionsChain.implied_vol.isnot(None),
                ).order_by(OptionsChain.strike).all()

                if iv_data:
                    calls_iv = [o for o in iv_data if o.option_type == "CALL"]
                    puts_iv = [o for o in iv_data if o.option_type == "PUT"]
                    if calls_iv:
                        oi_fig.add_trace(go.Bar(
                            x=[o.strike for o in calls_iv],
                            y=[o.implied_vol for o in calls_iv],
                            name="Calls IV",
                        ))
                    if puts_iv:
                        oi_fig.add_trace(go.Bar(
                            x=[o.strike for o in puts_iv],
                            y=[o.implied_vol for o in puts_iv],
                            name="Puts IV",
                        ))
                    oi_fig.update_layout(
                        template="oil_dark",
                        title="IV by Strike (OI unavailable — run IB backfill to fetch)",
                        xaxis_title="Strike", yaxis_title="Implied Vol",
                        barmode="group", height=400,
                    )
                else:
                    oi_fig.update_layout(template="oil_dark", title="Open Interest by Strike", height=400)
                    oi_fig.add_annotation(text="No OI data — run --ib-options to fetch",
                                          xref="paper", yref="paper", x=0.5, y=0.5,
                                          showarrow=False, font=dict(size=16))
        else:
            oi_fig.update_layout(template="oil_dark", title="Open Interest by Strike", height=400)
            oi_fig.add_annotation(text="No data", xref="paper", yref="paper",
                                    x=0.5, y=0.5, showarrow=False, font=dict(size=16))

        return metrics, vol_fig, smile_fig, rr_fig, oi_fig

    finally:
        session.close()


# ─── Chain Expiry Dropdowns ──────────────────────────────────────────────────

def _get_expiries(underlying):
    """Return sorted list of available expiry dates for an underlying."""
    session = get_session()
    try:
        rows = (
            session.query(OptionsChain.expiry_date)
            .filter(OptionsChain.underlying == underlying)
            .distinct()
            .order_by(OptionsChain.expiry_date)
            .all()
        )
        return [{"label": str(r[0]), "value": str(r[0])} for r in rows]
    finally:
        session.close()


def _first_active_expiry(opts):
    """Return the value of the first expiry that hasn't expired yet."""
    today = date.today()
    for opt in opts:
        try:
            if datetime.strptime(opt["value"][:10], "%Y-%m-%d").date() >= today:
                return opt["value"]
        except (ValueError, KeyError):
            continue
    return opts[0]["value"] if opts else None


@callback(
    Output("opt-wti-chain-expiry", "options"),
    Output("opt-wti-chain-expiry", "value"),
    Input("auto-refresh", "n_intervals"),
)
def populate_wti_expiries(_n):
    opts = _get_expiries("CL")
    val = _first_active_expiry(opts) if opts else None
    return opts, val


@callback(
    Output("opt-brent-chain-expiry", "options"),
    Output("opt-brent-chain-expiry", "value"),
    Input("auto-refresh", "n_intervals"),
)
def populate_brent_expiries(_n):
    opts = _get_expiries("COIL")
    val = _first_active_expiry(opts) if opts else None
    return opts, val


# ─── Calls & Puts Chain Tables ───────────────────────────────────────────────

def _build_chain_table(underlying, expiry_str):
    """Build a side-by-side Calls | Strike | Puts table for one expiry."""
    if not expiry_str:
        return html.P("Select an expiry", className="text-muted text-center my-4")

    expiry_date = datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
    session = get_session()
    try:
        # Get most recent date's data for this expiry
        latest_row = (
            session.query(OptionsChain.date)
            .filter(
                OptionsChain.underlying == underlying,
                OptionsChain.expiry_date == expiry_date,
            )
            .order_by(OptionsChain.date.desc())
            .first()
        )
        if not latest_row:
            return html.P("No data for this expiry", className="text-muted text-center my-4")

        rows = (
            session.query(OptionsChain)
            .filter(
                OptionsChain.underlying == underlying,
                OptionsChain.expiry_date == expiry_date,
                OptionsChain.date == latest_row[0],
            )
            .order_by(OptionsChain.strike)
            .all()
        )

        # Group by strike
        by_strike = defaultdict(dict)
        for r in rows:
            by_strike[r.strike][r.option_type] = r

        strikes = sorted(by_strike.keys())
        if not strikes:
            return html.P("No data", className="text-muted text-center my-4")

        # Get underlying price for this date — use stored underlying_contract_month
        # from the options data (mapped during backfill via reqSecDefOptParams)
        ucm_row = (
            session.query(OptionsChain.underlying_contract_month)
            .filter(
                OptionsChain.underlying == underlying,
                OptionsChain.expiry_date == expiry_date,
                OptionsChain.underlying_contract_month.isnot(None),
            )
            .first()
        )
        # Use stored mapping if available, else offset-based fallback
        # CL: option exp month + 1, COIL: option exp month + 2
        if ucm_row:
            expiry_cm = ucm_row[0]
        else:
            offset = {"CL": 1, "COIL": 2}.get(underlying, 0)
            m = expiry_date.month + offset
            y = expiry_date.year
            while m > 12:
                m -= 12
                y += 1
            expiry_cm = f"{y}-{m:02d}"

        und_row = (
            session.query(FuturesCurve.settlement_price, FuturesCurve.contract_month)
            .filter(
                FuturesCurve.symbol == underlying,
                FuturesCurve.date == latest_row[0],
                FuturesCurve.contract_month == expiry_cm,
            )
            .first()
        )
        if not und_row:
            # Try nearest date for the correct contract month (within 5 days)
            from sqlalchemy import func as sa_func
            und_row = (
                session.query(FuturesCurve.settlement_price, FuturesCurve.contract_month)
                .filter(
                    FuturesCurve.symbol == underlying,
                    FuturesCurve.contract_month == expiry_cm,
                    FuturesCurve.settlement_price.isnot(None),
                )
                .order_by(sa_func.abs(sa_func.julianday(FuturesCurve.date) - sa_func.julianday(latest_row[0])))
                .first()
            )
        if not und_row:
            # Fallback: nearest available contract month on this date
            und_row = (
                session.query(FuturesCurve.settlement_price, FuturesCurve.contract_month)
                .filter(
                    FuturesCurve.symbol == underlying,
                    FuturesCurve.date == latest_row[0],
                    FuturesCurve.settlement_price.isnot(None),
                )
                .order_by(FuturesCurve.contract_month)
                .first()
            )
        und_price = und_row[0] if und_row else None
        und_cm = und_row[1] if und_row else expiry_cm

        def _fmt(val, decimals=2):
            if val is None:
                return "—"
            return f"{val:.{decimals}f}"

        def _fmt_pct(val):
            if val is None:
                return "—"
            return f"{val * 100:.1f}%"

        # Build table header
        header = html.Thead(html.Tr([
            # Call side
            html.Th("IV", className="text-end", style={"width": "11%"}),
            html.Th("Delta", className="text-end", style={"width": "11%"}),
            html.Th("Mid", className="text-end", style={"width": "11%"}),
            # Strike
            html.Th("Strike", className="text-center fw-bold",
                     style={"width": "12%", "backgroundColor": "rgba(255,255,255,0.05)"}),
            # Put side
            html.Th("Mid", style={"width": "11%"}),
            html.Th("Delta", style={"width": "11%"}),
            html.Th("IV", style={"width": "11%"}),
        ], className="table-dark"))

        # Build table rows
        body_rows = []
        for s in strikes:
            call = by_strike[s].get("CALL")
            put = by_strike[s].get("PUT")

            body_rows.append(html.Tr([
                # Call side (right-aligned)
                html.Td(_fmt_pct(call.implied_vol) if call else "—", className="text-end text-info"),
                html.Td(_fmt(call.delta) if call else "—", className="text-end"),
                html.Td(_fmt(call.last_price) if call else "—",
                         className="text-end fw-bold"),
                # Strike (center, highlighted)
                html.Td(f"{s:.0f}", className="text-center fw-bold",
                         style={"backgroundColor": "rgba(255,255,255,0.05)"}),
                # Put side (left-aligned)
                html.Td(_fmt(put.last_price) if put else "—", className="fw-bold"),
                html.Td(_fmt(put.delta) if put else "—"),
                html.Td(_fmt_pct(put.implied_vol) if put else "—", className="text-info"),
            ]))

        caption = html.Small(
            f"Data as of {latest_row[0]}  |  Expiry {expiry_date}",
            className="text-muted",
        )

        table = dbc.Table(
            [header, html.Tbody(body_rows)],
            bordered=True, hover=True, size="sm", className="mb-1",
            style={"fontSize": "0.85rem"},
        )

        # Build futures contract ticker label (e.g. "CLM6", "COILM6")
        def _month_code(cm_str):
            """Convert 'YYYY-MM' to futures month code like 'M6' (Jun 2026)."""
            codes = {1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}
            try:
                y, m = cm_str.split('-')
                return f"{codes[int(m)]}{y[-1]}"
            except Exception:
                return cm_str

        mc = _month_code(und_cm)
        ticker_label = f"{underlying}{mc}"
        # Full month name for display
        import calendar
        try:
            y, m = und_cm.split('-')
            month_name = f"{calendar.month_abbr[int(m)]} {y}"
        except Exception:
            month_name = und_cm

        und_label = (
            f"Underlying: {ticker_label} ({month_name}) ${und_price:.2f}"
            if und_price else f"Underlying: {ticker_label} ({month_name}) N/A"
        )

        return html.Div([
            html.Div([
                html.Span(und_label, className="fw-bold me-3"),
                html.Span(f"Data as of {latest_row[0]}", className="text-muted me-3"),
                html.Span(f"Expiry {expiry_date}", className="text-muted"),
            ], className="mb-2"),
            html.Div("CALLS", className="text-center text-success fw-bold",
                      style={"display": "inline-block", "width": "46%"}),
            html.Div("", style={"display": "inline-block", "width": "8%"}),
            html.Div("PUTS", className="text-center text-danger fw-bold",
                      style={"display": "inline-block", "width": "46%"}),
            table,
            caption,
        ])

    finally:
        session.close()


@callback(
    Output("opt-wti-chain-table", "children"),
    Input("opt-wti-chain-expiry", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_wti_chain(expiry, _n):
    return _build_chain_table("CL", expiry)


@callback(
    Output("opt-brent-chain-table", "children"),
    Input("opt-brent-chain-expiry", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_brent_chain(expiry, _n):
    return _build_chain_table("COIL", expiry)
