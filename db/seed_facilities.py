"""
Seed the facility table with ~50 key Gulf region oil & gas facilities.
Run once: python -m db.seed_facilities
"""

from loguru import logger
from db.database import get_session, Facility, init_db

FACILITIES = [
    # ── Iran ──────────────────────────────────────────────────────────────────
    # Refineries
    {"name": "Abadan Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.40, "latitude": 30.34, "longitude": 48.28, "region": "Khuzestan",
     "owner_operator": "NIOC", "is_export_critical": True},
    {"name": "Isfahan Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.37, "latitude": 32.65, "longitude": 51.68, "region": "Isfahan",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "Bandar Abbas Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.32, "latitude": 27.19, "longitude": 56.27, "region": "Hormozgan",
     "owner_operator": "NIOC", "is_export_critical": True},
    {"name": "Tehran Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.25, "latitude": 35.63, "longitude": 51.35, "region": "Tehran",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "Tabriz Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.11, "latitude": 38.08, "longitude": 46.30, "region": "East Azerbaijan",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "Arak Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.17, "latitude": 34.09, "longitude": 49.69, "region": "Markazi",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "Lavan Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.06, "latitude": 26.81, "longitude": 53.36, "region": "Persian Gulf",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "Shiraz Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.06, "latitude": 29.62, "longitude": 52.53, "region": "Fars",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "Kermanshah Refinery", "country": "IR", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.03, "latitude": 34.31, "longitude": 47.07, "region": "Kermanshah",
     "owner_operator": "NIOC", "is_export_critical": False},
    # Fields
    {"name": "Gachsaran Oil Field", "country": "IR", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.56, "latitude": 30.35, "longitude": 50.80, "region": "Khuzestan",
     "owner_operator": "NIOC", "is_export_critical": True},
    {"name": "Ahvaz-Asmari Field", "country": "IR", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.75, "latitude": 31.32, "longitude": 48.67, "region": "Khuzestan",
     "owner_operator": "NIOC", "is_export_critical": True},
    {"name": "Marun Field", "country": "IR", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.52, "latitude": 31.00, "longitude": 49.50, "region": "Khuzestan",
     "owner_operator": "NIOC", "is_export_critical": True},
    {"name": "Agha-Jari Field", "country": "IR", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.20, "latitude": 30.75, "longitude": 49.85, "region": "Khuzestan",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "Bibi-Hakimeh Field", "country": "IR", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.13, "latitude": 30.88, "longitude": 50.28, "region": "Khuzestan",
     "owner_operator": "NIOC", "is_export_critical": False},
    {"name": "South Pars Gas Complex", "country": "IR", "facility_type": "processing", "commodity": "gas",
     "capacity_gas_bcfd": 8.5, "latitude": 26.95, "longitude": 52.05, "region": "Persian Gulf",
     "owner_operator": "NIOC", "is_export_critical": True},
    # Terminals
    {"name": "Kharg Island Terminal", "country": "IR", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 5.0, "latitude": 29.23, "longitude": 50.32, "region": "Persian Gulf",
     "owner_operator": "NIOC", "is_export_critical": True},
    {"name": "Lavan Island Terminal", "country": "IR", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 0.20, "latitude": 26.81, "longitude": 53.36, "region": "Persian Gulf",
     "owner_operator": "NIOC", "is_export_critical": True},
    {"name": "Jask Terminal", "country": "IR", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 1.0, "latitude": 25.64, "longitude": 57.77, "region": "Hormozgan",
     "owner_operator": "NIOC", "is_export_critical": True,
     "notes": "Bypasses Hormuz — Goreh-Jask pipeline"},
    {"name": "Bandar Abbas Terminal", "country": "IR", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 0.30, "latitude": 27.18, "longitude": 56.28, "region": "Hormozgan",
     "owner_operator": "NIOC", "is_export_critical": True},

    # ── Saudi Arabia ─────────────────────────────────────────────────────────
    {"name": "Ras Tanura Terminal", "country": "SA", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 6.0, "latitude": 26.64, "longitude": 50.16, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": True},
    {"name": "Abqaiq Processing", "country": "SA", "facility_type": "processing", "commodity": "oil",
     "capacity_oil_mbd": 7.0, "latitude": 25.94, "longitude": 49.68, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": True},
    {"name": "Yanbu Terminal", "country": "SA", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 4.5, "latitude": 24.09, "longitude": 38.06, "region": "Red Sea",
     "owner_operator": "Saudi Aramco", "is_export_critical": True,
     "notes": "Bypasses Hormuz — East-West Pipeline"},
    {"name": "Juaymah Terminal", "country": "SA", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 3.0, "latitude": 26.83, "longitude": 49.93, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": True},
    {"name": "Ras Al-Khair Terminal", "country": "SA", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 0.5, "latitude": 27.48, "longitude": 49.22, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": False},
    {"name": "Ghawar Field", "country": "SA", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 3.8, "latitude": 25.37, "longitude": 49.43, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": True},
    {"name": "Safaniyah Field", "country": "SA", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 1.5, "latitude": 28.15, "longitude": 49.38, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": True},
    {"name": "Khurais Field", "country": "SA", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 1.5, "latitude": 24.15, "longitude": 48.17, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": True},
    {"name": "Ras Tanura Refinery", "country": "SA", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.55, "latitude": 26.64, "longitude": 50.16, "region": "Eastern Province",
     "owner_operator": "Saudi Aramco", "is_export_critical": False},
    {"name": "Riyadh Refinery", "country": "SA", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.12, "latitude": 24.71, "longitude": 46.67, "region": "Riyadh",
     "owner_operator": "Saudi Aramco", "is_export_critical": False},

    # ── Iraq ─────────────────────────────────────────────────────────────────
    {"name": "Basra Oil Terminal", "country": "IQ", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 3.5, "latitude": 29.69, "longitude": 48.82, "region": "Basra",
     "owner_operator": "SOMO", "is_export_critical": True},
    {"name": "Rumaila Field", "country": "IQ", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 1.5, "latitude": 30.58, "longitude": 47.32, "region": "Basra",
     "owner_operator": "BP/PetroChina", "is_export_critical": True},
    {"name": "West Qurna Field", "country": "IQ", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.80, "latitude": 30.98, "longitude": 47.24, "region": "Basra",
     "owner_operator": "Lukoil", "is_export_critical": True},
    {"name": "Zubair Field", "country": "IQ", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.50, "latitude": 30.35, "longitude": 47.70, "region": "Basra",
     "owner_operator": "Eni", "is_export_critical": False},
    {"name": "Kirkuk-Ceyhan Pipeline", "country": "IQ", "facility_type": "pipeline", "commodity": "oil",
     "capacity_oil_mbd": 1.6, "latitude": 35.47, "longitude": 44.39, "region": "Kirkuk",
     "owner_operator": "SOMO", "is_export_critical": True},
    {"name": "Baiji Refinery", "country": "IQ", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.31, "latitude": 34.93, "longitude": 43.49, "region": "Saladin",
     "owner_operator": "Iraq MoO", "is_export_critical": False},

    # ── UAE ──────────────────────────────────────────────────────────────────
    {"name": "Fujairah Terminal", "country": "AE", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 2.0, "latitude": 25.12, "longitude": 56.33, "region": "Fujairah",
     "owner_operator": "ADNOC", "is_export_critical": True,
     "notes": "Bypasses Hormuz — Habshan-Fujairah pipeline"},
    {"name": "Jebel Ali Terminal", "country": "AE", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 0.50, "latitude": 25.00, "longitude": 55.06, "region": "Dubai",
     "owner_operator": "ENOC", "is_export_critical": False},
    {"name": "Das Island Terminal", "country": "AE", "facility_type": "terminal", "commodity": "both",
     "capacity_oil_mbd": 1.0, "capacity_gas_bcfd": 1.5, "latitude": 25.15, "longitude": 52.87,
     "region": "Abu Dhabi Offshore", "owner_operator": "ADNOC", "is_export_critical": True},
    {"name": "Upper Zakum Field", "country": "AE", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 1.0, "latitude": 25.30, "longitude": 53.60, "region": "Abu Dhabi Offshore",
     "owner_operator": "ADNOC", "is_export_critical": True},
    {"name": "Bu Hasa Field", "country": "AE", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.60, "latitude": 23.50, "longitude": 53.20, "region": "Abu Dhabi Onshore",
     "owner_operator": "ADNOC", "is_export_critical": False},
    {"name": "Ruwais Refinery", "country": "AE", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.84, "latitude": 24.11, "longitude": 52.73, "region": "Abu Dhabi",
     "owner_operator": "ADNOC", "is_export_critical": False},

    # ── Kuwait ───────────────────────────────────────────────────────────────
    {"name": "Mina Al-Ahmadi Terminal", "country": "KW", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 2.5, "latitude": 29.08, "longitude": 48.16, "region": "Al Ahmadi",
     "owner_operator": "KPC", "is_export_critical": True},
    {"name": "Mina Abdullah Terminal", "country": "KW", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 0.80, "latitude": 29.00, "longitude": 48.18, "region": "Al Ahmadi",
     "owner_operator": "KPC", "is_export_critical": True},
    {"name": "Burgan Field", "country": "KW", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 1.7, "latitude": 28.95, "longitude": 47.98, "region": "Al Ahmadi",
     "owner_operator": "KOC", "is_export_critical": True},

    # ── Qatar ────────────────────────────────────────────────────────────────
    {"name": "Ras Laffan LNG", "country": "QA", "facility_type": "lng_plant", "commodity": "gas",
     "capacity_gas_bcfd": 10.0, "latitude": 25.90, "longitude": 51.55, "region": "Ras Laffan",
     "owner_operator": "QatarEnergy", "is_export_critical": True},
    {"name": "North Field Gas", "country": "QA", "facility_type": "field", "commodity": "gas",
     "capacity_gas_bcfd": 16.0, "latitude": 26.50, "longitude": 51.80, "region": "Offshore",
     "owner_operator": "QatarEnergy", "is_export_critical": True},
    {"name": "Al-Shaheen Field", "country": "QA", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.30, "latitude": 26.30, "longitude": 51.35, "region": "Offshore",
     "owner_operator": "TotalEnergies/QatarEnergy", "is_export_critical": False},

    # ── Oman ─────────────────────────────────────────────────────────────────
    {"name": "Mina Al-Fahal Terminal", "country": "OM", "facility_type": "terminal", "commodity": "oil",
     "capacity_oil_mbd": 0.90, "latitude": 23.63, "longitude": 58.52, "region": "Muscat",
     "owner_operator": "PDO", "is_export_critical": True},
    {"name": "Yibal Field", "country": "OM", "facility_type": "field", "commodity": "both",
     "capacity_oil_mbd": 0.10, "capacity_gas_bcfd": 0.5, "latitude": 22.18, "longitude": 56.10,
     "region": "Interior", "owner_operator": "PDO", "is_export_critical": False},
    {"name": "Fahud Field", "country": "OM", "facility_type": "field", "commodity": "oil",
     "capacity_oil_mbd": 0.08, "latitude": 22.35, "longitude": 56.50, "region": "Interior",
     "owner_operator": "PDO", "is_export_critical": False},

    # ── Bahrain ──────────────────────────────────────────────────────────────
    {"name": "BAPCO Refinery", "country": "BH", "facility_type": "refinery", "commodity": "oil",
     "capacity_oil_mbd": 0.27, "latitude": 26.03, "longitude": 50.55, "region": "Sitra",
     "owner_operator": "BAPCO", "is_export_critical": False},
    {"name": "Awali Field", "country": "BH", "facility_type": "field", "commodity": "both",
     "capacity_oil_mbd": 0.04, "capacity_gas_bcfd": 1.5, "latitude": 26.05, "longitude": 50.52,
     "region": "Central", "owner_operator": "BAPCO", "is_export_critical": False},
]


def seed_facilities():
    """Insert facilities into DB. Skips duplicates."""
    init_db()
    session = get_session()
    added = 0
    try:
        for f in FACILITIES:
            exists = session.query(Facility).filter_by(
                name=f["name"], country=f["country"]
            ).first()
            if exists:
                continue
            session.add(Facility(**f))
            added += 1
        session.commit()
        logger.info(f"Seeded {added} facilities (skipped {len(FACILITIES) - added} duplicates).")
    except Exception as e:
        session.rollback()
        logger.error(f"Seed facilities failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_facilities()
