"""
Database engine, session management, and ORM models.

Uses SQLite with WAL journal mode for concurrent read/write.
"""

import json
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import (
    create_engine, event, Column, Integer, Float, Text, Date,
    DateTime, Boolean, UniqueConstraint, CheckConstraint, ForeignKey,
)
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DB_PATH, DB_URL

Base = declarative_base()


# ─── ORM Models ──────────────────────────────────────────────────────────────

class GeopoliticalEvent(Base):
    __tablename__ = "geopolitical_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    category = Column(Text, nullable=False)
    headline = Column(Text, nullable=False)
    summary = Column(Text)
    source_url = Column(Text)
    severity = Column(Integer)
    supply_impact_mbd = Column(Float)
    latitude = Column(Float)
    longitude = Column(Float)
    location_name = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    category = Column(Text, nullable=False)
    summary_text = Column(Text, nullable=False)
    severity_avg = Column(Float)
    total_supply_impact_mbd = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "category"),)


class MilitaryEvent(Base):
    __tablename__ = "military_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    side = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    loss_type = Column(Text)
    quantity = Column(Integer)
    unit_name = Column(Text)
    equipment_detail = Column(Text)
    headline = Column(Text)
    summary = Column(Text)
    source_url = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)
    location_name = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class MilitaryDeployment(Base):
    __tablename__ = "military_deployments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    side = Column(Text, nullable=False)
    deployment_status = Column(Text, nullable=False)
    force_type = Column(Text, nullable=False)
    unit_name = Column(Text)
    personnel_count = Column(Integer)
    equipment_summary = Column(Text)
    region = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)
    location_name = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "side", "unit_name"),)


class MilitaryDailySummary(Base):
    __tablename__ = "military_daily_summary"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    side = Column(Text, nullable=False)
    total_personnel_losses = Column(Integer, default=0)
    total_aircraft_losses = Column(Integer, default=0)
    total_naval_losses = Column(Integer, default=0)
    total_armor_losses = Column(Integer, default=0)
    total_missile_losses = Column(Integer, default=0)
    total_drone_losses = Column(Integer, default=0)
    cumulative_personnel_losses = Column(Integer, default=0)
    cumulative_aircraft_losses = Column(Integer, default=0)
    cumulative_naval_losses = Column(Integer, default=0)
    active_personnel_deployed = Column(Integer)
    pending_personnel_deployment = Column(Integer)
    summary_text = Column(Text)
    escalation_score = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "side"),)


class FuturesCurve(Base):
    __tablename__ = "futures_curves"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    symbol = Column(Text, nullable=False)
    contract_month = Column(Text, nullable=False)
    expiry_date = Column(Date)
    settlement_price = Column(Float)
    volume = Column(Integer)
    open_interest = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "symbol", "contract_month"),)


class Spread(Base):
    __tablename__ = "spreads"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    spread_type = Column(Text, nullable=False)
    front_month = Column(Text)
    back_month = Column(Text)
    spread_value = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "spread_type", "front_month"),)


class OptionsChain(Base):
    __tablename__ = "options_chains"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    underlying = Column(Text, nullable=False)
    expiry_date = Column(Date, nullable=False)
    strike = Column(Float, nullable=False)
    option_type = Column(Text, nullable=False)
    bid = Column(Float)
    ask = Column(Float)
    last_price = Column(Float)
    implied_vol = Column(Float)
    delta = Column(Float)
    gamma = Column(Float)
    vega = Column(Float)
    theta = Column(Float)
    volume = Column(Integer)
    open_interest = Column(Integer)
    underlying_contract_month = Column(Text)  # e.g. "2026-06" — the futures month this option settles into
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "underlying", "expiry_date", "strike", "option_type"),)


class VolSurface(Base):
    __tablename__ = "vol_surface"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    underlying = Column(Text, nullable=False)
    expiry_date = Column(Date, nullable=False)
    atm_vol = Column(Float)
    skew_25d = Column(Float)
    smile_25d = Column(Float)
    vol_of_vol = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "underlying", "expiry_date"),)


class ScenarioProbability(Base):
    __tablename__ = "scenario_probabilities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    scenario_name = Column(Text, nullable=False)
    probability = Column(Float, nullable=False)
    brent_low = Column(Float)
    brent_high = Column(Float)
    reasoning = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "scenario_name"),)


