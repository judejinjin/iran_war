"""
Production Tracker — daily status rollup pipeline.

Computes facility_status, country_production, chokepoint_status (Hormuz, Bab el-Mandeb,
Suez), and region_supply_summary for a given date based on disruption events and
previous-day status.
"""

from datetime import date, timedelta
from loguru import logger
from sqlalchemy import func

from config import WAR_START_DATE, CHOKEPOINT_BASELINES, CHOKEPOINT_BOUNDS
from db.database import (
    get_session, Facility, FacilityStatus, CountryProduction,
    DisruptionEvent, HormuzStatus, ChokepointStatus,
    RegionSupplySummary, GeopoliticalEvent,
)

# Country baselines
_BASELINES = {
    "IR": {"oil": 3.2, "gas": 8.5},
    "SA": {"oil": 10.5, "gas": 10.0},
    "IQ": {"oil": 4.5, "gas": 3.0},
    "AE": {"oil": 3.2, "gas": 6.0},
    "KW": {"oil": 2.7, "gas": 1.8},
    "QA": {"oil": 1.8, "gas": 16.0},
    "OM": {"oil": 1.0, "gas": 4.0},
    "BH": {"oil": 0.2, "gas": 1.5},
}

GLOBAL_OIL_DEMAND_MBD = 103.0  # approximate 2026 global oil demand


