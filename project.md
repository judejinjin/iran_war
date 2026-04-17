Project
Conduct agentic investment analysis on oil super spike thesis due to the ongoing iran war by analyzing geopolitical develpment, WTI and Brent futures and options. the goal is to take advantage of the super spike to make the most money.

The project should be implemented in Python with interactive broker feed for futures and options of WTI and Brent and Dash UI. Geopolitical news should be searched from the internet. agentic analysis can be performed with copilot-sdk and other tools, whichever works best. 

Requirements:
1. daily summary for geopolitical news on the iran war and timeline view
2. Oil infrastructure damage daily summary and timeline view 
3. Oil production shut-in daily summary and timeline view
4. Oil shipment disruption due to hormuz closure - daily summary and timeline view
5. WTI and Brent futures curve daily view and timeline view to see change over time
6. Brent and WTI spread daily view and timeline view to see change over time
7. Daily updated summary of probabilities of different scenarios from the most bullish to the most bearish; and timeline to display change of the probabilities over time
8. Brent and WTI options daily summary and timeline change over time
9. agentic analysis of whether the options market reflect prbabilities correctly; identify where to put the best bets
10. agentic analysis of where to place the best, WTI and Brent, or a mix of both
11. use sqlite db to store data
12. users can enter positions in a UI; UI should project pnl by different scenarios
13. daily summary of military losses on both sides, total military deployment and pending deployment, timeline view, and map views wherever feasible across all modules

---

# Detailed Project Proposal: Oil Super Spike Agentic Investment Analyzer

## 1. Executive Summary

This project builds an **agentic investment analysis platform** that monitors the Iran war's impact on global oil markets and identifies optimal trading opportunities in WTI and Brent crude futures and options. The system combines real-time geopolitical intelligence gathering, market data from Interactive Brokers, and AI-driven scenario analysis to exploit a potential oil super spike — a rapid, outsized move in crude prices driven by supply disruption.

The platform runs as a local **Dash web application** backed by a **SQLite database**, with **periodic intraday data collection** (news every 2 hours, market data 3× daily), AI-powered analysis via **Claude Sonnet 4.6** (Anthropic API), and an interactive UI for position management and P&L projection. On first run, the system **backfills all historical data since the war start date** using free APIs (GDELT, FRED, Yahoo Finance, IB historical data).

---

## 2. Problem Statement

An oil super spike scenario (Brent > $150/bbl) becomes plausible when multiple supply disruptions compound simultaneously:

- **Direct production destruction**: Iranian and regional oil infrastructure targeted in military strikes
- **Strait of Hormuz closure/restriction**: ~20% of global oil transits through this chokepoint
- **Cascading shut-ins**: Neighboring producers (Iraq, Kuwait, UAE, Saudi Arabia) lose export capacity
- **SPR limitations**: Strategic reserves insufficient to offset sustained multi-million bbl/day disruption

The options market may misprice tail-risk scenarios because implied volatility surfaces are calibrated on recent history, not on wartime supply destruction. This creates an asymmetric opportunity: buy convexity cheaply if the market underestimates disruption probability.

**The core challenge**: synthesizing fast-moving geopolitical developments, quantifying their supply impact, translating that into probability-weighted price scenarios, and comparing those to what the options market implies — all updated daily.

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Dash Web UI (Browser)                   │
│  ┌──────────┐ ┌───────────┐ ┌────────────┐ ┌────────────┐  │
│  │Geopolitcl│ │  Futures  │ │  Options   │ │  Position  │  │
│  │ Timeline │ │  Curves   │ │  Analysis  │ │  Manager   │  │
│  └──────────┘ └───────────┘ └────────────┘ └────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────┴──────────────────────────────────────┐
│                   Dash Server (Python)                       │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌────────────┐  │
│  │  Layout   │ │ Callbacks │ │  Charting  │ │   Auth     │  │
│  │  Engine   │ │  Router   │ │  (Plotly)  │ │ (local)    │  │
│  └───────────┘ └───────────┘ └───────────┘ └────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│                    Core Services Layer                        │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────────────────────┐ │
│  │  Data Collectors  │  │       Agentic Analysis Engine    │ │
│  │                  │  │                                  │ │
│  │ • IB Gateway     │  │ • Claude Sonnet 4.6 Agents      │ │
│  │   (ib_insync)    │  │ • Scenario Probability Engine   │ │
│  │ • News Scraper   │  │ • Options Mispricing Detector   │ │
│  │   (web search)   │  │ • Trade Recommender             │ │
│  │ • RSS/API Feeds  │  │                                  │ │
│  └────────┬─────────┘  └──────────────┬───────────────────┘ │
│           │                           │                      │
│  ┌────────┴───────────────────────────┴───────────────────┐ │
│  │                  SQLite Database                        │ │
│  │  • geopolitical_events  • futures_curves               │ │
│  │  • infrastructure_damage • options_chains               │ │
│  │  • production_shutins   • scenario_probabilities        │ │
│  │  • shipment_disruptions • positions                     │ │
│  │  • agent_analyses       • daily_summaries               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language | Python 3.12 (Anaconda) | Ecosystem for finance, data, AI |
| Virtual Env | Conda (`oil` env) | Isolated dependencies; handles binary packages (numpy, scipy) well on Windows. Anaconda already installed. |
| Broker API | `ib_insync` | Async wrapper for IB TWS/Gateway API |
| Web UI | Dash + Plotly | Interactive financial dashboards, no JS needed |
| Database | SQLite via `sqlalchemy` | Lightweight, zero-config, single-file persistence |
| AI / LLM | Anthropic Claude Sonnet 4.6 (`anthropic` SDK) | Primary model for all agentic analysis (classification, summarization, scenarios, trade recommendations). Key in `.env`. |
| News (Primary) | RSS feeds + GDELT API (all free, no keys) | Real-time + historical geopolitical news |
| News (Fallback) | NewsAPI, Bing News (free tiers with keys) | Supplementary when primary sources are thin |
| Price History | FRED API + Yahoo Finance (free) | Historical backfill + daily cross-check |
| Energy Data | EIA API (free key) | Production, inventories, supply data |
| Scheduling | `APScheduler` | Periodic intraday data collection and analysis |
| Data Processing | `pandas`, `numpy` | Futures curves, options Greeks, scenario math |
| Options Pricing | `py_vollib` or `QuantLib` | Black-76 model for futures options, Greeks, IV |

