"""
Map View Component — Leaflet maps for geopolitical, military, and infrastructure events.
"""

import dash_leaflet as dl
from dash import html


def create_event_map(events, height="400px"):
    """
    Create a Leaflet map with markers for geolocated events.

    Args:
        events: list of GeopoliticalEvent objects with latitude/longitude.
        height: CSS height for the map container.

    Returns:
        dash_leaflet.Map component.
    """
    markers = []
    for e in events:
        if e.latitude and e.longitude:
            sev = e.severity or 0
            color = "red" if sev >= 7 else "orange" if sev >= 4 else "blue"
            popup = dl.Popup(html.Div([
                html.Strong((e.headline or "Event")[:80]),
                html.Br(),
                html.Small(f"Severity: {sev} | {e.category or ''}"),
                html.Br(),
                html.Small(e.location_name or ""),
            ]))
            markers.append(
                dl.CircleMarker(
                    center=[e.latitude, e.longitude],
                    radius=max(5, sev),
                    color=color,
                    fillColor=color,
                    fillOpacity=0.7,
                    children=[popup],
                )
            )

    if not markers:
        return html.P("No geolocated events.", className="text-muted")

    # Center on Middle East / Persian Gulf
    center = [29.0, 52.0]
    zoom = 5

    return dl.Map(
        children=[
            dl.TileLayer(
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
                attribution='&copy; <a href="https://carto.com/">CARTO</a>',
            ),
            dl.LayerGroup(markers),
        ],
        center=center,
        zoom=zoom,
        style={"height": height, "width": "100%", "borderRadius": "8px"},
    )


def create_military_map(events, height="400px"):
    """
    Create a Leaflet map with markers for military events.

    Args:
        events: list of MilitaryEvent objects with latitude/longitude.
        height: CSS height for the map container.

    Returns:
        dash_leaflet.Map component.
    """
    markers = []
    for e in events:
        if e.latitude and e.longitude:
            side_color = "red" if e.side == "Iran" else "blue"
            popup = dl.Popup(html.Div([
                html.Strong((e.headline or e.event_type or "Event")[:80]),
                html.Br(),
                html.Small(f"{e.side} | {e.event_type or ''}"),
                html.Br(),
                html.Small(f"Loss: {e.loss_type or 'N/A'} x{e.quantity or '?'}"),
            ]))
            markers.append(
                dl.CircleMarker(
                    center=[e.latitude, e.longitude],
                    radius=8,
                    color=side_color,
                    fillColor=side_color,
                    fillOpacity=0.7,
                    children=[popup],
                )
            )

    if not markers:
        return html.P("No geolocated military events.", className="text-muted")

    center = [29.0, 52.0]
    zoom = 5

    return dl.Map(
        children=[
            dl.TileLayer(
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
                attribution='&copy; <a href="https://carto.com/">CARTO</a>',
            ),
            dl.LayerGroup(markers),
        ],
        center=center,
        zoom=zoom,
        style={"height": height, "width": "100%", "borderRadius": "8px"},
    )


# ─── Key Oil Infrastructure Facilities (base layer) ─────────────────────────
_OIL_FACILITIES = [
    # Iran
    {"name": "Abadan Refinery", "lat": 30.34, "lon": 48.28, "type": "refinery", "capacity_mbd": 0.4},
    {"name": "Isfahan Refinery", "lat": 32.65, "lon": 51.68, "type": "refinery", "capacity_mbd": 0.37},
    {"name": "Bandar Abbas Refinery", "lat": 27.19, "lon": 56.27, "type": "refinery", "capacity_mbd": 0.32},
    {"name": "Tehran Refinery", "lat": 35.63, "lon": 51.35, "type": "refinery", "capacity_mbd": 0.25},
    {"name": "Kharg Island Terminal", "lat": 29.23, "lon": 50.32, "type": "terminal", "capacity_mbd": 5.0},
    {"name": "Lavan Island Terminal", "lat": 26.81, "lon": 53.36, "type": "terminal", "capacity_mbd": 0.2},
    {"name": "Gachsaran Oil Field", "lat": 30.35, "lon": 50.80, "type": "field", "capacity_mbd": 0.56},
    {"name": "Ahvaz-Asmari Field", "lat": 31.32, "lon": 48.67, "type": "field", "capacity_mbd": 0.75},
    {"name": "Marun Field", "lat": 31.00, "lon": 49.50, "type": "field", "capacity_mbd": 0.52},
    {"name": "South Pars Gas Field", "lat": 26.95, "lon": 52.05, "type": "field", "capacity_mbd": 0.0},
    # Iraq
    {"name": "Basra Oil Terminal", "lat": 29.69, "lon": 48.82, "type": "terminal", "capacity_mbd": 3.5},
    {"name": "Kirkuk-Ceyhan Pipeline", "lat": 35.47, "lon": 44.39, "type": "pipeline", "capacity_mbd": 1.6},
    # Saudi Arabia
    {"name": "Ras Tanura Terminal", "lat": 26.64, "lon": 50.16, "type": "terminal", "capacity_mbd": 6.0},
    {"name": "Abqaiq Processing", "lat": 25.94, "lon": 49.68, "type": "refinery", "capacity_mbd": 7.0},
    {"name": "Yanbu Terminal", "lat": 24.09, "lon": 38.06, "type": "terminal", "capacity_mbd": 4.5},
    # UAE / Kuwait
    {"name": "Fujairah Storage Hub", "lat": 25.12, "lon": 56.33, "type": "storage", "capacity_mbd": 0.0},
    {"name": "Mina Al-Ahmadi (Kuwait)", "lat": 29.08, "lon": 48.16, "type": "terminal", "capacity_mbd": 2.5},
    # Strait of Hormuz
    {"name": "Strait of Hormuz (choke)", "lat": 26.56, "lon": 56.25, "type": "terminal", "capacity_mbd": 21.0},
    # Bab el-Mandeb
    {"name": "Bab el-Mandeb (choke)", "lat": 12.58, "lon": 43.33, "type": "terminal", "capacity_mbd": 4.8},
    # Suez Canal
    {"name": "Suez Canal (choke)", "lat": 30.46, "lon": 32.35, "type": "terminal", "capacity_mbd": 5.5},
]

