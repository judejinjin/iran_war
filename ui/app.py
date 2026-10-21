"""
Dash Application — main app instance with dark theme and 7-tab navigation.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc
import plotly.io as pio
import plotly.graph_objects as go

from config import DASH_HOST, DASH_PORT, DASH_DEBUG

# ─── Global Plotly Theme — readable fonts on dark background ─────────────────
_dark = pio.templates["plotly_dark"]
_custom = go.layout.Template(layout=go.Layout(
    font=dict(family="Segoe UI, Helvetica, Arial, sans-serif", size=13, color="#E0E0E0"),
    hoverlabel=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(0,0,0,0)",
        font=dict(color="#F0F0F0", size=12, family="Segoe UI, Helvetica, Arial, sans-serif"),
        namelength=-1,
    ),
    legend=dict(
        font=dict(size=13, color="#E0E0E0"),
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(0,0,0,0)",
        borderwidth=0,
    ),
    title=dict(font=dict(size=16, color="#FFFFFF")),
    xaxis=dict(
        title_font=dict(size=13, color="#CCCCCC"),
        tickfont=dict(size=11, color="#BBBBBB"),
    ),
    yaxis=dict(
        title_font=dict(size=13, color="#CCCCCC"),
        tickfont=dict(size=11, color="#BBBBBB"),
    ),
))
pio.templates["oil_dark"] = _dark
pio.templates["oil_dark"].layout.update(_custom.layout)
pio.templates.default = "oil_dark"

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="Oil Super Spike Analyzer",
)

# ─── Shared State Stores ─────────────────────────────────────────────────────
stores = html.Div([
    dcc.Store(id="store-selected-date", storage_type="session"),
    dcc.Store(id="store-selected-scenario", storage_type="session"),
    dcc.Store(id="store-selected-underlying", data="CL", storage_type="session"),
    dcc.Store(id="cfg-init", data=1),  # triggers config tab population
    dcc.Interval(id="auto-refresh", interval=300_000, n_intervals=0),  # 5 min
])

# ─── Tab Definitions ─────────────────────────────────────────────────────────
TAB_STYLE = {"padding": "12px 20px", "fontWeight": "bold"}

tabs = dbc.Tabs(
    id="main-tabs",
    active_tab="tab-geopolitical",
    children=[
        dbc.Tab(label="Geopolitical", tab_id="tab-geopolitical", tab_style=TAB_STYLE),
        dbc.Tab(label="Infrastructure", tab_id="tab-infrastructure", tab_style=TAB_STYLE),
        dbc.Tab(label="Military", tab_id="tab-military", tab_style=TAB_STYLE),
        dbc.Tab(label="Futures", tab_id="tab-futures", tab_style=TAB_STYLE),
        dbc.Tab(label="Physical", tab_id="tab-physical", tab_style=TAB_STYLE),
        dbc.Tab(label="SPR", tab_id="tab-spr", tab_style=TAB_STYLE),
        dbc.Tab(label="Supply/Demand", tab_id="tab-supply-demand", tab_style=TAB_STYLE),
        dbc.Tab(label="Crack Spread", tab_id="tab-crack-spread", tab_style=TAB_STYLE),
        dbc.Tab(label="Options", tab_id="tab-options", tab_style=TAB_STYLE),
        dbc.Tab(label="Scenarios", tab_id="tab-scenarios", tab_style=TAB_STYLE),
        dbc.Tab(label="Analysis", tab_id="tab-analysis", tab_style=TAB_STYLE),
        dbc.Tab(label="Portfolio", tab_id="tab-portfolio", tab_style=TAB_STYLE),
        dbc.Tab(label="Config", tab_id="tab-config", tab_style=TAB_STYLE),
    ],
)

# ─── Layout ──────────────────────────────────────────────────────────────────
app.layout = dbc.Container([
    stores,
    dbc.Row(dbc.Col(html.H2(
        "\U0001f6e2\ufe0f Oil Super Spike Analyzer",
        className="text-center my-3",
    ))),
    dbc.Row(dbc.Col(tabs)),
    html.Div(id="tab-content", className="mt-3"),
], fluid=True)


# ─── Tab Router ──────────────────────────────────────────────────────────────
@app.callback(
    dash.Output("tab-content", "children"),
    dash.Input("main-tabs", "active_tab"),
)
def render_tab(active_tab):
    if active_tab == "tab-geopolitical":
        from ui.layouts.geopolitical import layout
        return layout
    elif active_tab == "tab-infrastructure":
        from ui.layouts.infrastructure import layout
        return layout
    elif active_tab == "tab-military":
        from ui.layouts.military import layout
        return layout
    elif active_tab == "tab-futures":
        from ui.layouts.futures import layout
        return layout
    elif active_tab == "tab-physical":
        from ui.layouts.physical import layout
        return layout
    elif active_tab == "tab-spr":
        from ui.layouts.spr import layout
        return layout
    elif active_tab == "tab-supply-demand":
        from ui.layouts.supply_demand import layout
        return layout
    elif active_tab == "tab-crack-spread":
        from ui.layouts.crack_spread import layout
        return layout
    elif active_tab == "tab-options":
        from ui.layouts.options import layout
        return layout
    elif active_tab == "tab-scenarios":
        from ui.layouts.scenarios import layout
        return layout
    elif active_tab == "tab-analysis":
        from ui.layouts.analysis import layout
        return layout
    elif active_tab == "tab-portfolio":
        from ui.layouts.portfolio import layout
        return layout
    elif active_tab == "tab-config":
        from ui.layouts.config_tab import layout
        return layout
    return html.Div("Select a tab")


def start_app():
    """Start the Dash server."""
    # Import callbacks to register them
    import ui.callbacks.futures_cb
    import ui.callbacks.physical_cb
    import ui.callbacks.spr_cb
    import ui.callbacks.supply_demand_cb
    import ui.callbacks.crack_spread_cb
    import ui.callbacks.geopolitical_cb
    import ui.callbacks.infrastructure_cb
    import ui.callbacks.military_cb
    import ui.callbacks.options_cb
    import ui.callbacks.scenarios_cb
    import ui.callbacks.analysis_cb
    import ui.callbacks.portfolio_cb
    import ui.callbacks.config_cb

    app.run(host=DASH_HOST, port=DASH_PORT, debug=DASH_DEBUG, use_reloader=False)


if __name__ == "__main__":
    start_app()
