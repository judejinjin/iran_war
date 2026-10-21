"""
Oil Super Spike Analyzer — Central Configuration

All configurable constants: DB path, IB connection, API URLs, schedule times,
war parameters, search keywords, scenario definitions, category lists.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "oil_data.db"
DB_URL = f"sqlite:///{DB_PATH}"
LOG_DIR = BASE_DIR / "logs"

# ─── War Parameters ──────────────────────────────────────────────────────────
WAR_START_DATE = "2026-01-01"

# ─── IB TWS ──────────────────────────────────────────────────────────────────
TWS_HOST = os.environ.get("TWS_HOST", "127.0.0.1")
TWS_PORT = int(os.environ.get("TWS_PORT", "7496"))
TWS_CLIENT_ID = int(os.environ.get("TWS_CLIENT_ID", "1"))

# ─── API Keys ────────────────────────────────────────────────────────────────
EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
CLAUDE_KEY = os.environ.get("CLAUDE_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
BING_NEWS_KEY = os.environ.get("BING_NEWS_KEY", "")
EVENT_REGISTRY_KEY = os.environ.get("EVENT_REGISTRY_KEY", "")

# ─── LLM Backend ─────────────────────────────────────────────────────────────
# "copilot_sdk" (default) | "anthropic"
LLM_BACKEND = os.environ.get("LLM_BACKEND", "copilot_sdk")

# ─── LLM — Anthropic (used when LLM_BACKEND=anthropic) ──────────────────────
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 4096

# ─── LLM — Copilot SDK (used when LLM_BACKEND=copilot_sdk) ─────────────────
COPILOT_MODEL = os.environ.get("COPILOT_MODEL", "claude-sonnet-4.5")
COPILOT_MAX_TOKENS = int(os.environ.get("COPILOT_MAX_TOKENS", "4096"))

# ─── Futures Contracts ───────────────────────────────────────────────────────
FUTURES_SYMBOLS = ["CL", "COIL"]
FUTURES_EXCHANGE = {"CL": "NYMEX", "COIL": "IPE"}
FUTURES_MONTHS_AHEAD = 24          # Front 24 months for term structure
OPTIONS_EXPIRIES_AHEAD = 12        # Front 12 expiries for options chains

# ─── FRED Series ─────────────────────────────────────────────────────────────
FRED_WTI_SERIES = "DCOILWTICO"
FRED_BRENT_SERIES = "DCOILBRENTEU"
FRED_DUBAI_SERIES = "POILDUBUSDM"   # IMF monthly Dubai crude (1992+)

# Crack spread product series (FRED)
FRED_ULSD_SERIES = os.getenv("FRED_ULSD_SERIES", "DHOILNYH")        # NY Harbor No.2 Heating Oil (ULSD proxy), daily 1986+
FRED_RBOB_SERIES = os.getenv("FRED_RBOB_SERIES", "WRBWHOLESALE")    # EIA weekly wholesale/rack RBOB gasoline

# ─── EIA Series ──────────────────────────────────────────────────────────────
EIA_CRUDE_INVENTORY = "PET.WCESTUS1.W"
EIA_US_PRODUCTION = "PET.WCRFPUS2.W"
EIA_BRENT_SERIES = "RBRTE"    # Europe Brent Spot FOB (EIA v2 series ID)
EIA_SPR_SERIES        = "WCSSTUS1"          # US Strategic Petroleum Reserve, weekly (EIA API v2)
EIA_COMMERCIAL_SERIES = "WCESTUS1"          # US commercial crude stocks, weekly (EIA API v2)
EIA_CUSHING_SERIES    = "W_EPC0_SAX_YCUOK_MBBL"  # Cushing OK crude stocks excl SPR, weekly (EIA API v2)

# ─── SPR / JODI ──────────────────────────────────────────────────────────────
JODI_API_BASE = "https://www.jodidata.org/api/data/"
# US crude demand used for days-of-cover computation (kbd)
US_CRUDE_DEMAND_KBD = 19_500.0

SPR_COUNTRIES = {
    "US":   "United States",
    "CN":   "China",
    "JP":   "Japan",
    "DE":   "Germany",
    "FR":   "France",
    "IT":   "Italy",
    "KR":   "South Korea",
}

# IEA collective action agreed 11 March 2026 — largest ever emergency release
# Source: https://www.iea.org/news/iea-confirms-member-country-contributions-to-collective-action-...
IEA_COLLECTIVE_ACTION = {
    "agreed_date":   "2026-03-11",   # date the release officially began
    "release_days":  180,            # assumed release period (IEA convention)
    # Per-country total committed volumes in million barrels (Mbbl)
    "commitments_mbbl": {
        "US": 172.2,
        "JP":  79.8,
        "DE":  19.5,
        "FR":  14.6,
        "IT":  10.0,
        "KR":  22.5,
    },
}

# ─── Supply / Demand ─────────────────────────────────────────────────────────
# Supply (production) — EIA activityId=1, monthly frequency
SD_SUPPLY_PRODUCTS = {
    "total":    {"label": "Total Petroleum",   "eia_product_id": "53"},  # incl. NGPL + other liquids
    "crude":    {"label": "Crude Oil",         "eia_product_id": "57"},  # crude incl. lease condensate
    "ngpl":     {"label": "NGL",               "eia_product_id": "58"},
}

# Demand (consumption) — EIA activityId=2, annual frequency, unit=TBPD
SD_DEMAND_PRODUCTS = {
    "total":    {"label": "Total Petroleum",   "eia_product_id": "5"},   # petroleum & other liquids
    "gasoline": {"label": "Gasoline",          "eia_product_id": "62"},
    "jet_fuel": {"label": "Jet Fuel",          "eia_product_id": "63"},
    "diesel":   {"label": "Diesel / Distillate","eia_product_id": "65"},
    "residual": {"label": "Residual Fuel",     "eia_product_id": "66"},
    "lpg":      {"label": "LPG",               "eia_product_id": "67"},
}

# Combined UI product list (union; UI selects flow first, then filters products)
SD_PRODUCTS = {
    "total":    {"label": "Total Petroleum"},
    "crude":    {"label": "Crude Oil (supply only)"},
    "ngpl":     {"label": "NGL (supply only)"},
    "gasoline": {"label": "Gasoline (demand only)"},
    "jet_fuel": {"label": "Jet Fuel (demand only)"},
    "diesel":   {"label": "Diesel / Distillate (demand only)"},
    "residual": {"label": "Residual Fuel (demand only)"},
    "lpg":      {"label": "LPG (demand only)"},
}

SD_COUNTRIES = {
    # Major producers
    "SA": "Saudi Arabia", "RU": "Russia",    "US": "United States",
    "IQ": "Iraq",         "AE": "UAE",       "IR": "Iran",
    "KW": "Kuwait",       "NG": "Nigeria",   "LY": "Libya",
    "VE": "Venezuela",    "CN": "China",     "BR": "Brazil",
    "CA": "Canada",       "MX": "Mexico",    "NO": "Norway",
    # Additional major consumers
    "IN": "India",  "JP": "Japan",  "DE": "Germany",
    "KR": "S. Korea", "FR": "France", "GB": "UK",
    "IT": "Italy",  "ES": "Spain",  "SG": "Singapore", "AU": "Australia",
}

SD_DEFAULT_COUNTRIES = ["US", "SA", "RU", "CN", "IN"]

# EIA international country-code map (EIA 3-letter → our ISO-2)
SD_EIA_COUNTRY_MAP = {
    "SAU": "SA", "RUS": "RU", "USA": "US", "IRQ": "IQ", "ARE": "AE",
    "IRN": "IR", "KWT": "KW", "NGA": "NG", "LBY": "LY", "VEN": "VE",
    "CHN": "CN", "BRA": "BR", "CAN": "CA", "MEX": "MX", "NOR": "NO",
    "IND": "IN", "JPN": "JP", "DEU": "DE", "KOR": "KR", "FRA": "FR",
    "GBR": "GB", "ITA": "IT", "ESP": "ES", "SGP": "SG", "AUS": "AU",
}

# ─── News Search Keywords ────────────────────────────────────────────────────
NEWS_KEYWORDS = [
    "Iran war", "Iran strike", "Hormuz strait", "oil infrastructure",
    "IRGC", "oil tanker attack", "refinery strike", "pipeline damage",
    "production shut-in", "oil embargo", "OPEC emergency",
    "Iran military", "Persian Gulf", "Kharg Island",
    "Iran oil production", "Hormuz closure", "Iran sanctions",
    # Red Sea / Bab el-Mandeb / Houthi
    "Bab el-Mandeb", "Red Sea attack", "Houthi ship", "Houthi tanker",
    "Ansar Allah", "Yemen naval", "Red Sea shipping", "Gulf of Aden",
    "Suez Canal disruption", "Red Sea insurance", "Cape of Good Hope diversion",
    "Red Sea military", "Houthi drone ship", "Houthi missile ship",
]

NEWS_QUERY_STRING = " OR ".join(f'"{kw}"' for kw in NEWS_KEYWORDS[:8])

# ─── RSS Feed URLs ───────────────────────────────────────────────────────────
RSS_FEEDS = {
    "google_news": "https://news.google.com/rss/search?q=Iran+war+oil+Hormuz&hl=en-US&gl=US&ceid=US:en",
    "google_red_sea": "https://news.google.com/rss/search?q=Houthi+Red+Sea+Bab+el-Mandeb+tanker&hl=en-US&gl=US&ceid=US:en",
    "reuters_world": "https://www.rss.reuters.com/rssFeed/worldNews",
    "reuters_commodities": "https://www.rss.reuters.com/rssFeed/commoditiesNews",
    "oilprice": "https://oilprice.com/rss/main",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
}

# ─── GDELT API ───────────────────────────────────────────────────────────────
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = "Iran war OR Hormuz OR oil infrastructure OR IRGC OR Houthi OR Bab el-Mandeb OR Red Sea tanker"
GDELT_RATE_LIMIT_SECONDS = 15

# ─── Chokepoint Definitions ──────────────────────────────────────────────────
CHOKEPOINT_BASELINES = {
    "hormuz": {"normal_oil_mbd": 21.0, "normal_lng_bcfd": 16.0, "label": "Strait of Hormuz"},
    "bab_el_mandeb": {"normal_oil_mbd": 4.8, "normal_lng_bcfd": 0.4, "label": "Bab el-Mandeb"},
    "suez": {"normal_oil_mbd": 5.5, "normal_lng_bcfd": 2.0, "label": "Suez Canal"},
}

CHOKEPOINT_BOUNDS = {
    "hormuz": {
        "lat_min": 24.0, "lat_max": 27.5,
        "lon_min": 54.0, "lon_max": 58.0,
        "keywords": [
            "hormuz", "strait of hormuz", "persian gulf", "oman coast",
            "irgc naval", "iranian navy", "tanker seized", "persian gulf tanker",
        ],
    },
    "bab_el_mandeb": {
        "lat_min": 11.5, "lat_max": 15.0,
        "lon_min": 42.0, "lon_max": 45.0,
        "keywords": [
            "bab el-mandeb", "bab al-mandab", "red sea", "houthi",
            "ansar allah", "yemen", "gulf of aden", "aden gulf",
            "mocha", "djibouti strait", "red sea tanker", "red sea ship",
        ],
    },
    "suez": {
        "lat_min": 29.5, "lat_max": 31.5,
        "lon_min": 32.0, "lon_max": 33.0,
        "keywords": [
            "suez canal", "suez blockade", "port said", "ismailia",
        ],
    },
}

# ─── Event Categories ────────────────────────────────────────────────────────
EVENT_CATEGORIES = [
    "geopolitical_development",
    "military_operations",
    "infrastructure_damage",
    "production_shutin",
    "shipment_disruption",
]

# ─── Scenario Definitions ────────────────────────────────────────────────────
SCENARIOS = [
    {
        "name": "Super Spike",
        "brent_low": 180,
        "brent_high": 250,
        "description": "Hormuz closed, multi-country production offline, SPR depleted",
    },
    {
        "name": "Major Disruption",
        "brent_low": 130,
        "brent_high": 180,
        "description": "Significant Iranian production offline + partial Hormuz restriction",
    },
    {
        "name": "Moderate Escalation",
        "brent_low": 100,
        "brent_high": 130,
        "description": "Limited strikes, some production loss, Hormuz open but risky",
    },
    {
        "name": "Current State",
        "brent_low": 80,
        "brent_high": 100,
        "description": "Contained conflict, minimal supply impact",
    },
    {
        "name": "De-escalation",
        "brent_low": 65,
        "brent_high": 80,
        "description": "Ceasefire/negotiations, sanctions relief potential",
    },
    {
        "name": "Resolution",
        "brent_low": 55,
        "brent_high": 65,
        "description": "War ends, Iranian supply returns, OPEC+ unwinds cuts",
    },
]

# ─── Schedule (ET) ───────────────────────────────────────────────────────────
SCHEDULE_TIMEZONE = "US/Eastern"
NEWS_INTERVAL_HOURS = 2
MARKET_DATA_TIMES = [(10, 0), (13, 0), (16, 15)]
EIA_FRED_TIME = (11, 0)
AI_SUMMARY_TIMES = [(8, 0), (17, 0)]
SCENARIO_ANALYSIS_TIME = (17, 30)
DASHBOARD_REFRESH_SECONDS = 300

# ─── Dedup Threshold ─────────────────────────────────────────────────────────
HEADLINE_SIMILARITY_THRESHOLD = 0.6

# ─── UI ──────────────────────────────────────────────────────────────────────
DASH_HOST = "0.0.0.0"
DASH_PORT = 8050
DASH_DEBUG = True
DEFAULT_TIMELINE_DAYS = 30
