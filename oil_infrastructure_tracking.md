# Oil & Gas Infrastructure Production Tracking — Design & Implementation Plan

## Problem Statement

Track the real-time operational status of oil and natural gas production across all Gulf region producing countries impacted by the Iran war. Distinguish between:

- **Shut-in** production — temporarily offline, can resume quickly once conditions allow
- **Damaged** infrastructure — requires long-term repair (weeks to months), capacity degraded or destroyed

Current system only tracks aggregate `supply_impact_mbd` on news events. No facility-level inventory, no country-level baselines, no recovery timelines, no distinction between temporary and permanent capacity loss.

---

## Gulf Region Countries & Baseline Capacities (2026 estimates)

| Country | Oil (mbd) | NGL (mbd) | Gas (bcf/d) | Key Export Routes |
|---------|-----------|-----------|-------------|-------------------|
| Iran | 3.2 | 0.8 | 8.5 | Kharg Island, Lavan, Jask |
| Saudi Arabia | 10.5 | 1.8 | 10.0 | Ras Tanura, Yanbu, East-West Pipeline |
| Iraq | 4.5 | 0.3 | 3.0 | Basra Terminal, Kirkuk-Ceyhan |
| UAE | 3.2 | 0.6 | 6.0 | Fujairah, Jebel Ali, Habshan-Fujairah |
| Kuwait | 2.7 | 0.3 | 1.8 | Mina Al-Ahmadi, Mina Abdullah |
| Qatar | 1.8 | 0.8 | 16.0 | Ras Laffan (LNG), Al Shaheen |
| Oman | 1.0 | 0.2 | 4.0 | Mina Al-Fahal |
| Bahrain | 0.2 | 0.0 | 1.5 | BAPCO refinery |
| **Total** | **27.1** | **4.8** | **50.8** | |

Strait of Hormuz daily throughput: ~21 mbd oil + 16 bcf/d LNG

---

## Database Schema

### Table 1: `facility` — Master registry of oil/gas facilities

```sql
CREATE TABLE facility (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                   -- "Abadan Refinery", "Kharg Island Terminal"
    country         TEXT NOT NULL,                   -- ISO-like: "IR", "SA", "IQ", "AE", "KW", "QA", "OM", "BH"
    facility_type   TEXT NOT NULL,                   -- refinery | field | terminal | pipeline | storage | processing | lng_plant
    commodity       TEXT NOT NULL DEFAULT 'oil',     -- oil | gas | both
    capacity_oil_mbd    FLOAT DEFAULT 0.0,           -- nameplate oil capacity (million barrels/day)
    capacity_gas_bcfd   FLOAT DEFAULT 0.0,           -- nameplate gas capacity (billion cubic feet/day)
    latitude        FLOAT,
    longitude       FLOAT,
    region          TEXT,                            -- "Khuzestan", "Persian Gulf", "Eastern Province"
    owner_operator  TEXT,                            -- "NIOC", "Saudi Aramco", "ADNOC"
    is_export_critical  BOOLEAN DEFAULT FALSE,       -- TRUE = loss impacts global supply chains
    notes           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(name, country)
);
```

### Table 2: `facility_status` — Daily operational status per facility (time series)

```sql
CREATE TABLE facility_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id     INTEGER NOT NULL REFERENCES facility(id),
    date            DATE NOT NULL,
    status          TEXT NOT NULL,                   -- operational | shut_in | damaged | destroyed | partial
    cause           TEXT,                            -- airstrike | missile | sabotage | precautionary | sanctions | maintenance
    oil_offline_mbd     FLOAT DEFAULT 0.0,           -- oil production/throughput lost (mbd)
    gas_offline_bcfd    FLOAT DEFAULT 0.0,           -- gas production/throughput lost (bcf/d)
    oil_online_mbd      FLOAT DEFAULT 0.0,           -- remaining operational oil capacity
    gas_online_bcfd     FLOAT DEFAULT 0.0,           -- remaining operational gas capacity
    damage_pct      FLOAT DEFAULT 0.0,               -- 0.0 = intact, 1.0 = total destruction
    estimated_repair_days   INTEGER,                 -- NULL if operational or unknown
    estimated_recovery_date DATE,                    -- when expected back online
    confidence      TEXT DEFAULT 'estimated',        -- confirmed | estimated | rumored
    source_event_id INTEGER REFERENCES geopolitical_event(id),  -- link to triggering news event
    notes           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(facility_id, date)
);
```