class AgentAnalysis(Base):
    __tablename__ = "agent_analyses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    analysis_type = Column(Text, nullable=False)
    underlying = Column(Text)
    summary = Column(Text, nullable=False)
    detailed_analysis = Column(Text)
    recommended_trades = Column(Text)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    underlying = Column(Text, nullable=False)
    instrument_type = Column(Text, nullable=False)
    contract_month = Column(Text, nullable=False)
    strike = Column(Float)
    option_type = Column(Text)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    entry_date = Column(Date, nullable=False)
    is_open = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class PnlProjection(Base):
    __tablename__ = "pnl_projections"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"))
    scenario_name = Column(Text, nullable=False)
    projected_underlying_price = Column(Float)
    projected_option_price = Column(Float)
    projected_pnl = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class BackfillStatus(Base):
    __tablename__ = "backfill_status"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(Text, nullable=False, unique=True)
    war_start_date = Column(Date, nullable=False)
    last_backfilled_date = Column(Date)
    status = Column(Text, nullable=False, default="pending")
    total_records = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow)


# ─── Infrastructure Production Tracking Models ──────────────────────────────

class Facility(Base):
    __tablename__ = "facility"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    country = Column(Text, nullable=False)
    facility_type = Column(Text, nullable=False)
    commodity = Column(Text, nullable=False, default="oil")
    capacity_oil_mbd = Column(Float, default=0.0)
    capacity_gas_bcfd = Column(Float, default=0.0)
    latitude = Column(Float)
    longitude = Column(Float)
    region = Column(Text)
    owner_operator = Column(Text)
    is_export_critical = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("name", "country"),)


class FacilityStatus(Base):
    __tablename__ = "facility_status"
    id = Column(Integer, primary_key=True, autoincrement=True)
    facility_id = Column(Integer, ForeignKey("facility.id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(Text, nullable=False)
    cause = Column(Text)
    oil_offline_mbd = Column(Float, default=0.0)
    gas_offline_bcfd = Column(Float, default=0.0)
    oil_online_mbd = Column(Float, default=0.0)
    gas_online_bcfd = Column(Float, default=0.0)
    damage_pct = Column(Float, default=0.0)
    estimated_repair_days = Column(Integer)
    estimated_recovery_date = Column(Date)
    confidence = Column(Text, default="estimated")
    source_event_id = Column(Integer, ForeignKey("geopolitical_events.id"))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("facility_id", "date"),)


class CountryProduction(Base):
    __tablename__ = "country_production"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    country = Column(Text, nullable=False)
    baseline_oil_mbd = Column(Float, nullable=False)
    baseline_gas_bcfd = Column(Float, nullable=False)
    current_oil_mbd = Column(Float, nullable=False)
    current_gas_bcfd = Column(Float, nullable=False)
    shut_in_oil_mbd = Column(Float, default=0.0)
    shut_in_gas_bcfd = Column(Float, default=0.0)
    damaged_oil_mbd = Column(Float, default=0.0)
    damaged_gas_bcfd = Column(Float, default=0.0)
    sanctions_oil_mbd = Column(Float, default=0.0)
    total_offline_oil_mbd = Column(Float, default=0.0)
    total_offline_gas_bcfd = Column(Float, default=0.0)
    pct_oil_offline = Column(Float, default=0.0)
    pct_gas_offline = Column(Float, default=0.0)
    summary_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "country"),)


class DisruptionEvent(Base):
    __tablename__ = "disruption_event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    facility_id = Column(Integer, ForeignKey("facility.id"), nullable=False)
    event_type = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    is_resolved = Column(Boolean, default=False)
    cause = Column(Text, nullable=False)
    oil_impact_mbd = Column(Float, default=0.0)
    gas_impact_bcfd = Column(Float, default=0.0)
    damage_pct = Column(Float, default=0.0)
    repair_estimate_days = Column(Integer)
    repair_cost_estimate_m = Column(Float)
    source_event_id = Column(Integer, ForeignKey("geopolitical_events.id"))
    headline = Column(Text)
    summary = Column(Text)
    confidence = Column(Text, default="estimated")
    created_at = Column(DateTime, default=datetime.utcnow)