def compute_daily_status(target_date: date) -> dict:
    """
    Compute full daily status snapshot for target_date.

    Steps:
    1. For each facility: determine status from active disruptions
    2. Upsert facility_status for the date
    3. Aggregate by country → upsert country_production
    4. Update hormuz_status
    5. Sum → upsert region_supply_summary

    Returns dict with summary stats.
    """
    session = get_session()
    try:
        facilities = session.query(Facility).all()
        facility_map = {f.id: f for f in facilities}

        # ── Step 1-2: Compute per-facility status ────────────────────
        for facility in facilities:
            # Get all unresolved disruptions for this facility up to target_date
            disruptions = session.query(DisruptionEvent).filter(
                DisruptionEvent.facility_id == facility.id,
                DisruptionEvent.start_date <= target_date,
                DisruptionEvent.is_resolved == False,
            ).all()

            # Check for natural recovery (shut-ins with repair estimates)
            active_disruptions = []
            for d in disruptions:
                if d.repair_estimate_days and d.event_type in ("shut_in", "precautionary_shutdown"):
                    recovery_date = d.start_date + timedelta(days=d.repair_estimate_days)
                    if target_date >= recovery_date:
                        d.is_resolved = True
                        d.end_date = recovery_date
                        continue
                active_disruptions.append(d)

            # Aggregate impacts
            total_oil_off = 0.0
            total_gas_off = 0.0
            max_damage_pct = 0.0
            worst_cause = None
            worst_status = "operational"
            max_repair_days = None
            recovery_date = None
            source_event_id = None

            status_priority = {
                "operational": 0, "shut_in": 1, "partial": 2,
                "damaged": 3, "destroyed": 4,
            }

            for d in active_disruptions:
                total_oil_off += d.oil_impact_mbd or 0
                total_gas_off += d.gas_impact_bcfd or 0
                max_damage_pct = max(max_damage_pct, d.damage_pct or 0)

                # Map event_type → status
                et_map = {
                    "shut_in": "shut_in",
                    "precautionary_shutdown": "shut_in",
                    "partial_damage": "partial",
                    "damage": "damaged",
                    "destruction": "destroyed",
                }
                this_status = et_map.get(d.event_type, "damaged")
                if status_priority.get(this_status, 0) > status_priority.get(worst_status, 0):
                    worst_status = this_status
                    worst_cause = d.cause
                    source_event_id = d.source_event_id

                if d.repair_estimate_days:
                    if max_repair_days is None or d.repair_estimate_days > max_repair_days:
                        max_repair_days = d.repair_estimate_days
                        recovery_date = d.start_date + timedelta(days=d.repair_estimate_days)

            # Cap offline at capacity
            cap_oil = facility.capacity_oil_mbd or 0
            cap_gas = facility.capacity_gas_bcfd or 0
            total_oil_off = min(total_oil_off, cap_oil)
            total_gas_off = min(total_gas_off, cap_gas)

            oil_online = max(0, cap_oil - total_oil_off)
            gas_online = max(0, cap_gas - total_gas_off)

            # Upsert facility_status
            fs = session.query(FacilityStatus).filter_by(
                facility_id=facility.id, date=target_date
            ).first()
            if fs:
                fs.status = worst_status
                fs.cause = worst_cause
                fs.oil_offline_mbd = total_oil_off
                fs.gas_offline_bcfd = total_gas_off
                fs.oil_online_mbd = oil_online
                fs.gas_online_bcfd = gas_online
                fs.damage_pct = max_damage_pct
                fs.estimated_repair_days = max_repair_days
                fs.estimated_recovery_date = recovery_date
                fs.source_event_id = source_event_id
            else:
                session.add(FacilityStatus(
                    facility_id=facility.id,
                    date=target_date,
                    status=worst_status,
                    cause=worst_cause,
                    oil_offline_mbd=total_oil_off,
                    gas_offline_bcfd=total_gas_off,
                    oil_online_mbd=oil_online,
                    gas_online_bcfd=gas_online,
                    damage_pct=max_damage_pct,
                    estimated_repair_days=max_repair_days,
                    estimated_recovery_date=recovery_date,
                    source_event_id=source_event_id,
                ))

        session.flush()

        # ── Step 3: Aggregate by country ─────────────────────────────
        country_stats = {}
        for country, baseline in _BASELINES.items():
            country_facilities = [f for f in facilities if f.country == country]
            fids = [f.id for f in country_facilities]

            statuses = session.query(FacilityStatus).filter(
                FacilityStatus.facility_id.in_(fids),
                FacilityStatus.date == target_date,
            ).all() if fids else []

            shut_in_oil = sum(
                fs.oil_offline_mbd or 0 for fs in statuses
                if fs.status == "shut_in"
            )
            shut_in_gas = sum(
                fs.gas_offline_bcfd or 0 for fs in statuses
                if fs.status == "shut_in"
            )
            damaged_oil = sum(
                fs.oil_offline_mbd or 0 for fs in statuses
                if fs.status in ("damaged", "destroyed", "partial")
            )
            damaged_gas = sum(
                fs.gas_offline_bcfd or 0 for fs in statuses
                if fs.status in ("damaged", "destroyed", "partial")
            )

            total_off_oil = shut_in_oil + damaged_oil
            total_off_gas = shut_in_gas + damaged_gas
            current_oil = max(0, baseline["oil"] - total_off_oil)
            current_gas = max(0, baseline["gas"] - total_off_gas)
            pct_oil = total_off_oil / baseline["oil"] if baseline["oil"] > 0 else 0
            pct_gas = total_off_gas / baseline["gas"] if baseline["gas"] > 0 else 0

            country_stats[country] = {
                "shut_in_oil": shut_in_oil, "shut_in_gas": shut_in_gas,
                "damaged_oil": damaged_oil, "damaged_gas": damaged_gas,
                "total_off_oil": total_off_oil, "total_off_gas": total_off_gas,
                "current_oil": current_oil, "current_gas": current_gas,
                "pct_oil": pct_oil, "pct_gas": pct_gas,
            }

            cp = session.query(CountryProduction).filter_by(
                date=target_date, country=country
            ).first()
            if cp:
                cp.baseline_oil_mbd = baseline["oil"]
                cp.baseline_gas_bcfd = baseline["gas"]
                cp.current_oil_mbd = current_oil
                cp.current_gas_bcfd = current_gas
                cp.shut_in_oil_mbd = shut_in_oil
                cp.shut_in_gas_bcfd = shut_in_gas
                cp.damaged_oil_mbd = damaged_oil
                cp.damaged_gas_bcfd = damaged_gas
                cp.total_offline_oil_mbd = total_off_oil
                cp.total_offline_gas_bcfd = total_off_gas
                cp.pct_oil_offline = pct_oil
                cp.pct_gas_offline = pct_gas
            else:
                session.add(CountryProduction(
                    date=target_date,
                    country=country,
                    baseline_oil_mbd=baseline["oil"],
                    baseline_gas_bcfd=baseline["gas"],
                    current_oil_mbd=current_oil,
                    current_gas_bcfd=current_gas,
                    shut_in_oil_mbd=shut_in_oil,
                    shut_in_gas_bcfd=shut_in_gas,
                    damaged_oil_mbd=damaged_oil,
                    damaged_gas_bcfd=damaged_gas,
                    total_offline_oil_mbd=total_off_oil,
                    total_offline_gas_bcfd=total_off_gas,
                    pct_oil_offline=pct_oil,
                    pct_gas_offline=pct_gas,
                ))

        session.flush()

        # ── Step 4: All chokepoint statuses ─────────────────────────
        update_chokepoint_statuses(session, target_date)
        # Also update legacy HormuzStatus for backward compat
        _sync_legacy_hormuz(session, target_date)

        # ── Step 5: Region supply summary ────────────────────────────
        total_baseline_oil = sum(b["oil"] for b in _BASELINES.values())
        total_baseline_gas = sum(b["gas"] for b in _BASELINES.values())
        total_shut_in = sum(cs["shut_in_oil"] for cs in country_stats.values())
        total_damaged = sum(cs["damaged_oil"] for cs in country_stats.values())
        total_current_oil = sum(cs["current_oil"] for cs in country_stats.values())
        total_current_gas = sum(cs["current_gas"] for cs in country_stats.values())

        # Hormuz chokepoint impact
        hormuz_cp = session.query(ChokepointStatus).filter_by(
            chokepoint="hormuz", date=target_date
        ).first()
        hormuz_blocked = 0.0
        if hormuz_cp and hormuz_cp.reduction_pct and hormuz_cp.reduction_pct > 0:
            hormuz_blocked = hormuz_cp.normal_oil_mbd * hormuz_cp.reduction_pct
            total_current_oil = max(0, total_current_oil - hormuz_blocked)

        # Bab el-Mandeb chokepoint impact
        bab_cp = session.query(ChokepointStatus).filter_by(
            chokepoint="bab_el_mandeb", date=target_date
        ).first()
        bab_blocked = 0.0
        if bab_cp and bab_cp.reduction_pct and bab_cp.reduction_pct > 0:
            bab_blocked = bab_cp.normal_oil_mbd * bab_cp.reduction_pct
            # Bab el-Mandeb doesn't directly subtract from Gulf production
            # but adds transit delay/cost; count as effective offline
            total_current_oil = max(0, total_current_oil - bab_blocked)

        total_off_oil = total_baseline_oil - total_current_oil
        total_off_gas = total_baseline_gas - total_current_gas
        pct_global = total_off_oil / GLOBAL_OIL_DEMAND_MBD

        rss = session.query(RegionSupplySummary).filter_by(date=target_date).first()
        if rss:
            rss.total_baseline_oil_mbd = total_baseline_oil
            rss.total_current_oil_mbd = total_current_oil
            rss.total_offline_oil_mbd = total_off_oil
            rss.total_shut_in_oil_mbd = total_shut_in
            rss.total_damaged_oil_mbd = total_damaged
            rss.total_hormuz_blocked_mbd = hormuz_blocked
            rss.total_bab_el_mandeb_blocked_mbd = bab_blocked
            rss.total_baseline_gas_bcfd = total_baseline_gas
            rss.total_current_gas_bcfd = total_current_gas
            rss.total_offline_gas_bcfd = total_off_gas
            rss.pct_global_supply_offline = pct_global
        else:
            session.add(RegionSupplySummary(
                date=target_date,
                total_baseline_oil_mbd=total_baseline_oil,
                total_current_oil_mbd=total_current_oil,
                total_offline_oil_mbd=total_off_oil,
                total_shut_in_oil_mbd=total_shut_in,
                total_damaged_oil_mbd=total_damaged,
                total_sanctions_oil_mbd=0.0,
                total_hormuz_blocked_mbd=hormuz_blocked,
                total_bab_el_mandeb_blocked_mbd=bab_blocked,
                total_baseline_gas_bcfd=total_baseline_gas,
                total_current_gas_bcfd=total_current_gas,
                total_offline_gas_bcfd=total_off_gas,
                pct_global_supply_offline=pct_global,
            ))

        session.commit()
        logger.info(
            f"Daily status for {target_date}: "
            f"oil offline={total_off_oil:.2f} mbd ({pct_global*100:.1f}% global), "
            f"shut-in={total_shut_in:.2f}, damaged={total_damaged:.2f}, "
            f"hormuz={hormuz_blocked:.2f}, bab_el_mandeb={bab_blocked:.2f}"
        )
        return {
            "date": str(target_date),
            "total_offline_oil_mbd": total_off_oil,
            "total_shut_in_oil_mbd": total_shut_in,
            "total_damaged_oil_mbd": total_damaged,
            "hormuz_blocked_mbd": hormuz_blocked,
            "bab_el_mandeb_blocked_mbd": bab_blocked,
            "pct_global": pct_global,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"compute_daily_status({target_date}) failed: {e}")
        raise
    finally:
        session.close()