### 3.3 Data Sources: API Keys & Cost Analysis

All primary data sources are **free**. Paid/limited sources are used only as fallbacks. API keys are stored in a `.env` file managed by `python-dotenv`.

#### NEWS SOURCES

| Source | API Key? | Cost | Historical Access | Rate Limits | Role |
|--------|----------|------|-------------------|-------------|------|
| **GDELT Project API** | No | Free | Full archive since Feb 2015 | ~1 req/5 sec | **PRIMARY** — best for historical backfill. Returns articles matching keywords with metadata. DOC 2.0 API supports date ranges, themes, tone scoring. |
| **Google News RSS** | No | Free | ~30 days rolling | No formal limit (don't abuse) | **PRIMARY** — real-time news. RSS feed at `news.google.com/rss/search?q=...`. No article body (headline + link only; scrape body with BeautifulSoup). |
| **Reuters RSS** | No | Free | Current items only | No formal limit | **PRIMARY** — authoritative commodities/world news. Feeds: `/rssFeed/worldNews`, `/rssFeed/commoditiesNews`. |
| **OilPrice.com RSS** | No | Free | Current items only | No formal limit | **PRIMARY** — oil-specific analysis and reporting. |
| **Al Jazeera RSS** | No | Free | Current items only | No formal limit | **PRIMARY** — Middle East–focused war coverage. |
| **BBC News RSS** | No | Free | Current items only | No formal limit | **PRIMARY** — global conflict reporting. |
| **NewsAPI.org** | Yes (free tier) | Free: 100 req/day; Developer: $449/mo | Free tier: 1 month. Paid: full archive | 100 req/day (free) | **FALLBACK** — structured JSON search. Free tier is yesterday+today only. Good for supplementing thin days. Sign up: newsapi.org/register |
| **Bing News Search API** | Yes (Azure free tier) | Free: 1,000 calls/month; S1: $7/1k calls | Free: 30 days Paid: full | 1,000/mo (free) | **FALLBACK** — Microsoft Cognitive Services. Free tier via Azure. Good structured search. |
| **Event Registry** | Yes (free tier) | Free: 2,000 articles/month; Paid: from $150/mo | Full archive (paid only) | 2,000 articles/mo (free) | **FALLBACK** — NLP-enriched, entity-tagged articles. Useful for high-quality classification. |

#### MARKET DATA SOURCES

| Source | API Key? | Cost | Historical Access | Rate Limits | Role |
|--------|----------|------|-------------------|-------------|------|
| **Interactive Brokers TWS** | No (uses TWS Desktop already installed) | Free with IB account (market data subscription may apply) | Daily bars: up to 1 year via `reqHistoricalData` | 60 requests / 10 min (historical); real-time snapshots unlimited during market hours | **PRIMARY** — live futures curves, options chains, Greeks. Connects to TWS Desktop on `localhost:7497` (paper) or `localhost:7496` (live). |
| **FRED API** (Federal Reserve) | Yes (free) | Completely free | Full history (decades) | 120 req/min | **PRIMARY for backfill** — daily WTI spot (series: `DCOILWTICO`) and Brent spot (series: `DCOILBRENTEU`). Register: fred.stlouisfed.org/docs/api/api_key.html |
| **Yahoo Finance** (`yfinance`) | No | Free | Full history | No formal API (scraping-based, occasional throttling) | **PRIMARY for backfill** — daily OHLCV for `CL=F` (WTI front-month). Also useful as cross-check for IB data. |
| **EIA API** (U.S. Energy Information Admin) | Yes (free) | Completely free | Full history (decades) | Generous (no published limit) | **PRIMARY** — weekly petroleum status report, crude inventories (series: `PET.WCESTUS1.W`), U.S. production, global production by country. Register: eia.gov/opendata/register.php |

#### API KEY SUMMARY

```
.env file contents:
─────────────────────────────────────────────────────
# REQUIRED (free registration)
EIA_API_KEY=your_eia_key_here          # eia.gov — free
FRED_API_KEY=your_fred_key_here        # fred.stlouisfed.org — free

# LLM — Claude Sonnet 4.6 (primary model for all agentic analysis)
CLAUDE_KEY=your_anthropic_key_here     # Anthropic API — pay-per-token
# Model: claude-sonnet-4-20250514 (used for dev & testing)
# Fallback keys (optional, if Anthropic is down):
# OPENAI_KEY=your_openai_key_here
# OPENROUTER_KEY=your_openrouter_key_here

# OPTIONAL FALLBACK NEWS SOURCES (free tier available)
NEWSAPI_KEY=your_newsapi_key_here      # newsapi.org — 100 req/day free
BING_NEWS_KEY=your_azure_key_here      # Azure Cognitive — 1000/mo free
EVENT_REGISTRY_KEY=your_er_key_here    # eventregistry.org — 2000 articles/mo free

# IB TWS — no API key needed, just TWS Desktop running with API enabled
TWS_HOST=127.0.0.1
TWS_PORT=7496
TWS_CLIENT_ID=1
```

> **Bottom line**: The system runs fully on free data sources. The only required registrations are EIA and FRED (both free, instant approval). NewsAPI/Bing/Event Registry are optional fallbacks if RSS feeds are insufficient on a given day.

---

## 4. Module Design

### 4.1 Module 1: Geopolitical News Intelligence (Requirements 1–4)

**Purpose**: Automated daily collection, classification, and summarization of Iran war developments affecting oil supply.

#### Data Sources (see Section 3.3 for full cost analysis)

**Primary (Free, no API key):**
- **GDELT Project API** — bulk keyword search, full historical archive since 2015, ideal for backfill
- **Google News RSS** — real-time keyword-based news feeds, no registration
- **Reuters RSS** — commodities and world news feeds
- **OilPrice.com RSS** — oil-specific coverage
- **Al Jazeera RSS** — Middle East conflict-focused
- **BBC News RSS** — global coverage
- **EIA API** — oil production, inventories, supply disruption data (free key)

**Fallback (Free tier with API key):**
- **NewsAPI.org** — structured search, 100 req/day free tier
- **Bing News Search** — 1,000 calls/month free via Azure
- **Event Registry** — NLP-enriched news, 2,000 articles/month free

**Search queries**: `"Iran war" OR "Iran strike" OR "Hormuz strait" OR "oil infrastructure" OR "IRGC" OR "oil tanker attack" OR "refinery strike" OR "pipeline damage" OR "production shut-in" OR "oil embargo" OR "OPEC emergency"`

#### Processing Pipeline
1. **Collect**: Fetch articles from all primary sources every 2 hours throughout the day (see Section 5)
2. **Deduplicate**: Fuzzy-match headlines (Jaccard similarity > 0.6) to avoid duplicates
3. **Classify**: AI agent categorizes each event into one of five buckets:
   - `geopolitical_development` — diplomatic, escalation/de-escalation, sanctions
   - `military_operations` — strikes, losses, deployments, troop movements, naval operations
   - `infrastructure_damage` — refineries, pipelines, terminals, storage
   - `production_shutin` — OPEC member output changes, force majeure declarations
   - `shipment_disruption` — Hormuz transit, tanker incidents, insurance/freight
4. **Summarize**: Daily AI-generated summary per category with severity scoring (1–10)
5. **Store**: All events + summaries persisted to SQLite with timestamps

#### Database Schema — Geopolitical Events
```sql
CREATE TABLE geopolitical_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    category TEXT NOT NULL,  -- geopolitical | military | infrastructure | shutin | shipment
    headline TEXT NOT NULL,
    summary TEXT,
    source_url TEXT,
    severity INTEGER CHECK(severity BETWEEN 1 AND 10),
    supply_impact_mbd REAL,  -- estimated million bbl/day impact
    latitude REAL,           -- event geolocation (for map views)
    longitude REAL,          -- event geolocation (for map views)
    location_name TEXT,      -- human-readable location (e.g. "Kharg Island", "Strait of Hormuz")
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    category TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    severity_avg REAL,
    total_supply_impact_mbd REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, category)
);
```

#### UI Components
- **Daily Summary Cards**: One card per category showing today's AI summary, severity badge, supply impact estimate
- **Interactive Map View** (Plotly Mapbox / `dash-leaflet`): Scattermapbox centered on Middle East/Persian Gulf region showing:
  - Geolocated events as markers, color-coded by category, sized by severity
  - Click marker → popup with headline, summary, timestamp
  - Infrastructure damage shown as red markers on oil facilities
  - Shipment disruptions shown along Hormuz strait shipping lanes
  - Filter by category, date range, severity
  - **Timeline slider**: Scrub through dates to animate events appearing on the map over time
- **Timeline View**: Plotly timeline/Gantt chart showing events over time, color-coded by category and severity
- **Drill-down**: Click any event to see full article text and AI analysis
- **Filters**: Date range, category, severity threshold

---

### 4.2 Module 2: Military Intelligence & Losses (Requirement 13)

**Purpose**: Track military losses, equipment destruction, troop deployments, and naval movements on both sides (Iran + allies vs. opposing coalition). Provides a daily war status dashboard with map visualization.

#### Data Sources
- Same news pipeline as Module 1 (GDELT, RSS feeds), filtered to `military_operations` category
- **ACLED API** (Armed Conflict Location & Event Data) — free for research, provides geolocated conflict events with fatality counts. Excellent for backfill.
- **Janes / OSINT Twitter aggregators** — scraped via RSS or API where available
- AI agent extracts structured data from unstructured news (casualty counts, equipment types, unit names, locations)

#### Military Data Extraction
The Claude agent parses each military news article and extracts:
- **Side**: `iran_coalition` or `opposing_coalition`
- **Loss type**: `personnel`, `aircraft`, `naval_vessel`, `armor`, `missile_battery`, `drone`, `other`
- **Quantity**: estimated count
- **Deployment type**: `active`, `pending`, `withdrawn`
- **Location**: lat/lng + name (e.g., "USS Eisenhower — Persian Gulf", "Bandar Abbas naval base")
- **Event type**: `strike`, `interception`, `deployment`, `withdrawal`, `naval_movement`

#### Database Schema — Military
```sql
CREATE TABLE military_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    side TEXT NOT NULL,            -- 'iran_coalition' or 'opposing_coalition'
    event_type TEXT NOT NULL,      -- 'strike', 'interception', 'deployment', 'withdrawal', 'naval_movement'
    loss_type TEXT,                -- 'personnel', 'aircraft', 'naval_vessel', 'armor', 'missile_battery', 'drone'
    quantity INTEGER,
    unit_name TEXT,                -- e.g. 'IRGC Quds Force', 'USS Eisenhower CSG'
    equipment_detail TEXT,         -- e.g. 'F-35A', 'Shahed-136 drone', 'Fateh-class submarine'
    headline TEXT,
    summary TEXT,
    source_url TEXT,
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE military_deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    side TEXT NOT NULL,
    deployment_status TEXT NOT NULL,  -- 'active', 'pending', 'withdrawn'
    force_type TEXT NOT NULL,         -- 'naval', 'air', 'ground', 'missile'
    unit_name TEXT,
    personnel_count INTEGER,
    equipment_summary TEXT,           -- JSON: {"carriers": 2, "destroyers": 8, ...}
    region TEXT,                      -- 'persian_gulf', 'red_sea', 'mediterranean', 'iran_mainland', etc.
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, side, unit_name)
);

CREATE TABLE military_daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    side TEXT NOT NULL,
    total_personnel_losses INTEGER DEFAULT 0,
    total_aircraft_losses INTEGER DEFAULT 0,
    total_naval_losses INTEGER DEFAULT 0,
    total_armor_losses INTEGER DEFAULT 0,
    total_missile_losses INTEGER DEFAULT 0,
    total_drone_losses INTEGER DEFAULT 0,
    cumulative_personnel_losses INTEGER DEFAULT 0,
    cumulative_aircraft_losses INTEGER DEFAULT 0,
    cumulative_naval_losses INTEGER DEFAULT 0,
    active_personnel_deployed INTEGER,
    pending_personnel_deployment INTEGER,
    summary_text TEXT,
    escalation_score INTEGER CHECK(escalation_score BETWEEN 1 AND 10),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, side)
);
```

#### UI Components
- **War Status Dashboard**: Two-column layout (Iran coalition | Opposing coalition) showing:
  - Today's losses by type (personnel, aircraft, naval, armor, drones) with running cumulative totals
  - Active deployment strength vs. pending reinforcements
  - Daily escalation score (1–10)
- **Military Map View** (Plotly Mapbox / `dash-leaflet`):
  - Full Middle East / Persian Gulf theater map
  - **Force deployment markers**: Blue (opposing coalition) vs. Red (Iran coalition), sized by force strength
  - **Strike locations**: Explosion icons at strike sites, color-coded by side
  - **Naval positions**: Ship icons along Gulf, Red Sea, Mediterranean
  - **Pending deployments**: Dashed-outline markers showing inbound reinforcements
  - Layer toggles: show/hide naval, air, ground, strikes independently
  - **Animation mode**: Play through dates to watch deployment evolution over time
- **Losses Timeline**: Stacked bar chart — daily losses by type per side, with cumulative line overlay
- **Deployment Timeline**: Area chart showing total active + pending forces over time per side
- **Escalation Score Timeline**: Line chart tracking escalation scores over time (key input to scenario probabilities)

---

### 4.3 Module 3: Futures Market Data (Requirements 5–6)

**Purpose**: Capture and display WTI (CL) and Brent (COIL) futures curves and spreads daily.

#### Interactive Brokers Integration
- **IB TWS Desktop is already installed** on the development machine
- Connect via `ib_insync` to TWS on `localhost:7497` (paper) or `localhost:7496` (live)
- TWS must be running with API connections enabled (File → Global Configuration → API → Settings → Enable ActiveX and Socket Clients)
- Request contract details for CL (NYMEX) and COIL (ICE via IB) front 24 months
- Snapshot prices multiple times per day during trading hours (see Section 5 schedule)
- Store full curves with intraday timestamps; the latest snapshot each day serves as the "daily" view
- **Historical backfill**: On first run, use `ib_insync`'s `reqHistoricalData()` to fetch daily bars for CL and COIL going back to war start date (configurable in `config.py`)

#### Database Schema — Futures
```sql
CREATE TABLE futures_curves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    symbol TEXT NOT NULL,       -- 'CL' or 'COIL'
    contract_month TEXT NOT NULL, -- '2026-04', '2026-05', etc.
    expiry_date DATE,
    settlement_price REAL,
    volume INTEGER,
    open_interest INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, symbol, contract_month)
);

CREATE TABLE spreads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    spread_type TEXT NOT NULL,   -- 'COIL-CL' (Brent-WTI), 'CL_M1-M2' (calendar)
    front_month TEXT,
    back_month TEXT,
    spread_value REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, spread_type, front_month)
);
```

#### UI Components
- **Futures Curve Chart**: Plotly line chart showing current CL and COIL term structures (price vs. contract month)
- **Curve Animation**: Slider to replay how the curve shape evolved over time (contango → backwardation shifts)
- **Spread Chart**: Brent-WTI spread over time; calendar spreads (M1-M2, M1-M6, M1-M12)
- **Key Metrics Panel**: Current front-month prices, backwardation depth, spread levels

---

### 4.4 Module 4: Options Market Intelligence (Requirement 8)

**Purpose**: Capture options chains for WTI and Brent, compute Greeks and implied volatilities, and track changes over time.

#### Data Collection
- Fetch full options chains from IB TWS (localhost) for CL and COIL (front 6 expiries)
- Refresh options data 3× daily during trading hours (see Section 5)
- For each strike: bid, ask, last, volume, open interest, implied volatility
- Compute Greeks via Black-76: delta, gamma, vega, theta
- **Historical backfill**: IB provides limited options history; on first run, store the first snapshot as the baseline and build history forward from there

#### Database Schema — Options
```sql
CREATE TABLE options_chains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    underlying TEXT NOT NULL,     -- 'CL' or 'COIL'
    expiry_date DATE NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL,    -- 'CALL' or 'PUT'
    bid REAL,
    ask REAL,
    last_price REAL,
    implied_vol REAL,
    delta REAL,
    gamma REAL,
    vega REAL,
    theta REAL,
    volume INTEGER,
    open_interest INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, underlying, expiry_date, strike, option_type)
);

CREATE TABLE vol_surface (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    underlying TEXT NOT NULL,
    expiry_date DATE NOT NULL,
    atm_vol REAL,
    skew_25d REAL,         -- 25-delta risk reversal
    smile_25d REAL,        -- 25-delta butterfly
    vol_of_vol REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, underlying, expiry_date)
);
```

#### UI Components
- **Vol Surface Heatmap**: Strike × Expiry heatmap of implied vols
- **Vol Smile Chart**: IV by strike for selected expiry, overlay multiple dates
- **Skew Tracker**: 25-delta risk reversal and butterfly over time (shows how tail risk pricing evolves)
- **Open Interest Profile**: OI by strike — shows where the market is positioned
- **Daily Change Table**: Biggest movers in IV, OI, and volume

---

### 4.5 Module 5: Scenario Probability Engine (Requirement 7)

**Purpose**: AI-driven daily assessment of scenario probabilities, tracked over time.

#### Scenario Framework

| Scenario | Brent Target | Description |
|----------|-------------|-------------|
| **Super Spike** | $180–250+ | Hormuz closed, multi-country production offline, SPR depleted |
| **Major Disruption** | $130–180 | Significant Iranian production offline + partial Hormuz restriction |
| **Moderate Escalation** | $100–130 | Limited strikes, some production loss, Hormuz open but risky |
| **Current State** | $80–100 | Contained conflict, minimal supply impact |
| **De-escalation** | $65–80 | Ceasefire/negotiations, sanctions relief potential |
| **Resolution** | $55–65 | War ends, Iranian supply returns, OPEC+ unwinds cuts |

#### Probability Assessment Process
1. AI agent ingests today's geopolitical summaries, **military escalation scores**, infrastructure damage reports, and shipment disruption data
2. Agent reviews current futures curve shape and options skew for market-implied sentiment
3. Agent reviews military deployment changes — major force build-ups or withdrawals shift probabilities
4. Agent produces updated probability distribution across scenarios with reasoning
5. Probabilities stored with justification text for auditability

#### Database Schema — Scenarios
```sql
CREATE TABLE scenario_probabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    scenario_name TEXT NOT NULL,
    probability REAL NOT NULL CHECK(probability BETWEEN 0 AND 1),
    brent_low REAL,
    brent_high REAL,
    reasoning TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, scenario_name)
);
```

#### UI Components
- **Probability Bar Chart**: Horizontal bars showing today's scenario probabilities
- **Probability Timeline**: Stacked area chart showing how probabilities shift day-to-day
- **Reasoning Panel**: Expandable text showing the AI's justification for each probability
- **Expected Value Display**: Probability-weighted expected Brent and WTI prices

---

### 4.6 Module 6: Agentic Options Mispricing Analysis (Requirements 9–10)

**Purpose**: Compare AI-assessed scenario probabilities to options-market-implied probabilities and identify asymmetric bets.

#### Analysis Pipeline

**Step 1: Extract Market-Implied Distribution**
- From the options chain, extract the risk-neutral probability distribution using the Breeden-Litzenberger method (second derivative of call prices w.r.t. strike)
- This gives the market's implied probability of Brent/WTI reaching each price level

**Step 2: Compare to AI Scenario Probabilities**
- Map AI scenarios to price ranges
- Compute: `edge = AI_probability(price_range) - market_implied_probability(price_range)`
- Positive edge = market underprices that outcome → buying opportunity

**Step 3: Identify Optimal Trades**
The AI agent evaluates:
- **Which strikes** offer the best expected value given the probability edge
- **Which expiries** balance theta decay vs. time for the thesis to play out
- **WTI vs. Brent vs. spread trades**: Brent is more directly exposed to Hormuz risk; WTI benefits via global substitution but less directly — the agent recommends the optimal mix
- **Structure recommendations**: Outright calls, call spreads (limit cost), strangles (play vol), ratio spreads (leverage convexity)

#### Agent Tooling (Claude Sonnet 4.6 via Anthropic API)

All agents use **Claude Sonnet 4.6** (`claude-sonnet-4-20250514`) via the `anthropic` Python SDK with tool use. The model is called with structured tool definitions; Claude decides when and how to invoke each tool.

```python
import anthropic

client = anthropic.Anthropic(api_key=os.environ["CLAUDE_KEY"])

# Agent has access to these tools (defined as Anthropic tool schemas):
tools = [
    get_current_futures_curves,      # Read latest CL/COIL curves from DB
    get_options_chain,               # Read latest options data from DB
    get_scenario_probabilities,      # Read AI scenario probs from DB
    compute_implied_distribution,    # Breeden-Litzenberger extraction
    price_option_black76,            # Price any option given vol/strike/expiry
    compute_expected_value,          # EV of a trade under scenario probs
    get_geopolitical_summary,        # Today's geopolitical context
    compute_greeks,                  # Full Greeks for any position
]

# Example agent call pattern:
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system="You are an oil markets analyst...",
    tools=tools,
    messages=[{"role": "user", "content": prompt}],
)
# Handle tool_use blocks → execute tool → return results → loop
```

#### Database Schema — Agent Analysis
```sql
CREATE TABLE agent_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    analysis_type TEXT NOT NULL,    -- 'mispricing' or 'trade_recommendation'
    underlying TEXT,                -- 'CL', 'COIL', or 'BOTH'
    summary TEXT NOT NULL,
    detailed_analysis TEXT,
    recommended_trades TEXT,        -- JSON array of trade suggestions
    confidence REAL CHECK(confidence BETWEEN 0 AND 1),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### UI Components
- **Mispricing Heatmap**: Strike × Expiry showing edge (AI prob minus market-implied prob)
- **Trade Recommendations Panel**: Ranked list of suggested trades with EV, max loss, payoff ratio
- **WTI vs Brent Comparison**: Side-by-side analysis of where the better opportunity lies
- **Agent Reasoning**: Full text of the agent's analysis, expandable

---

### 4.7 Module 7: Position Manager & P&L Projector (Requirement 12)

**Purpose**: Users enter their actual positions; the system projects P&L across all scenarios.

#### Position Entry
- UI form to add positions: underlying, contract month, strike (if option), quantity, entry price, option type
- Support for: futures (long/short), calls (long/short), puts (long/short), spreads (entered as legs)
- Positions stored in SQLite, editable and deletable from UI

#### P&L Projection Engine
For each scenario's price range:
1. Reprice each position at scenario target price using Black-76 (adjusting vol to scenario-implied level)
2. Sum P&L across all legs
3. Display per-scenario P&L and probability-weighted expected P&L

#### Database Schema — Positions
```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    underlying TEXT NOT NULL,       -- 'CL' or 'COIL'
    instrument_type TEXT NOT NULL,  -- 'FUTURE' or 'OPTION'
    contract_month TEXT NOT NULL,
    strike REAL,
    option_type TEXT,               -- 'CALL' or 'PUT' (null for futures)
    quantity INTEGER NOT NULL,      -- positive = long, negative = short
    entry_price REAL NOT NULL,
    entry_date DATE NOT NULL,
    is_open BOOLEAN DEFAULT 1,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pnl_projections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    position_id INTEGER REFERENCES positions(id),
    scenario_name TEXT NOT NULL,
    projected_underlying_price REAL,
    projected_option_price REAL,
    projected_pnl REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### UI Components
- **Position Table**: Editable table showing all open positions with current mark-to-market
- **Add Position Form**: Dropdowns and inputs for entering new positions
- **Scenario P&L Matrix**: Table — rows = positions, columns = scenarios, cells = P&L
- **Aggregate P&L Chart**: Bar chart showing total portfolio P&L per scenario, colored by probability
- **Payoff Diagram**: Classic options payoff curve at expiry overlaid with scenario price markers

---

## 5. Data Flow & Scheduling

### 5.1 Periodic Intraday Pipeline (runs via APScheduler)

All times in Eastern Time (ET). News runs throughout the day; market data runs during trading hours.

```
═══════════════════════════════════════════════════════════════
  RECURRING JOBS (every day, Mon–Fri)
═══════════════════════════════════════════════════════════════

NEWS COLLECTION — Every 2 hours, 24/7 (wars don't stop at market close)
  • 00:00, 02:00, 04:00, 06:00, 08:00, 10:00, 12:00,
    14:00, 16:00, 18:00, 20:00, 22:00 ET
  • Sources polled: GDELT API, Google News RSS, Reuters RSS,
    OilPrice.com RSS, Al Jazeera RSS, BBC RSS
  • Fallback sources (if primary returns < 5 articles):
    NewsAPI, Bing News
  • Each run: fetch → deduplicate → classify → store

MARKET DATA (IB TWS) — 3× daily during trading hours
  • 10:00 ET — Morning snapshot (after US open + initial volatility)
  • 13:00 ET — Midday snapshot
  • 16:15 ET — Settlement snapshot (after NYMEX close)
  • Each run: futures curves (CL + COIL, 24 months) +
    options chains (front 6 expiries) + spreads + Greeks

EIA / FRED DATA — Once daily at 11:00 ET
  • EIA: weekly petroleum status report, production data
  • FRED: daily spot prices for WTI + Brent
  • Yahoo Finance: front-month price cross-check

AI SUMMARIZATION — Twice daily
  • 08:00 ET — Morning summary (overnight + early news)
  • 17:00 ET — End-of-day summary (full day's events)
  • Generates: 4 category summaries, severity scores,
    supply impact estimates

SCENARIO & ANALYSIS — Once daily at 17:30 ET
  • Update scenario probabilities (using day's full data)
  • Run options mispricing analysis
  • Generate trade recommendations
  • Reproject P&L for all open positions

DASHBOARD — Auto-refresh every 5 minutes
  • UI polls latest data from SQLite
  • Incremental updates, no full page reload

═══════════════════════════════════════════════════════════════
  SCHEDULE SUMMARY
═══════════════════════════════════════════════════════════════

  Job                    Frequency        Hours (ET)
  ─────────────────────  ──────────────   ──────────────────
  News collection        Every 2 hours    24/7
  IB market data         3× daily         10:00, 13:00, 16:15
  EIA/FRED/Yahoo         1× daily         11:00
  AI news summaries      2× daily         08:00, 17:00
  Scenario analysis      1× daily         17:30
  Dashboard refresh      Every 5 min      While UI is open
```

### 5.2 First-Run Historical Backfill

On first launch (when the database is empty), the system runs a one-time backfill to populate historical data from the **war start date** (configurable in `config.py`, e.g., `WAR_START_DATE = "2026-01-15"`).

```
═══════════════════════════════════════════════════════════════
  BACKFILL PIPELINE (one-time, on first run)
═══════════════════════════════════════════════════════════════

Step 1: HISTORICAL NEWS BACKFILL
  Source: GDELT Project API (full archive, free, no key)
  • Query GDELT DOC API for each 1-day window from
    WAR_START_DATE to today
  • Keywords: Iran war, Hormuz, oil infrastructure, etc.
  • Rate limit: 1 request per 5 seconds (respect GDELT limits)
  • Each article: classify → store in geopolitical_events
  • Generate retroactive daily summaries for each past day
  • Estimated volume: ~100–500 articles/day × N days

Step 2: HISTORICAL PRICE BACKFILL
  Source: FRED API (free key) + Yahoo Finance (no key)
  • FRED: fetch DCOILWTICO (WTI) and DCOILBRENTEU (Brent)
    daily spot prices from WAR_START_DATE to today
  • Yahoo Finance: fetch CL=F daily OHLCV
    as cross-check and for volume/OI data
  • Store in futures_curves table with one entry per day

Step 3: HISTORICAL FUTURES CURVES BACKFILL
  Source: IB TWS (reqHistoricalData)
  • For each contract month (front 12): request daily bars
    from WAR_START_DATE to today
  • IB allows ~60 historical data requests per 10 minutes
  • Pacing: batch 6 contracts, wait 1 minute, next batch
  • Reconstructs full term structure for each historical day

Step 4: HISTORICAL EIA DATA BACKFILL
  Source: EIA API (free key)
  • Weekly petroleum status (crude inventories, production)
  • Monthly production by country (Iran, Iraq, Saudi)
  • All data from WAR_START_DATE to today

Step 5: GENERATE RETROACTIVE ANALYSES
  • Once historical data is loaded, run the scenario agent
    for each past week to produce weekly probability snapshots
  • This populates the scenario timeline so the UI
    isn't empty on first load

  ┌─────────────────────────────────────────────────────┐
  │  BACKFILL STATUS TRACKING                           │
  │                                                     │
  │  backfill_status table in SQLite tracks:             │
  │  • source (gdelt, fred, ib_futures, eia, scenarios) │
  │  • last_backfilled_date                             │
  │  • status (pending / in_progress / complete)        │
  │  • error_message (if failed)                        │
  │                                                     │
  │  If backfill is interrupted, it resumes from         │
  │  last_backfilled_date on next startup.              │
  └─────────────────────────────────────────────────────┘
```

#### Backfill Database Schema
```sql
CREATE TABLE backfill_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL UNIQUE,   -- 'gdelt', 'fred', 'yahoo', 'ib_futures', 'eia', 'scenarios'
    war_start_date DATE NOT NULL,
    last_backfilled_date DATE,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'in_progress', 'complete'
    total_records INTEGER DEFAULT 0,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Dash UI Layout

### Navigation: Top tab bar with 7 sections

| Tab | Content |
|-----|---------||
| **Geopolitical** | Daily summaries (5 categories) + event timeline + **event map** |
| **Military** | Losses dashboard (both sides), deployment tracker, **theater map**, escalation timeline |
| **Futures** | Curve charts, spread charts, historical overlays |
| **Options** | Vol surface, skew tracker, OI profile |
| **Scenarios** | Probability bars, probability timeline, reasoning |
| **Analysis** | Mispricing heatmap, trade recommendations, WTI vs Brent |
| **Portfolio** | Position entry, scenario P&L matrix, payoff diagrams |

### Design Principles
- Dark theme (financial standard)
- **Map views** use Plotly Scattermapbox with Mapbox GL (free tier: 50k loads/month) or `dash-leaflet` (fully free, OpenStreetMap tiles)
- All charts zoomable, pannable, with crosshair tooltips
- Map views support date-range animation (scrub through time to watch events unfold geographically)
- Every view has a date selector to look at historical snapshots
- Timeline views default to last 30 days with adjustable range
- Auto-refresh every 5 minutes when dashboard is open

---

## 7. Project Structure

```
oil/
├── project.md                  # This document
├── requirements.txt            # Python dependencies (pip install -r)
├── environment.yml             # Conda environment definition (conda env create -f)
├── config.py                   # IB connection, API keys, DB path, schedule
├── db/
│   ├── schema.sql              # Full database schema
│   ├── database.py             # SQLAlchemy engine, session, models
│   └── oil_data.db             # SQLite database file (gitignored)
├── collectors/
│   ├── __init__.py
│   ├── news_collector.py       # Geopolitical news fetching & classification
│   ├── military_collector.py   # Military losses, deployments, ACLED data
│   ├── ib_futures.py           # IB futures curve data collection
│   └── ib_options.py           # IB options chain data collection
├── analysis/
│   ├── __init__.py
│   ├── summarizer.py           # AI daily summary generation
│   ├── scenarios.py            # Scenario probability engine
│   ├── options_analysis.py     # IV surface, Breeden-Litzenberger, Greeks
│   ├── mispricing.py           # Market-implied vs AI probability comparison
│   └── trade_recommender.py    # Optimal trade identification
├── agents/
│   ├── __init__.py
│   ├── llm_client.py           # Anthropic SDK wrapper (Claude Sonnet 4.6) + fallback to OpenAI
│   ├── geopolitical_agent.py   # Claude agent for news classification & summarization
│   ├── military_agent.py       # Claude agent for military data extraction from news
│   ├── scenario_agent.py       # Claude agent for scenario probability updates
│   └── trading_agent.py        # Claude agent for trade recommendations
├── ui/
│   ├── __init__.py
│   ├── app.py                  # Dash app initialization
│   ├── layouts/
│   │   ├── geopolitical.py     # Geopolitical tab layout (includes map view)
│   │   ├── military.py         # Military tab layout (losses, deployments, theater map)
│   │   ├── futures.py          # Futures tab layout
│   │   ├── options.py          # Options tab layout
│   │   ├── scenarios.py        # Scenarios tab layout
│   │   ├── analysis.py         # Analysis tab layout
│   │   └── portfolio.py        # Portfolio tab layout
│   ├── callbacks/
│   │   ├── geopolitical_cb.py  # Geopolitical tab callbacks (map + timeline)
│   │   ├── military_cb.py      # Military tab callbacks (map + losses + deployments)
│   │   ├── futures_cb.py       # Futures tab callbacks
│   │   ├── options_cb.py       # Options tab callbacks
│   │   ├── scenarios_cb.py     # Scenarios tab callbacks
│   │   ├── analysis_cb.py      # Analysis tab callbacks
│   │   └── portfolio_cb.py     # Portfolio tab callbacks
│   └── components/
│       ├── timeline.py         # Reusable timeline component
│       ├── map_view.py         # Reusable Mapbox/Leaflet map component
│       ├── summary_card.py     # Reusable summary card component
│       └── payoff_chart.py     # Options payoff diagram component
├── backfill/
│   ├── __init__.py
│   ├── backfill_manager.py     # Orchestrates first-run historical backfill
│   ├── gdelt_backfill.py       # GDELT historical news fetcher
│   ├── fred_backfill.py        # FRED historical price fetcher
│   ├── yahoo_backfill.py       # Yahoo Finance historical data fetcher
│   ├── ib_backfill.py          # IB historical futures curves fetcher
│   └── eia_backfill.py         # EIA historical production/inventory fetcher
├── scheduler.py                # APScheduler intraday periodic pipeline
└── main.py                     # Entry point: backfill check → scheduler → Dash server
```

---

## 8. Key Dependencies

```
# Broker & Market Data
ib_insync>=0.9.86          # IB TWS API wrapper (connects to TWS Desktop on localhost)
yfinance>=0.2.36           # Yahoo Finance — free historical prices, no key
fredapi>=0.5.2             # FRED API client — free key required

# Web UI
dash>=2.17
dash-bootstrap-components>=1.6
dash-leaflet>=1.0            # Interactive maps (OpenStreetMap tiles, free)
plotly>=5.22

# AI / LLM — Claude Sonnet 4.6 is the primary model
anthropic>=0.42            # Anthropic SDK — Claude Sonnet 4.6 (primary)
openai>=1.30               # Fallback LLM provider (OpenAI / OpenRouter)

# Data & Analysis
pandas>=2.2
numpy>=1.26
scipy>=1.13               # For Breeden-Litzenberger interpolation
py_vollib>=1.0            # Black-76 options pricing & IV

# Database
sqlalchemy>=2.0
alembic>=1.13             # Schema migrations

# News & Web — all primary sources are FREE
requests>=2.32
feedparser>=6.0           # RSS feed parsing (Google News, Reuters, OilPrice, Al Jazeera, BBC)
beautifulsoup4>=4.12      # HTML parsing for article text extraction
newsapi-python>=0.2.7     # NewsAPI client (FALLBACK — free tier: 100 req/day)

# Scheduling
apscheduler>=3.10

# Utilities
python-dotenv>=1.0        # .env file for API keys (EIA_API_KEY, FRED_API_KEY, etc.)
loguru>=0.7               # Structured logging
thefuzz>=0.22             # Fuzzy string matching for headline deduplication
```

---

## 9. Implementation Phases

### Phase 1: Foundation (Week 1–2)
- Create Conda virtual environment: `conda create -n oil python=3.12 -y && conda activate oil`
- Install dependencies: `pip install -r requirements.txt`
- Project scaffolding, config, `.env` setup with free API keys (EIA, FRED)
- SQLite schema (all tables + backfill_status)
- IB TWS connection manager with `ib_insync` (verify TWS Desktop API is enabled)
- Historical backfill: FRED + Yahoo Finance price history since war start
- Historical backfill: IB futures curves via `reqHistoricalData`
- Basic Dash app with futures curve visualization

### Phase 2: News & Geopolitical Intelligence (Week 2–3)
- News collector: RSS feeds (Google, Reuters, OilPrice, Al Jazeera, BBC) + GDELT API
- GDELT historical backfill of all war-related articles since war start
- AI classification and summarization agent (5 categories incl. military)
- **Military data extraction agent** — losses, deployments, geolocations from news
- Retroactive daily summary generation for historical dates
- **Geopolitical event map** (dash-leaflet) with category-coded markers
- **Military theater map** with force deployment markers + strike locations
- Timeline UI with drill-down

### Phase 3: Options Data & Analytics (Week 3–4)
- Options chain collection from IB
- IV surface computation and storage
- Greeks calculation (Black-76)
- Options UI: vol surface, skew tracker, OI profile

### Phase 4: Scenario Engine (Week 4–5)
- Define scenario framework and database schema
- Scenario probability agent (Claude Sonnet 4.6 with tool use)
- Daily probability updates with reasoning
- Probability timeline UI

### Phase 5: Agentic Mispricing Analysis (Week 5–6)
- Breeden-Litzenberger implied distribution extraction
- AI-vs-market probability comparison
- Trade recommendation agent
- Mispricing heatmap and recommendation UI

### Phase 6: Position Management & P&L (Week 6–7)
- Position entry UI and CRUD operations
- Scenario-based P&L projection engine
- Payoff diagram generation
- Aggregate portfolio P&L matrix

### Phase 7: Integration & Polish (Week 7–8)
- Full intraday pipeline automation (APScheduler — news every 2h, market data 3×/day)
- Cross-tab data linking (click scenario → see impacted positions)
- Backfill resume logic (interrupted backfills restart from last checkpoint)
- Error handling, retry logic with exponential backoff, logging
- Performance optimization (query caching, lazy loading)

---

## 10. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| IB API rate limits / disconnections | Data gaps | Retry with exponential backoff; cache last-known data; graceful degradation in UI |
| News source API limits / paywalls | Incomplete geopolitical picture | 7 free primary sources (RSS + GDELT); paid APIs are fallback only; manual entry option in UI |
| LLM hallucination in analysis | Incorrect probabilities or trade recommendations | Always show reasoning; human review before execution; compare to market-implied as sanity check |
| Brent options liquidity on IB | Thin options chains for COIL | Use ICE Brent (BRN) as fallback; flag low-liquidity strikes in UI |
| SQLite write contention | Scheduler conflicts with UI reads | Use WAL journal mode; read-only connections for UI |
| Super spike doesn't materialize | Theta decay on options positions | Size positions for limited downside; use spreads to reduce cost; track thesis validity daily |

---

## 11. Success Criteria

1. **Intraday automated pipeline** runs without manual intervention — news every 2 hours, market data 3× daily, analysis by 17:30 ET
2. **Historical backfill** completes on first run, populating all data from war start date to present
3. **Scenario probabilities** update daily and track meaningfully with geopolitical developments (not random noise)
4. **Mispricing detection** identifies at least 3 actionable opportunities per week where AI probability exceeds market-implied by >5%
5. **Position P&L projections** match within 2% of actual IB P&L for realized scenarios
6. **UI response time** < 2 seconds for any view, including historical timeline queries
7. **Data completeness** > 95% of trading days have full futures + options snapshots
8. **Zero paid API dependencies** at launch — all primary data flows work with free sources only