class PhysicalPrice(Base):
    """Daily (FRED/EIA) and monthly (IMF) Dated Brent physical spot prices, multi-source."""
    __tablename__ = "physical_prices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    symbol = Column(Text, nullable=False)              # e.g. "DATED_BRENT"
    price = Column(Float, nullable=False)
    source = Column(Text, nullable=False)              # "FRED" | "EIA" | "IMF"
    freq = Column(Text, nullable=False, default="daily")  # "daily" | "monthly"
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "symbol", "source"),)


class HormuzStatus(Base):
    __tablename__ = "hormuz_status"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    status = Column(Text, nullable=False)
    oil_transit_mbd = Column(Float)
    lng_transit_bcfd = Column(Float)
    normal_oil_mbd = Column(Float, default=21.0)
    reduction_pct = Column(Float, default=0.0)
    insurance_war_risk_pct = Column(Float)
    tanker_diversions = Column(Integer, default=0)
    naval_incidents = Column(Integer, default=0)
    summary_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChokepointStatus(Base):
    __tablename__ = "chokepoint_status"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chokepoint = Column(Text, nullable=False)          # "hormuz" | "bab_el_mandeb" | "suez"
    date = Column(Date, nullable=False)
    status = Column(Text, nullable=False)              # open | restricted | partial_blockade | full_blockade
    oil_transit_mbd = Column(Float)
    lng_transit_bcfd = Column(Float)
    normal_oil_mbd = Column(Float)
    normal_lng_bcfd = Column(Float)
    reduction_pct = Column(Float, default=0.0)
    insurance_war_risk_pct = Column(Float)
    tanker_diversions = Column(Integer, default=0)
    naval_incidents = Column(Integer, default=0)
    cape_diversion_active = Column(Boolean, default=False)
    effective_delay_days = Column(Integer, default=0)
    extra_freight_cost_per_bbl = Column(Float, default=0.0)
    summary_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("chokepoint", "date"),)


class RegionSupplySummary(Base):
    __tablename__ = "region_supply_summary"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    total_baseline_oil_mbd = Column(Float, nullable=False)
    total_current_oil_mbd = Column(Float, nullable=False)
    total_offline_oil_mbd = Column(Float, nullable=False)
    total_shut_in_oil_mbd = Column(Float, default=0.0)
    total_damaged_oil_mbd = Column(Float, default=0.0)
    total_sanctions_oil_mbd = Column(Float, default=0.0)
    total_hormuz_blocked_mbd = Column(Float, default=0.0)
    total_bab_el_mandeb_blocked_mbd = Column(Float, default=0.0)
    total_baseline_gas_bcfd = Column(Float, nullable=False)
    total_current_gas_bcfd = Column(Float, nullable=False)
    total_offline_gas_bcfd = Column(Float, nullable=False)
    pct_global_supply_offline = Column(Float, default=0.0)
    brent_price = Column(Float)
    wti_price = Column(Float)
    ai_narrative = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Engine & Session ────────────────────────────────────────────────────────

_engine = None
_SessionLocal = None


def _set_wal_mode(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_engine():
    global _engine
    if _engine is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            DB_URL,
            connect_args={"timeout": 30},
            echo=False,
        )
        event.listen(_engine, "connect", _set_wal_mode)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db():
    """Create all tables if they don't exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)


# ─── Position CRUD helpers ───────────────────────────────────────────────────

def add_position(underlying, instrument_type, contract_month, quantity,
                 entry_price, entry_date, strike=None, option_type=None, notes=None):
    session = get_session()
    pos = Position(
        underlying=underlying,
        instrument_type=instrument_type,
        contract_month=contract_month,
        strike=strike,
        option_type=option_type,
        quantity=quantity,
        entry_price=entry_price,
        entry_date=entry_date,
        notes=notes,
    )
    session.add(pos)
    session.commit()
    pid = pos.id
    session.close()
    return pid


def update_position(position_id, **kwargs):
    session = get_session()
    pos = session.query(Position).get(position_id)
    if pos is None:
        session.close()
        return False
    for k, v in kwargs.items():
        if hasattr(pos, k):
            setattr(pos, k, v)
    session.commit()
    session.close()
    return True


def close_position(position_id):
    return update_position(position_id, is_open=False)


def delete_position(position_id):
    session = get_session()
    pos = session.query(Position).get(position_id)
    if pos is None:
        session.close()
        return False
    session.delete(pos)
    session.commit()
    session.close()
    return True


def get_open_positions():
    session = get_session()
    positions = session.query(Position).filter(Position.is_open == True).all()
    session.close()
    return positions