def _route_event_to_chokepoint(event) -> str:
    """
    Route a shipment_disruption event to the correct chokepoint using
    lat/lon bounding boxes and keyword matching. Returns chokepoint key.
    """
    text = ((event.headline or "") + " " + (event.summary or "") + " " +
            (event.location_name or "")).lower()

    # 1. If event has coordinates, try bounding-box match
    if event.latitude and event.longitude:
        for cp_name, bounds in CHOKEPOINT_BOUNDS.items():
            if (bounds["lat_min"] <= event.latitude <= bounds["lat_max"] and
                    bounds["lon_min"] <= event.longitude <= bounds["lon_max"]):
                return cp_name

    # 2. Keyword match (check most specific first)
    for cp_name in ("bab_el_mandeb", "suez", "hormuz"):
        keywords = CHOKEPOINT_BOUNDS[cp_name]["keywords"]
        if any(kw in text for kw in keywords):
            return cp_name

    # 3. Default to hormuz (most Gulf-war events are Hormuz-related)
    return "hormuz"


def update_chokepoint_statuses(session, target_date: date):
    """
    Update all chokepoint statuses for target_date based on shipment_disruption events.
    Routes events to correct chokepoint, then computes each independently.
    """
    from datetime import datetime as _dt

    # Query all shipment_disruption events on this date
    incidents = session.query(GeopoliticalEvent).filter(
        GeopoliticalEvent.category == "shipment_disruption",
        GeopoliticalEvent.timestamp >= _dt.combine(target_date, _dt.min.time()),
        GeopoliticalEvent.timestamp <= _dt.combine(target_date, _dt.max.time()),
    ).all()

    # Route events to chokepoints
    routed = {cp: [] for cp in CHOKEPOINT_BASELINES}
    for evt in incidents:
        cp = _route_event_to_chokepoint(evt)
        routed[cp].append(evt)

    # Update each chokepoint
    for cp_name, cp_config in CHOKEPOINT_BASELINES.items():
        cp_events = routed.get(cp_name, [])
        n_incidents = len(cp_events)
        avg_severity = (
            sum(e.severity or 0 for e in cp_events) / n_incidents
            if n_incidents else 0
        )

        # Previous day's status for rollforward
        prev = session.query(ChokepointStatus).filter_by(
            chokepoint=cp_name,
            date=target_date - timedelta(days=1),
        ).first()

        # Estimate reduction based on incidents
        if avg_severity >= 8:
            status = "partial_blockade"
            reduction = min(0.5, (prev.reduction_pct if prev else 0) + 0.1 * n_incidents)
        elif avg_severity >= 5:
            status = "restricted"
            reduction = min(0.3, (prev.reduction_pct if prev else 0) + 0.05 * n_incidents)
        elif n_incidents > 0:
            status = "restricted"
            reduction = max(0, (prev.reduction_pct if prev else 0))
        else:
            prev_reduction = prev.reduction_pct if prev else 0
            reduction = max(0, prev_reduction - 0.02)
            status = "open" if reduction < 0.01 else "restricted"

        normal_oil = cp_config["normal_oil_mbd"]
        normal_lng = cp_config["normal_lng_bcfd"]
        oil_transit = normal_oil * (1 - reduction)
        lng_transit = normal_lng * (1 - reduction)

        # Cape diversion logic for Bab el-Mandeb
        cape_active = (cp_name == "bab_el_mandeb" and
                       status in ("partial_blockade", "full_blockade"))
        delay_days = 12 if cape_active else 0
        freight_cost = 2.50 if cape_active else 0.0

        cs = session.query(ChokepointStatus).filter_by(
            chokepoint=cp_name, date=target_date
        ).first()
        if cs:
            cs.status = status
            cs.oil_transit_mbd = oil_transit
            cs.lng_transit_bcfd = lng_transit
            cs.normal_oil_mbd = normal_oil
            cs.normal_lng_bcfd = normal_lng
            cs.reduction_pct = reduction
            cs.naval_incidents = n_incidents
            cs.cape_diversion_active = cape_active
            cs.effective_delay_days = delay_days
            cs.extra_freight_cost_per_bbl = freight_cost
        else:
            session.add(ChokepointStatus(
                chokepoint=cp_name,
                date=target_date,
                status=status,
                oil_transit_mbd=oil_transit,
                lng_transit_bcfd=lng_transit,
                normal_oil_mbd=normal_oil,
                normal_lng_bcfd=normal_lng,
                reduction_pct=reduction,
                naval_incidents=n_incidents,
                cape_diversion_active=cape_active,
                effective_delay_days=delay_days,
                extra_freight_cost_per_bbl=freight_cost,
            ))

    session.flush()


