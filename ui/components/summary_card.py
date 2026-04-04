"""
Summary Card Component — reusable metric/summary display cards.
"""

import dash_bootstrap_components as dbc
from dash import html


def metric_card(title: str, value: str, color: str = "light") -> dbc.Card:
    """Create a simple metric card with title and value."""
    return dbc.Card(dbc.CardBody([
        html.H6(title, className="text-muted"),
        html.H4(value),
    ]))


def summary_card(title: str, text: str, severity: int = 0) -> dbc.Card:
    """Create a summary card with title, text, and optional severity badge."""
    color = "danger" if severity >= 7 else "warning" if severity >= 4 else "info"
    return dbc.Card([
        dbc.CardHeader([
            title,
            dbc.Badge(f"Sev: {severity}", color=color, className="ms-2") if severity else None,
        ]),
        dbc.CardBody(html.P(text, style={"fontSize": "0.9rem"})),
    ])