### Table 3: `country_production` — Daily country-level production rollup

```sql
CREATE TABLE country_production (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE NOT NULL,
    country         TEXT NOT NULL,                   -- "IR", "SA", "IQ" etc.
    baseline_oil_mbd    FLOAT NOT NULL,              -- pre-war production capacity
    baseline_gas_bcfd   FLOAT NOT NULL,              -- pre-war gas capacity
    current_oil_mbd     FLOAT NOT NULL,              -- current operational (after shut-in + damage)
    current_gas_bcfd    FLOAT NOT NULL,
    shut_in_oil_mbd     FLOAT DEFAULT 0.0,           -- temporarily offline (reversible)
    shut_in_gas_bcfd    FLOAT DEFAULT 0.0,
    damaged_oil_mbd     FLOAT DEFAULT 0.0,           -- offline due to damage (long-term)
    damaged_gas_bcfd    FLOAT DEFAULT 0.0,
    sanctions_oil_mbd   FLOAT DEFAULT 0.0,           -- offline due to sanctions/embargo
    total_offline_oil_mbd   FLOAT DEFAULT 0.0,       -- shut_in + damaged + sanctions
    total_offline_gas_bcfd  FLOAT DEFAULT 0.0,
    pct_oil_offline     FLOAT DEFAULT 0.0,           -- total_offline / baseline
    pct_gas_offline     FLOAT DEFAULT 0.0,
    summary_text    TEXT,                             -- AI-generated daily narrative
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(date, country)
);
```

### Table 4: `disruption_event` — Individual shut-in or damage incidents

```sql
CREATE TABLE disruption_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id     INTEGER NOT NULL REFERENCES facility(id),
    event_type      TEXT NOT NULL,                   -- shut_in | damage | destruction | partial_damage | precautionary_shutdown
    start_date      DATE NOT NULL,
    end_date        DATE,                            -- NULL if ongoing
    is_resolved     BOOLEAN DEFAULT FALSE,
    cause           TEXT NOT NULL,                   -- airstrike | missile | drone | sabotage | fire | precautionary | sanctions
    oil_impact_mbd  FLOAT DEFAULT 0.0,
    gas_impact_bcfd FLOAT DEFAULT 0.0,
    damage_pct      FLOAT DEFAULT 0.0,               -- 0-1 scale
    repair_estimate_days    INTEGER,
    repair_cost_estimate_m  FLOAT,                   -- millions USD
    source_event_id INTEGER REFERENCES geopolitical_event(id),
    headline        TEXT,
    summary         TEXT,
    confidence      TEXT DEFAULT 'estimated',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Table 5: `hormuz_status` — Strait of Hormuz transit tracking

```sql
CREATE TABLE hormuz_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE NOT NULL UNIQUE,
    status          TEXT NOT NULL,                   -- open | restricted | partial_blockade | full_blockade
    oil_transit_mbd     FLOAT,                       -- estimated daily oil transit
    lng_transit_bcfd    FLOAT,                       -- estimated daily LNG transit
    normal_oil_mbd      FLOAT DEFAULT 21.0,          -- baseline transit capacity
    reduction_pct       FLOAT DEFAULT 0.0,           -- 0.0-1.0
    insurance_war_risk_pct  FLOAT,                   -- war risk insurance premium for tankers
    tanker_diversions   INTEGER DEFAULT 0,           -- ships rerouted
    naval_incidents     INTEGER DEFAULT 0,           -- mining, harassment, seizure events
    summary_text    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Table 6: `region_supply_summary` — Aggregate Gulf output snapshot