def _sync_legacy_hormuz(session, target_date: date):
    """Keep legacy hormuz_status table in sync for backward compatibility."""
    cp = session.query(ChokepointStatus).filter_by(
        chokepoint="hormuz", date=target_date
    ).first()
    if not cp:
        return

    hs = session.query(HormuzStatus).filter_by(date=target_date).first()
    if hs:
        hs.status = cp.status
        hs.oil_transit_mbd = cp.oil_transit_mbd
        hs.lng_transit_bcfd = cp.lng_transit_bcfd
        hs.reduction_pct = cp.reduction_pct
        hs.naval_incidents = cp.naval_incidents
    else:
        session.add(HormuzStatus(
            date=target_date,
            status=cp.status,
            oil_transit_mbd=cp.oil_transit_mbd,
            lng_transit_bcfd=cp.lng_transit_bcfd,
            normal_oil_mbd=cp.normal_oil_mbd,
            reduction_pct=cp.reduction_pct,
            naval_incidents=cp.naval_incidents,
        ))
    session.flush()


def update_hormuz_status(session, target_date: date):
    """Legacy wrapper — delegates to multi-chokepoint system."""
    update_chokepoint_statuses(session, target_date)
    _sync_legacy_hormuz(session, target_date)


def compute_range(start_date: date, end_date: date) -> int:
    """Compute daily status for a date range. Returns number of days processed."""
    d = start_date
    count = 0
    while d <= end_date:
        compute_daily_status(d)
        d += timedelta(days=1)
        count += 1
    return count
