"""
Supply / Demand Tab Callbacks.

Single @callback fires on: date range, flow toggle, product, countries, YoY switch,
and auto-refresh. Drives: KPI cards, trend chart, bar chart, choropleth map, data table.
"""

from datetime import date, datetime, timedelta
from collections import defaultdict

import plotly.graph_objects as go
import plotly.express as px
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output

from config import SD_PRODUCTS, SD_SUPPLY_PRODUCTS, SD_DEMAND_PRODUCTS, SD_COUNTRIES, WAR_START_DATE
from db.database import get_session, SupplyDemand

_WAR_START = datetime.strptime(WAR_START_DATE, "%Y-%m-%d").date()

# Colour palette for countries (cycles if > 10 selected)
_PALETTE = [
    "#2E86DE", "#E74C3C", "#F39C12", "#27AE60", "#8E44AD",
    "#16A085", "#D35400", "#2980B9", "#C0392B", "#7F8C8D",
    "#1ABC9C", "#F1C40F", "#9B59B6", "#E67E22", "#BDC3C7",
]

# EIA 3-letter country codes (for choropleth locationmode="ISO-3")
_ISO2_TO_3 = {
    "SA": "SAU", "RU": "RUS", "US": "USA", "IQ": "IRQ", "AE": "ARE",
    "IR": "IRN", "KW": "KWT", "NG": "NGA", "LY": "LBY", "VE": "VEN",
    "CN": "CHN", "BR": "BRA", "CA": "CAN", "MX": "MEX", "NO": "NOR",
    "IN": "IND", "JP": "JPN", "DE": "DEU", "KR": "KOR", "FR": "FRA",
    "GB": "GBR", "IT": "ITA", "ES": "ESP", "SG": "SGP", "AU": "AUS",
}


def _parse_date(d) -> date | None:
    if d is None:
        return None
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _fmt(val, decimals=1):
    if val is None:
        return "N/A"
    return f"{val:,.{decimals}f}"


def _kpi_card(title: str, value: str, subtitle: str = "", color: str = "#2E86DE"):
    return dbc.Col(dbc.Card([
        dbc.CardBody([
            html.P(title, className="text-muted small mb-1"),
            html.H4(value, style={"color": color, "fontWeight": "bold"}),
            html.P(subtitle, className="text-muted small mb-0"),
        ])
    ], className="h-100 text-center"), xs=12, sm=6, md=4, lg=3)