```sql
CREATE TABLE region_supply_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE NOT NULL UNIQUE,
    total_baseline_oil_mbd      FLOAT NOT NULL,      -- sum of all countries
    total_current_oil_mbd       FLOAT NOT NULL,
    total_offline_oil_mbd       FLOAT NOT NULL,      -- shut_in + damaged + sanctions + hormuz
    total_shut_in_oil_mbd       FLOAT DEFAULT 0.0,
    total_damaged_oil_mbd       FLOAT DEFAULT 0.0,
    total_sanctions_oil_mbd     FLOAT DEFAULT 0.0,
    total_hormuz_blocked_mbd    FLOAT DEFAULT 0.0,
    total_baseline_gas_bcfd     FLOAT NOT NULL,
    total_current_gas_bcfd      FLOAT NOT NULL,
    total_offline_gas_bcfd      FLOAT NOT NULL,
    pct_global_supply_offline   FLOAT DEFAULT 0.0,   -- vs ~100 mbd global demand
    brent_price                 FLOAT,               -- close price on this date
    wti_price                   FLOAT,
    ai_narrative                TEXT,                 -- AI daily narrative of supply situation
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Entity-Relationship Diagram

```
┌──────────────────┐       ┌────────────────────┐
│    facility       │───1:N──│  facility_status   │  (daily snapshot per facility)
│                   │       │                    │
│  name, country,   │       │  date, status,     │
│  type, commodity, │       │  oil/gas offline,  │
│  capacity,        │       │  damage_pct,       │
│  lat/lon          │       │  repair estimate   │
└─────────┬────────┘       └────────────────────┘
          │
          │1:N
          ▼
┌──────────────────┐       ┌────────────────────┐
│ disruption_event  │       │  geopolitical_event │  (existing table)
│                   │──────▶│                    │
│  event_type,      │  FK   │  headline, category│
│  start/end_date,  │       │  supply_impact_mbd │
│  cause, impact,   │       └────────────────────┘
│  repair_estimate  │
└──────────────────┘

┌──────────────────┐       ┌────────────────────┐
│country_production │       │   hormuz_status    │
│                   │       │                    │
│  date, country,   │       │  date, status,     │
│  baseline vs      │       │  transit volume,   │
│  current output,  │       │  insurance, naval  │
│  by cause type    │       │  incidents         │
└──────────────────┘       └────────────────────┘
          │                         │
          └───────────┬─────────────┘
                      ▼
          ┌────────────────────┐
          │region_supply_summary│  (daily rollup of everything)
          │                    │
          │  total offline,    │
          │  by cause bucket,  │
          │  % global supply,  │
          │  brent/wti price   │
          └────────────────────┘
