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
WAR_START_DATE = "2026-02-28"

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
FUTURES_SYMBOLS = ["CL", "BZ"]
FUTURES_EXCHANGE = {"CL": "NYMEX", "BZ": "NYMEX"}  # BZ listed on NYMEX via ICE
FUTURES_MONTHS_AHEAD = 24          # Front 24 months for term structure
OPTIONS_EXPIRIES_AHEAD = 6         # Front 6 expiries for options chains

# ─── FRED Series ─────────────────────────────────────────────────────────────
FRED_WTI_SERIES = "DCOILWTICO"
FRED_BRENT_SERIES = "DCOILBRENTEU"

# ─── EIA Series ──────────────────────────────────────────────────────────────
EIA_CRUDE_INVENTORY = "PET.WCESTUS1.W"
EIA_US_PRODUCTION = "PET.WCRFPUS2.W"

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