_FACILITY_ICONS = {
    "refinery": "#FFD700",
    "pipeline": "#8B8000",
    "terminal": "#4FC3F7",
    "storage":  "#AB47BC",
    "field":    "#66BB6A",
}


def create_infrastructure_map(events, height="500px", facility_statuses=None):
    """
    Infrastructure damage map with:
    - Base layer: known oil facilities (colored by status if available, else dim)
    - Overlay: damage events (bright markers scaled by severity)

    Args:
        events: list of GeopoliticalEvent objects
        height: CSS height string
        facility_statuses: optional dict {facility_name: {"status": ..., "oil_offline": ..., "recovery": ...}}
    """
    layers = []

    _STATUS_MARKER_COLORS = {
        "operational": ("#66BB6A", 0.3),
        "shut_in": ("#FFD600", 0.8),
        "partial": ("#4FC3F7", 0.7),
        "damaged": ("#FF5252", 0.9),
        "destroyed": ("#888888", 0.9),
    }

    # ── Base: known oil facilities ───────────────────────────────────
    facility_markers = []
    for f in _OIL_FACILITIES:
        # Check if we have a live status for this facility
        fs = (facility_statuses or {}).get(f["name"])
        if fs:
            status = fs.get("status", "operational")
            fcolor, opacity = _STATUS_MARKER_COLORS.get(status, ("#888", 0.3))
            size = max(8, 6 + (fs.get("oil_offline", 0) or 0) * 3)
            status_text = f"Status: {status.replace('_', ' ').title()}"
            off_text = f"Oil offline: {fs.get('oil_offline', 0):.2f} mbd" if fs.get("oil_offline") else ""
            rec_text = f"Recovery: {fs.get('recovery', 'N/A')}" if fs.get("recovery") else ""
        else:
            fcolor = _FACILITY_ICONS.get(f["type"], "#888")
            opacity = 0.25
            size = 6
            status_text = "Status: Unknown"
            off_text = ""
            rec_text = ""

        cap = f"Capacity: {f['capacity_mbd']:.1f} mbd" if f["capacity_mbd"] else ""
        popup = dl.Popup(html.Div([
            html.Strong(f["name"]),
            html.Br(),
            html.Small(f"Type: {f['type'].title()}"),
            html.Br(),
            html.Small(cap) if cap else html.Span(),
            html.Br() if status_text else html.Span(),
            html.Small(status_text, style={"fontWeight": "bold"}) if fs else html.Span(),
            html.Br() if off_text else html.Span(),
            html.Small(off_text, style={"color": "#FF5252"}) if off_text else html.Span(),
            html.Br() if rec_text else html.Span(),
            html.Small(rec_text) if rec_text else html.Span(),
        ]))
        facility_markers.append(
            dl.CircleMarker(
                center=[f["lat"], f["lon"]],
                radius=size,
                color=fcolor,
                fillColor=fcolor,
                fillOpacity=opacity,
                weight=1 if not fs else 2,
                children=[popup],
            )
        )
    layers.append(dl.LayerGroup(facility_markers))

    # ── Overlay: damage events ───────────────────────────────────────
    damage_markers = []
    for e in events:
        if e.latitude and e.longitude:
            sev = e.severity or 0
            impact = e.supply_impact_mbd or 0
            if sev >= 7:
                color, fill = "#FF1744", "#FF5252"
            elif sev >= 4:
                color, fill = "#FF6D00", "#FF9100"
            else:
                color, fill = "#FFD600", "#FFFF00"

            radius = max(8, sev * 1.5 + impact * 3)

            popup = dl.Popup(html.Div([
                html.Strong((e.headline or "Damage Event")[:80]),
                html.Br(),
                html.Small(f"Severity: {sev}/10"),
                html.Br(),
                html.Small(f"Supply Impact: {impact:.2f} mbd") if impact else html.Span(),
                html.Br(),
                html.Small(e.location_name or ""),
                html.Br(),
                html.Small(
                    e.timestamp.strftime("%Y-%m-%d %H:%M") if e.timestamp else "",
                ),
            ]))

            damage_markers.append(
                dl.CircleMarker(
                    center=[e.latitude, e.longitude],
                    radius=radius,
                    color=color,
                    fillColor=fill,
                    fillOpacity=0.6,
                    weight=2,
                    children=[popup],
                )
            )

    if damage_markers:
        layers.append(dl.LayerGroup(damage_markers))

    if not facility_markers and not damage_markers:
        return html.P("No infrastructure data to display.", className="text-muted")

    center = [25.0, 48.0]
    zoom = 4

    return dl.Map(
        children=[
            dl.TileLayer(
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
                attribution='&copy; <a href="https://carto.com/">CARTO</a>',
            ),
            *layers,
        ],
        center=center,
        zoom=zoom,
        style={"height": height, "width": "100%", "borderRadius": "8px"},
    )
