"""
Seed baseline production data for all Gulf countries on WAR_START_DATE - 1.
Also seeds initial Hormuz and Bab el-Mandeb chokepoint status rows.
Run once: python -m db.seed_baselines
"""

from datetime import date, timedelta
from loguru import logger

from config import WAR_START_DATE, CHOKEPOINT_BASELINES
from db.database import (
    get_session, init_db, CountryProduction, HormuzStatus,
    ChokepointStatus, RegionSupplySummary,
)

# Pre-war baseline capacities (2026 estimates)
COUNTRY_BASELINES = [
    {"country": "IR", "baseline_oil_mbd": 3.2, "baseline_gas_bcfd": 8.5},
    {"country": "SA", "baseline_oil_mbd": 10.5, "baseline_gas_bcfd": 10.0},
    {"country": "IQ", "baseline_oil_mbd": 4.5, "baseline_gas_bcfd": 3.0},
    {"country": "AE", "baseline_oil_mbd": 3.2, "baseline_gas_bcfd": 6.0},
    {"country": "KW", "baseline_oil_mbd": 2.7, "baseline_gas_bcfd": 1.8},
    {"country": "QA", "baseline_oil_mbd": 1.8, "baseline_gas_bcfd": 16.0},
    {"country": "OM", "baseline_oil_mbd": 1.0, "baseline_gas_bcfd": 4.0},
    {"country": "BH", "baseline_oil_mbd": 0.2, "baseline_gas_bcfd": 1.5},
]

COUNTRY_NAMES = {
    "IR": "Iran", "SA": "Saudi Arabia", "IQ": "Iraq", "AE": "UAE",
    "KW": "Kuwait", "QA": "Qatar", "OM": "Oman", "BH": "Bahrain",
}


def seed_baselines():
    """Seed pre-war country production and Hormuz status."""
    init_db()
    session = get_session()

    war_start = date.fromisoformat(WAR_START_DATE)
    baseline_date = war_start - timedelta(days=1)  # Day before war

    added = 0
    try:
        # ── Country production baselines ─────────────────────────────
        for cb in COUNTRY_BASELINES:
            exists = session.query(CountryProduction).filter_by(
                date=baseline_date, country=cb["country"]
            ).first()
            if exists:
                continue
            session.add(CountryProduction(
                date=baseline_date,
                country=cb["country"],
                baseline_oil_mbd=cb["baseline_oil_mbd"],
                baseline_gas_bcfd=cb["baseline_gas_bcfd"],
                current_oil_mbd=cb["baseline_oil_mbd"],
                current_gas_bcfd=cb["baseline_gas_bcfd"],
                shut_in_oil_mbd=0.0,
                shut_in_gas_bcfd=0.0,
                damaged_oil_mbd=0.0,
                damaged_gas_bcfd=0.0,
                sanctions_oil_mbd=0.0,
                total_offline_oil_mbd=0.0,
                total_offline_gas_bcfd=0.0,
                pct_oil_offline=0.0,
                pct_gas_offline=0.0,
                summary_text=f"{COUNTRY_NAMES[cb['country']]}: All facilities operational at baseline capacity.",
            ))
            added += 1

        # ── Hormuz baseline ──────────────────────────────────────────
        exists = session.query(HormuzStatus).filter_by(date=baseline_date).first()
        if not exists:
            session.add(HormuzStatus(
                date=baseline_date,
                status="open",
                oil_transit_mbd=21.0,
                lng_transit_bcfd=16.0,
                normal_oil_mbd=21.0,
                reduction_pct=0.0,
                insurance_war_risk_pct=0.05,
                tanker_diversions=0,
                naval_incidents=0,
                summary_text="Strait of Hormuz operating normally. Standard transit volumes.",
            ))
            added += 1

        # ── Chokepoint baselines (all three) ─────────────────────────
        for cp_key, cp_cfg in CHOKEPOINT_BASELINES.items():
            exists = session.query(ChokepointStatus).filter_by(
                chokepoint=cp_key, date=baseline_date
            ).first()
            if not exists:
                session.add(ChokepointStatus(
                    chokepoint=cp_key,
                    date=baseline_date,
                    status="open",
                    oil_transit_mbd=cp_cfg["normal_oil_mbd"],
                    lng_transit_bcfd=cp_cfg["normal_lng_bcfd"],
                    normal_oil_mbd=cp_cfg["normal_oil_mbd"],
                    normal_lng_bcfd=cp_cfg["normal_lng_bcfd"],
                    reduction_pct=0.0,
                    naval_incidents=0,
                    cape_diversion_active=False,
                    effective_delay_days=0,
                    extra_freight_cost_per_bbl=0.0,
                    summary_text=f"{cp_cfg['label']} operating normally.",
                ))
                added += 1

        # ── Region supply summary baseline ───────────────────────────
        total_oil = sum(c["baseline_oil_mbd"] for c in COUNTRY_BASELINES)
        total_gas = sum(c["baseline_gas_bcfd"] for c in COUNTRY_BASELINES)
        exists = session.query(RegionSupplySummary).filter_by(date=baseline_date).first()
        if not exists:
            session.add(RegionSupplySummary(
                date=baseline_date,
                total_baseline_oil_mbd=total_oil,
                total_current_oil_mbd=total_oil,
                total_offline_oil_mbd=0.0,
                total_shut_in_oil_mbd=0.0,
                total_damaged_oil_mbd=0.0,
                total_sanctions_oil_mbd=0.0,
                total_hormuz_blocked_mbd=0.0,
                total_bab_el_mandeb_blocked_mbd=0.0,
                total_baseline_gas_bcfd=total_gas,
                total_current_gas_bcfd=total_gas,
                total_offline_gas_bcfd=0.0,
                pct_global_supply_offline=0.0,
                ai_narrative="Pre-war baseline: All Gulf region production at full capacity. "
                             f"Total oil: {total_oil:.1f} mbd, Total gas: {total_gas:.1f} bcf/d.",
            ))
            added += 1

        session.commit()
        logger.info(f"Seeded {added} baseline rows for {baseline_date}.")
    except Exception as e:
        session.rollback()
        logger.error(f"Seed baselines failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_baselines()
