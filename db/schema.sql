-- Oil Super Spike Analyzer — Full Database Schema

PRAGMA journal_mode=WAL;

-- ═══════════════════════════════════════════════════════════════
--  GEOPOLITICAL & NEWS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS geopolitical_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    category TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    source_url TEXT,
    severity INTEGER CHECK(severity BETWEEN 1 AND 10),
    supply_impact_mbd REAL,
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    category TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    severity_avg REAL,
    total_supply_impact_mbd REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, category)
);

-- ═══════════════════════════════════════════════════════════════
--  MILITARY INTELLIGENCE
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS military_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    side TEXT NOT NULL,
    event_type TEXT NOT NULL,
    loss_type TEXT,
    quantity INTEGER,
    unit_name TEXT,
    equipment_detail TEXT,
    headline TEXT,
    summary TEXT,
    source_url TEXT,
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS military_deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    side TEXT NOT NULL,
    deployment_status TEXT NOT NULL,
    force_type TEXT NOT NULL,
    unit_name TEXT,
    personnel_count INTEGER,
    equipment_summary TEXT,
    region TEXT,
    latitude REAL,
    longitude REAL,
    location_name TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, side, unit_name)
);

CREATE TABLE IF NOT EXISTS military_daily_summary (
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

-- ═══════════════════════════════════════════════════════════════
--  FUTURES
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS futures_curves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    symbol TEXT NOT NULL,
    contract_month TEXT NOT NULL,
    expiry_date DATE,
    settlement_price REAL,
    volume INTEGER,
    open_interest INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, symbol, contract_month)
);

CREATE TABLE IF NOT EXISTS spreads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    spread_type TEXT NOT NULL,
    front_month TEXT,
    back_month TEXT,
    spread_value REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, spread_type, front_month)
);

-- ═══════════════════════════════════════════════════════════════
--  OPTIONS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS options_chains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    underlying TEXT NOT NULL,
    expiry_date DATE NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS vol_surface (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    underlying TEXT NOT NULL,
    expiry_date DATE NOT NULL,
    atm_vol REAL,
    skew_25d REAL,
    smile_25d REAL,
    vol_of_vol REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, underlying, expiry_date)
);

-- ═══════════════════════════════════════════════════════════════
--  PHYSICAL CRUDE PRICES
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS physical_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    symbol TEXT NOT NULL,         -- 'DATED_BRENT'
    price REAL NOT NULL,
    source TEXT NOT NULL,         -- 'FRED' | 'EIA' | 'IMF'
    freq TEXT NOT NULL DEFAULT 'daily',  -- 'daily' | 'monthly'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, symbol, source)
);

CREATE INDEX IF NOT EXISTS idx_physical_prices_date ON physical_prices(date);
CREATE INDEX IF NOT EXISTS idx_physical_prices_source ON physical_prices(symbol, source);

-- ═══════════════════════════════════════════════════════════════
--  SCENARIOS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS scenario_probabilities (
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

-- ═══════════════════════════════════════════════════════════════
--  AGENT ANALYSIS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS agent_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    analysis_type TEXT NOT NULL,
    underlying TEXT,
    summary TEXT NOT NULL,
    detailed_analysis TEXT,
    recommended_trades TEXT,
    confidence REAL CHECK(confidence BETWEEN 0 AND 1),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════════
--  POSITIONS & P&L
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    underlying TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    contract_month TEXT NOT NULL,
    strike REAL,
    option_type TEXT,
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    entry_date DATE NOT NULL,
    is_open BOOLEAN DEFAULT 1,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pnl_projections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    position_id INTEGER REFERENCES positions(id),
    scenario_name TEXT NOT NULL,
    projected_underlying_price REAL,
    projected_option_price REAL,
    projected_pnl REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════════
--  BACKFILL STATUS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS backfill_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL UNIQUE,
    war_start_date DATE NOT NULL,
    last_backfilled_date DATE,
    status TEXT NOT NULL DEFAULT 'pending',
    total_records INTEGER DEFAULT 0,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════════
--  INDEXES
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_geo_events_date ON geopolitical_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_geo_events_category ON geopolitical_events(category);
CREATE INDEX IF NOT EXISTS idx_military_events_date ON military_events(date);
CREATE INDEX IF NOT EXISTS idx_military_events_side ON military_events(side);
CREATE INDEX IF NOT EXISTS idx_futures_curves_date ON futures_curves(date, symbol);
CREATE INDEX IF NOT EXISTS idx_options_chains_date ON options_chains(date, underlying);
CREATE INDEX IF NOT EXISTS idx_scenario_prob_date ON scenario_probabilities(date);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(is_open);
CREATE INDEX IF NOT EXISTS idx_spr_levels_date ON spr_levels(date);
CREATE INDEX IF NOT EXISTS idx_spr_levels_country ON spr_levels(country_code);

-- ═══════════════════════════════════════════════════════════════
--  STRATEGIC PETROLEUM RESERVES
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS spr_levels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE    NOT NULL,
    country_code    TEXT    NOT NULL,
    country_name    TEXT    NOT NULL,
    spr_mbbl        REAL,
    commercial_mbbl REAL,
    total_mbbl      REAL,
    days_of_cover   REAL,
    source          TEXT    NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, country_code)
);