```

---

## Implementation Plan

### Phase 1: Schema & Seed Data

**Goal**: Create tables, seed facility registry and country baselines.

**Tasks**:
1. Add 6 new SQLAlchemy models to `db/database.py`: `Facility`, `FacilityStatus`, `CountryProduction`, `DisruptionEvent`, `HormuzStatus`, `RegionSupplySummary`
2. Create `db/seed_facilities.py` — populate `facility` table with ~50 key facilities:
   - Iran: 9 refineries, 5 major fields (Gachsaran, Ahvaz-Asmari, Marun, Agha-Jari, Bibi-Hakimeh), 4 export terminals (Kharg, Lavan, Jask, Bandar Abbas), South Pars gas complex
   - Saudi Arabia: 6 refineries, Ghawar/Safaniyah/Khurais fields, Ras Tanura/Yanbu/Juaymah terminals, Abqaiq processing
   - Iraq: 4 refineries, Rumaila/West Qurna/Zubair fields, Basra terminal, Kirkuk-Ceyhan pipeline
   - UAE: ADNOC refineries, Upper Zakum/Bu Hasa fields, Fujairah/Jebel Ali terminals, Das Island
   - Kuwait: Mina Al-Ahmadi/Mina Abdullah, Burgan field, KOC processing
   - Qatar: Ras Laffan LNG, North Field gas, Al-Shaheen oil
   - Oman: Mina Al-Fahal, Yibal/Fahud fields
   - Bahrain: BAPCO refinery, Awali field
3. Create `db/seed_baselines.py` — populate pre-war `country_production` row for WAR_START_DATE with baseline capacities
4. Initialize `hormuz_status` with baseline row (status=open, 21 mbd transit)

**Files**:
- `db/database.py` — add models
- `db/seed_facilities.py` — facility registry
- `db/seed_baselines.py` — baseline production data

---

### Phase 2: AI-Powered Disruption Extraction Agent

**Goal**: Automatically extract facility-level disruption events from news, classify shut-in vs damage, estimate impacts.

**Tasks**:
1. Create `agents/infrastructure_agent.py` with two main functions:
   - `extract_disruption_from_event(event_id)` — Takes a GeopoliticalEvent (category=infrastructure_damage or production_shutin), uses Claude to extract:
     - Which facility was affected (fuzzy match to facility registry)
     - Event type: shut_in | damage | destruction | precautionary_shutdown
     - Oil/gas impact in mbd/bcf/d
     - Damage percentage (0-100%)
     - Estimated repair time (days)
     - Cause: airstrike | missile | drone | sabotage | fire | precautionary | sanctions
   - `update_daily_status(date)` — For a given date, roll forward previous day's status, apply any new disruption_events, compute country_production and region_supply_summary

2. Claude prompt design for disruption extraction:
   ```
   Given this news event about oil/gas infrastructure:
   Headline: {headline}
   Summary: {summary}
   Location: {location_name}

   And this facility registry: {nearby_facilities}

   Extract:
   - facility_match: best matching facility name (or "unknown" if new)
   - event_type: shut_in | damage | destruction | partial_damage | precautionary_shutdown
   - oil_impact_mbd: estimated oil production/throughput lost
   - gas_impact_bcfd: estimated gas lost
   - damage_pct: 0.0 to 1.0 (0=intact, 1=destroyed)
   - repair_estimate_days: integer or null
   - cause: airstrike | missile | drone | sabotage | fire | precautionary | sanctions
   - confidence: confirmed | estimated | rumored
   ```

3. Facility fuzzy matching: use `thefuzz` to match extracted facility names to the `facility` registry (threshold 70%)

**Files**:
- `agents/infrastructure_agent.py`

---

### Phase 3: Daily Status Pipeline

**Goal**: Automated daily rollup of all facility statuses into country and regional summaries.

**Tasks**:
1. Create `collectors/production_tracker.py`:
   - `compute_daily_status(target_date)`:
     - For each facility: look at latest disruption_event (unresolved), compute current status
     - Upsert `facility_status` for the date
     - Aggregate by country → upsert `country_production`
     - Sum all countries + Hormuz impact → upsert `region_supply_summary`
   - `update_hormuz_status(target_date)`:
     - Query shipment_disruption events for the date
     - Estimate transit reduction from naval incidents, blockade events
     - Upsert `hormuz_status`

2. Recovery logic:
   - Shut-in facilities auto-recover after `estimated_repair_days` unless a new disruption extends it
   - Damaged facilities remain degraded until explicitly resolved (manual or news-driven)
   - Partial damage: capacity reduced by `damage_pct`, remainder operational

3. Status rollforward rules:
   ```
   For each facility on date D:
     1. Copy status from D-1 (if exists)
     2. Apply any new disruption_events with start_date = D
     3. Check if any existing disruption has end_date = D → mark resolved
     4. Check if estimated_recovery_date ≤ D → auto-recover shut-ins
     5. Compute: oil_online = capacity - oil_offline
   ```

4. Integrate into scheduler: add `compute_daily_status()` to the daily pipeline in `main.py`

**Files**:
- `collectors/production_tracker.py`
- `main.py` — add to pipeline

---

### Phase 4: Infrastructure Tab Enhancements

**Goal**: Upgrade the existing Infrastructure tab with facility-level tracking and country breakdowns.

**Tasks**:
1. Update `ui/layouts/infrastructure.py`:
   - Add **Country Production Dashboard** section: stacked bar chart showing baseline vs current for each country, split by cause (shut-in / damaged / sanctions)
   - Add **Facility Status Table**: sortable table with facility name, country, type, status, capacity, offline amount, damage %, recovery ETA
   - Add **Regional Supply Waterfall**: waterfall chart from baseline (27.1 mbd) → shut-ins → damage → sanctions → Hormuz → current available
   - Add **Hormuz Transit Panel**: status badge, transit volume, war risk premium
   - Keep existing damage timeline and cumulative impact charts

2. Update `ui/callbacks/infrastructure_cb.py`:
   - New callback for country production chart
   - New callback for facility status table
   - New callback for waterfall chart
   - New callback for Hormuz status

3. Update `ui/components/map_view.py`:
   - Enhance `create_infrastructure_map()`: facility markers colored by status (green=operational, yellow=shut-in, red=damaged, black=destroyed)
   - Size by capacity: larger facilities = larger markers
   - Tooltip shows: name, status, offline amount, recovery ETA

**Files**:
- `ui/layouts/infrastructure.py`
- `ui/callbacks/infrastructure_cb.py`
- `ui/components/map_view.py`

---

### Phase 5: Shut-in vs Damage Analysis & Scenarios

**Goal**: Integrate production tracking with scenario engine for forward-looking analysis.

**Tasks**:
1. Create `agents/production_scenario_agent.py`:
   - For each scenario (from ScenarioProbability table), estimate production impact:
     - **Diplomacy/ceasefire**: shut-ins recover in X days, damaged facilities begin repair
     - **Prolonged conflict**: shut-ins persist, damage accumulates, Hormuz narrows
     - **Full escalation**: Saudi/UAE facilities targeted, Hormuz fully blocked
   - Output: scenario-specific `total_offline_mbd` and recovery timeline

2. Add production impact to existing scenarios tab:
   - Show "Supply Offline by Scenario" chart
   - Show "Recovery Timeline by Scenario" (Gantt-like view)

3. Link to futures analysis:
   - Compare current offline mbd with historical supply disruptions (Libya 2011: 1.5 mbd, Kuwait 1990: 5.0 mbd, etc.)
   - Estimate price impact per mbd offline (rule of thumb: ~$5-10/bbl per 1 mbd)

**Files**:
- `agents/production_scenario_agent.py`
- `ui/callbacks/scenarios_cb.py` — add production impact outputs

---

### Phase 6: Historical Backfill

**Goal**: Reconstruct facility disruption history since WAR_START_DATE.

**Tasks**:
1. Create `backfill/production_backfill.py`:
   - For each date since WAR_START_DATE:
     - Query existing GeopoliticalEvents (infrastructure_damage, production_shutin)
     - Run infrastructure_agent to extract disruption_events
     - Run production_tracker to compute daily status
   - This builds the full time-series retroactively

2. One-time baseline initialization:
   - On WAR_START_DATE - 1: all facilities operational, all countries at baseline
   - WAR_START_DATE: first disruption events applied

**Files**:
- `backfill/production_backfill.py`

---

## Data Flow

```
RSS/GDELT News
    │
    ▼
