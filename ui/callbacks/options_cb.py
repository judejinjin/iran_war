"""
Options Tab Callbacks — vol surface, smile, risk reversal, open interest.
"""

from datetime import date, datetime
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output

from db.database import get_session, OptionsChain, VolSurface


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

        # ─── Open Interest ───────────────────────────────────────────
        oi_fig = go.Figure()
        oi_fig.update_layout(
            template="oil_dark", title="Open Interest by Strike",
            xaxis_title="Strike", yaxis_title="Open Interest", height=400,
        )

        if latest_date_row:
            oi_data = session.query(OptionsChain).filter(
                OptionsChain.underlying == underlying,
                OptionsChain.date == latest_date_row[0],
                OptionsChain.open_interest.isnot(None),
            ).order_by(OptionsChain.strike).all()

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
            oi_fig.update_layout(barmode="group")
        else:
            oi_fig.add_annotation(text="No data", xref="paper", yref="paper",
                                    x=0.5, y=0.5, showarrow=False, font=dict(size=16))

        return metrics, vol_fig, smile_fig, rr_fig, oi_fig

    finally:
        session.close()