@callback(
    Output("sd-kpi-row",    "children"),
    Output("sd-trend-chart", "figure"),
    Output("sd-bar-chart",   "figure"),
    Output("sd-map-chart",   "figure"),
    Output("sd-data-table",  "data"),
    Output("sd-trend-header", "children"),
    Output("sd-bar-header",   "children"),
    Output("sd-map-header",   "children"),
    Input("sd-date-range",   "start_date"),
    Input("sd-date-range",   "end_date"),
    Input("sd-flow",         "value"),
    Input("sd-product",      "value"),
    Input("sd-countries",    "value"),
    Input("sd-yoy",          "value"),
    Input("auto-refresh",    "n_intervals"),
)
def update_sd(start_date, end_date, flow, product_key, countries, yoy, _n):
    session = get_session()
    empty_fig = go.Figure()
    empty_fig.update_layout(
        paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e",
        font_color="#aaa",
        annotations=[{"text": "No data", "xref": "paper", "yref": "paper",
                      "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 16}}],
    )

    start_dt = _parse_date(start_date) or date(2024, 1, 1)
    end_dt   = _parse_date(end_date)   or date.today()
    product_key = product_key or "total"
    flow = flow or "supply"
    countries = countries or ["US"]
    _prod_dict = SD_SUPPLY_PRODUCTS if flow == "supply" else SD_DEMAND_PRODUCTS
    prod_label = _prod_dict.get(product_key, SD_PRODUCTS.get(product_key, {})).get("label", product_key)
    flow_label = {"supply": "Supply", "demand": "Demand", "balance": "Balance"}.get(flow, flow)
    trend_title = f"{prod_label} — {flow_label} Trend {'(YoY %)' if yoy else '(kbd)'}"
    bar_title   = f"Latest Month — {prod_label} {flow_label} (kbd)"
    map_title   = f"World Map — {prod_label} {flow_label} Latest Month (kbd)"

    try:
        # ── Pull all data for the selected product + relevant flows ─────────
        # For balance we need both supply and demand; otherwise just the one flow.
        if flow == "balance":
            query_flows = ["supply", "demand"]
        else:
            query_flows = [flow]

        all_rows = (
            session.query(SupplyDemand)
            .filter(
                SupplyDemand.product == product_key,
                SupplyDemand.flow.in_(query_flows),
                SupplyDemand.date <= end_dt,
            )
            .order_by(SupplyDemand.date)
            .all()
        )

        # Organise into {country: {flow: [(date, value_kbd)]}}
        raw: dict[str, dict[str, list]] = defaultdict(lambda: {"supply": [], "demand": []})
        for r in all_rows:
            raw[r.country][r.flow].append((r.date, r.value_kbd))

        # ── Compute effective series per country ──────────────────────────
        # series[country] = sorted list of (date, value) for the requested flow/balance
        series: dict[str, list[tuple[date, float]]] = {}
        all_countries_in_db = set(raw.keys())

        for country in SD_COUNTRIES:  # maintain config order for map
            if country not in all_countries_in_db:
                series[country] = []
                continue
            if flow == "balance":
                sup_map = dict(raw[country]["supply"])
                dem_map = dict(raw[country]["demand"])
                common  = sorted(set(sup_map) & set(dem_map))
                series[country] = [(d, sup_map[d] - dem_map[d]) for d in common]
            elif flow == "supply":
                series[country] = sorted(raw[country]["supply"])
            else:
                series[country] = sorted(raw[country]["demand"])

        # ── YoY conversion ────────────────────────────────────────────────
        def _yoy_series(pts: list[tuple[date, float]]) -> list[tuple[date, float]]:
            if len(pts) < 13:
                return []
            result = []
            val_map = {d: v for d, v in pts}
            for d, v in pts:
                prior_date = date(d.year - 1, d.month, d.day)
                # find closest match ± 15 days
                prior = None
                for delta in range(16):
                    for sign in (1, -1):
                        candidate = prior_date + timedelta(days=delta * sign)
                        if candidate in val_map:
                            prior = val_map[candidate]
                            break
                    if prior is not None:
                        break
                if prior is not None and prior != 0:
                    result.append((d, (v / prior - 1) * 100))
            return result

        display_series: dict[str, list[tuple[date, float]]] = {}
        for country in series:
            pts = series[country]
            if yoy:
                display_series[country] = _yoy_series(pts)
            else:
                display_series[country] = pts

        # ── Filter to date range for trend chart ─────────────────────────
        filtered: dict[str, list[tuple[date, float]]] = {}
        for country, pts in display_series.items():
            filtered[country] = [(d, v) for d, v in pts if start_dt <= d <= end_dt]

        # ── Latest month value per country (from unfiltered series for KPIs/bar/map) ─
        latest_vals: dict[str, float | None] = {}
        for country in SD_COUNTRIES:
            pts = display_series[country]
            latest_vals[country] = pts[-1][1] if pts else None

        # ── KPI Cards ─────────────────────────────────────────────────────
        # 1. World total (sum of latest values for countries with data)
        world_total = sum(v for v in latest_vals.values() if v is not None)
        # 2. YoY change for selected countries
        yoy_pcts = []
        for c in countries:
            pts = series[c]  # always absolute for YoY calc
            yoy_pts = _yoy_series(pts)
            if yoy_pts:
                yoy_pcts.append(yoy_pts[-1][1])
        avg_yoy = (sum(yoy_pcts) / len(yoy_pcts)) if yoy_pcts else None
        # 3. War drawdown: latest vs war start for selected countries
        war_changes = []
        for c in countries:
            pts = series[c]
            war_pt = next((v for d, v in pts if d >= _WAR_START), None)
            latest = latest_vals.get(c)
            if war_pt is not None and latest is not None:
                war_changes.append(latest - war_pt)
        war_net = sum(war_changes) if war_changes else None

        cards = [
            _kpi_card(
                f"World Total {flow_label}",
                f"{_fmt(world_total, 0)} kbd",
                f"{prod_label} • latest month",
                "#2E86DE",
            ),
            _kpi_card(
                "Avg YoY Change (selected)",
                f"{_fmt(avg_yoy, 1)}%" if avg_yoy is not None else "N/A",
                "vs same month prior year",
                "#27AE60" if (avg_yoy or 0) >= 0 else "#E74C3C",
            ),
            _kpi_card(
                f"War Drawdown (selected)",
                f"{_fmt(war_net, 0)} kbd" if war_net is not None else "N/A",
                f"vs {WAR_START_DATE} baseline",
                "#E74C3C" if (war_net or 0) < 0 else "#27AE60",
            ),
        ]

        # ── Trend Chart ───────────────────────────────────────────────────
        trend_fig = go.Figure()
        for i, country in enumerate(countries):
            pts = filtered.get(country, [])
            if not pts:
                continue
            dates = [d for d, _ in pts]
            vals  = [v for _, v in pts]
            color = _PALETTE[i % len(_PALETTE)]
            trend_fig.add_trace(go.Scatter(
                x=dates, y=vals,
                mode="lines",
                name=SD_COUNTRIES.get(country, country),
                line=dict(color=color, width=2),
                hovertemplate="%{x|%b %Y}<br>%{y:,.1f}" + ("%" if yoy else " kbd") + "<extra>" + SD_COUNTRIES.get(country, country) + "</extra>",
            ))
        # War start vertical line
        if _WAR_START >= start_dt:
            trend_fig.add_shape(type="line", x0=_WAR_START, x1=_WAR_START, y0=0, y1=1,
                                xref="x", yref="paper", line=dict(color="#E74C3C", width=1.5, dash="dot"))
            trend_fig.add_annotation(x=_WAR_START, y=1, xref="x", yref="paper",
                                     text="War Start", showarrow=False, font=dict(color="#E74C3C", size=10),
                                     yanchor="bottom")
        trend_fig.update_layout(
            paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e", font_color="#E0E0E0",
            xaxis=dict(gridcolor="#2a2a3e", showgrid=True),
            yaxis=dict(gridcolor="#2a2a3e", showgrid=True,
                       title="YoY %" if yoy else "kbd"),
            legend=dict(bgcolor="rgba(0,0,0,0.3)"),
            margin=dict(l=50, r=20, t=20, b=40),
            hovermode="x unified",
        )

        # ── Bar Chart — latest month, all selected countries ──────────────
        bar_data = sorted(
            [(c, latest_vals.get(c)) for c in countries if latest_vals.get(c) is not None],
            key=lambda x: x[1],
        )
        bar_countries = [SD_COUNTRIES.get(c, c) for c, _ in bar_data]
        bar_vals = [v for _, v in bar_data]

        if flow == "balance":
            bar_colors = ["#27AE60" if v >= 0 else "#E74C3C" for v in bar_vals]
        elif flow == "supply":
            bar_colors = "#2E86DE"
        else:
            bar_colors = "#E74C3C"

        bar_fig = go.Figure(go.Bar(
            x=bar_vals,
            y=bar_countries,
            orientation="h",
            marker_color=bar_colors,
            hovertemplate="%{y}: %{x:,.1f} kbd<extra></extra>",
        ))
        bar_fig.update_layout(
            paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e", font_color="#E0E0E0",
            xaxis=dict(gridcolor="#2a2a3e", title="kbd"),
            yaxis=dict(gridcolor="#2a2a3e"),
            margin=dict(l=10, r=20, t=20, b=40),
        )

        # ── Choropleth Map — all countries with data ──────────────────────
        map_data = [
            {
                "iso3": _ISO2_TO_3.get(c),
                "country": SD_COUNTRIES.get(c, c),
                "value": v,
            }
            for c, v in latest_vals.items()
            if v is not None and _ISO2_TO_3.get(c)
        ]
        if map_data:
            if flow == "balance":
                color_scale = "RdBu"
                color_mid = 0
            elif flow == "supply":
                color_scale = "Blues"
                color_mid = None
            else:
                color_scale = "Reds"
                color_mid = None

            map_fig = go.Figure(go.Choropleth(
                locations=[d["iso3"] for d in map_data],
                z=[d["value"] for d in map_data],
                text=[d["country"] for d in map_data],
                colorscale=color_scale,
                zmid=color_mid,
                colorbar=dict(title="kbd", thickness=12),
                marker_line_color="#333",
                hovertemplate="%{text}: %{z:,.1f} kbd<extra></extra>",
            ))
            map_fig.update_layout(
                geo=dict(
                    showframe=False,
                    showcoastlines=True,
                    coastlinecolor="#444",
                    bgcolor="#1a1a2e",
                    landcolor="#1e2a3a",
                    oceancolor="#141a26",
                    showocean=True,
                    projection_type="natural earth",
                ),
                paper_bgcolor="#1a1a2e",
                font_color="#E0E0E0",
                margin=dict(l=0, r=0, t=0, b=0),
            )
        else:
            map_fig = empty_fig

        # ── Data Table — pivoted: supply + demand + balance per (date, country) ─
        # Pull both flows regardless of UI toggle for the table
        both_rows = (
            session.query(SupplyDemand)
            .filter(
                SupplyDemand.product == product_key,
                SupplyDemand.country.in_(countries),
                SupplyDemand.date >= start_dt,
                SupplyDemand.date <= end_dt,
            )
            .order_by(SupplyDemand.date.desc(), SupplyDemand.country)
            .all()
        )

        pivot: dict[tuple, dict] = {}
        for r in both_rows:
            key = (r.date, r.country)
            if key not in pivot:
                pivot[key] = {"date": str(r.date), "country": SD_COUNTRIES.get(r.country, r.country),
                               "product": prod_label, "supply_kbd": None, "demand_kbd": None}
            pivot[key][f"{r.flow}_kbd"] = round(r.value_kbd, 1)

        table_rows = []
        for (d, c), row_dict in sorted(pivot.items(), key=lambda x: x[0][0], reverse=True):
            s = row_dict["supply_kbd"]
            dem = row_dict["demand_kbd"]
            bal = round(s - dem, 1) if s is not None and dem is not None else None
            row_dict["balance_kbd"] = bal
            table_rows.append(row_dict)

        return cards, trend_fig, bar_fig, map_fig, table_rows, trend_title, bar_title, map_title

    except Exception as exc:
        import traceback
        traceback.print_exc()
        err = dbc.Alert(f"Error: {exc}", color="danger")
        return [err], empty_fig, empty_fig, empty_fig, [], trend_title, bar_title, map_title
    finally:
        session.close()