GeopoliticalEvent (existing)
    │ category = infrastructure_damage | production_shutin | shipment_disruption
    ▼
infrastructure_agent.py ──extract──▶ DisruptionEvent
    │                                    │
    │                                    ▼
    │                              ┌─ facility_status (per facility per day)
    │                              │
    ▼                              ├─ country_production (per country per day)
production_tracker.py ─────────────┤
    │                              ├─ hormuz_status (daily)
    │                              │
    │                              └─ region_supply_summary (daily rollup)
    ▼
UI: Infrastructure Tab
    ├─ Country bar charts (baseline vs current, by cause)
    ├─ Facility status map (color by operational status)
    ├─ Regional supply waterfall
    ├─ Hormuz transit panel
    ├─ Disruption event timeline
    └─ Facility status table
```

---

## Key Design Decisions

1. **Shut-in vs Damaged distinction**: Shut-ins are reversible (precautionary closures, blockades). Damaged requires physical repair. This maps to `disruption_event.event_type` and drives recovery logic.

2. **Facility registry as source of truth**: All capacity data lives in `facility` table. Status is tracked as delta from capacity, not absolute.

3. **Daily snapshot model**: `facility_status` and `country_production` store one row per entity per day. This enables clean time-series charting without complex window queries.

4. **AI extraction with human override**: Agent extracts disruptions from news, but results can be manually corrected via future admin UI or direct DB edits.

5. **Both oil AND gas**: Schema tracks both commodities since Iran war affects gas (South Pars, LNG exports) as much as oil. Gas in bcf/d, oil in mbd.

6. **Hormuz as separate entity**: Strait of Hormuz impacts all Gulf exporters simultaneously, tracked separately from individual facility status.

7. **Confidence levels**: All data tagged with `confirmed | estimated | rumored` since wartime information is unreliable.
