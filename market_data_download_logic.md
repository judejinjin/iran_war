# Market Data Download Logic

## Architecture Overview

The system uses a **three-tier architecture**:

1. **Backfill System** — one-time + incremental historical loading from `WAR_START_DATE` (2026-02-28)
2. **Collectors** — real-time retrieval on fixed schedules (futures, options, news, military)
3. **Scheduler** — APScheduler orchestrating periodic jobs

All data flows through a **SQLite WAL database** (`db/oil_data.db`).

---

## 1. Backfill System

### BackfillManager (`backfill/backfill_manager.py`)

Master orchestrator. Manages 7 sources via `backfill_status` table:

| Source | Runner File | Status |
|--------|-------------|--------|
| fred | `fred_backfill.py` | Spot prices |
| yahoo | `yahoo_backfill.py` | Volume enrichment |
| ib_futures | `ib_backfill.py` | Futures curves |
| ib_options | `ib_options_backfill.py` | Options + Greeks |
| eia | `eia_backfill.py` | Weekly inventory |
| gdelt | `gdelt_backfill.py` | News + classification |
| scenarios | — | Not yet implemented |

**Two modes:**

- `run()` — One-time: skips sources already marked `complete`
- `run_incremental()` — Resets `complete` → `pending`, re-fetches from `last_backfilled_date` to today

**Status tracking:** Each source has a row in `backfill_status` with `status` (pending/in_progress/complete), `last_backfilled_date`, `total_records`, `error_message`, timestamps.

**Entry point:** `main.py` calls `BackfillManager.run_incremental()` on startup with flags:
- `--skip-backfill`: Skip all backfill
- `--skip-scheduler`: Don't start scheduled jobs
- `--backfill-only`: Run backfill then exit
- `--ib-options`: Include IB options backfill (requires TWS)

---

### FRED Backfill (`backfill/fred_backfill.py`)

**Source:** Federal Reserve Economic Data API (`fredapi`)

| Series ID | Symbol | Start Date |
|-----------|--------|------------|
| DCOILWTICO | CL (WTI) | `start_from` |
| DCOILBRENTEU | COIL (Brent) | `start_from` |
| POILDUBUSDM | DUB (Dubai) | 1992-01-01 (always full history) |

**Storage:** `futures_curves` table — `settlement_price` only (no volume from FRED).  
**Upsert:** INSERT if row doesn't exist; skip if already present.  
**Error handling:** Re-raises exceptions (fatal).

---

### Yahoo Finance Backfill (`backfill/yahoo_backfill.py`)

**Source:** Yahoo Finance (`yfinance`)

| Ticker | Symbol |
|--------|--------|
| CL=F | CL (WTI front-month) |

**Purpose:** Cross-check FRED prices + **enrich with volume** (FRED has no volume).  
**Storage:** `futures_curves` — updates existing rows with volume, inserts new if absent.  
**Limitation:** Front-month only.

---

### EIA Backfill (`backfill/eia_backfill.py`)

**Source:** U.S. Energy Information Administration API v2

| Series | Description |
|--------|-------------|
| PET.WCESTUS1.W | US Crude Inventory (weekly) |
| PET.WCRFPUS2.W | US Crude Production (weekly) |

**Endpoint:** `https://api.eia.gov/v2/petroleum/sum/sndw/data/`  
**Storage:** Currently **not persisted** to main schema — treated as supplementary metadata.  
**Error handling:** Non-fatal (logs warning, continues).

---

### GDELT News Backfill (`backfill/gdelt_backfill.py`)

**Source:** GDELT DOC 2.0 API + NewsAPI fallback

**Day-by-day pipeline per date:**

1. **Fetch articles** from GDELT (or NewsAPI if rate-limited)
2. **Deduplicate** — URL hash + headline fuzzy matching (60% threshold via `token_sort_ratio`)
3. **Extract bodies** — BeautifulSoup on top 10 articles (removes script/style/nav/footer)
4. **Store raw** → `geopolitical_events` (category = `unclassified`)
5. **LLM batch classification** via `geopolitical_agent` → updates category, severity (1-10), supply_impact_mbd, coordinates
6. **Disruption extraction** → `disruption_event` (facility_id, oil_impact_mbd, damage_pct, repair_estimate_days)
7. **Military extraction** → `military_events` + `military_deployments`
8. **Daily summaries** → `daily_summaries` + `military_daily_summary`
9. **Update status** — `last_backfilled_date = current_date`

**Rate limiting:** Exponential backoff — 15s base (GDELT minimum), retries at 20/40/80/160/320s, max 5 retries. Handles 429 codes + stealth rate-limits (empty body / HTML errors). 3 consecutive failures = stop (resume next run).

**Resumption:** Tracks `last_backfilled_date` so interrupted runs pick up where they left off.

---

### IB Futures Backfill (`backfill/ib_backfill.py`)

**Source:** Interactive Brokers TWS API

**Instruments:** CL (NYMEX) + COIL (IPE), front 12 contract months.

**Fetch per contract:**
```
contract = Future(symbol, exchange, lastTradeDateOrContractMonth=YYYYMM)
ib.qualifyContracts(contract)
bars = ib.reqHistoricalData(
    contract, endDateTime="",
    durationStr=f"{days} D",
    barSizeSetting="1 day",
    whatToShow="TRADES",
    useRTH=True
)
```

**Rate limiting:** Batch 6 contracts, wait 65s between batches (IB allows ~60 requests/10min).  
**Storage:** `futures_curves` — INSERT if not exists (skip if FRED/Yahoo already present).  
**Error handling:** Warns on unqualified contracts, skips; re-raises connection failures.

---

### IB Options Backfill (`backfill/ib_options_backfill.py`)

**The most complex component.** 10-step pipeline per symbol:

#### Step 1 — Contract Discovery

```python
details = ib.reqContractDetails(Future(symbol, exchange))
futures_months = [d.contract for d in details[:OPTIONS_EXPIRIES_AHEAD]]  # front 12
```

#### Step 2 — Chain Metadata

For each futures month, call `reqSecDefOptParams` to get expirations + strikes. Builds:
- `expiry_to_fut_month` mapping — e.g. option exp `20260527` → futures `2026-06`
- Filters to preferred trading class: **LO** for CL, **COIL** for COIL

**Month offset logic:**
- CL (WTI): option expiry month + 1 → futures month
- COIL (Brent): option expiry month + 2 → futures month

#### Step 3 — Underlying Price Maps

Fetches daily MIDPOINT bars for each futures contract month. Returns `{contract_month: {date: price}}`. Also persists to `futures_curves` so `recompute_greeks()` works offline.

#### Step 4 — Strike Filtering

```python
low_strike  = underlying_price * 0.50   # -50%
high_strike = underlying_price * 3.00   # +300%
relevant_strikes = [s for s in all_strikes if low <= s <= high and s % 10 == 0]
```

Typically yields ~24 strikes.

#### Step 5 — Contract Building

`expirations × relevant_strikes × [C, P]` → ~500-1200 `FuturesOption` contracts grouped by expiry.

#### Step 6 — Async Wave Fetching

```python
CONCURRENT_REQUESTS = 45   # under IB's 50-simultaneous limit
WAVE_PAUSE_SECONDS = 2

for wave in chunks(all_contracts, 45):
    pending = []
    loop = util.getLoop()  # ib_insync's loop (Python 3.12 safe)
    for opt_info in wave:
        coro = ib.reqHistoricalDataAsync(
            opt, endDateTime="",
            durationStr=f"{days_back} D",
            barSizeSetting="1 hour",
            whatToShow="MIDPOINT",
            useRTH=True
        )
        task = loop.create_task(coro)
        pending.append(task)
    
    while not all(t.done() for t in pending):
        ib.sleep(0.1)
    # process results...
    time.sleep(2)
```

**Key choices:**
- **1-hour bars** (not daily) — hourly MIDPOINT data is available for inactive/deep OTM strikes
- **MIDPOINT** (not TRADES) — more coverage for illiquid options
- **45 concurrent** — just under IB's 50 simultaneous limit

#### Step 6b — Hourly→Daily Aggregation + Black-76 Greeks

For each contract's bars:
1. Aggregate hourly bars to daily (last close of day, sum volume)
2. Look up underlying futures price for this date + expiry
3. Compute IV via Black-76 inverse (Brent's method, bounds 0.1%–500%)
4. Compute Greeks: delta, gamma, vega, theta
5. Batch upsert via `INSERT ON CONFLICT DO UPDATE`

**Black-76 model** (for futures options):
```
d1 = (ln(F/K) + 0.5σ²T) / (σ√T)
d2 = d1 - σ√T
Call = e^(-rT) * [F·N(d1) - K·N(d2)]
Put  = e^(-rT) * [K·N(-d2) - F·N(-d1)]
```
Risk-free rate: `r = 0.045`

#### Step 7 — Vol Surface Computation

For each (date, expiry): compute ATM vol, 25-delta risk-reversal (skew), 25-delta butterfly (smile). Stored in `vol_surface` table.

#### Step 7b — Symmetric Strike Fill

IB MIDPOINT bars only cover strikes with active quoting. Insert placeholder rows for the missing side (if CALL exists but PUT doesn't for same strike, insert a PUT row with NULL prices). Uses `INSERT OR IGNORE`.

#### Step 7c — Ensure Today's Rows

Historical bars only return data for ~20% of strikes on any given day. Insert placeholder rows for **ALL** requested strikes on today's date so the UI shows the complete grid and market snapshots can fill them.

```sql
INSERT OR IGNORE INTO options_chains
    (date, underlying, expiry_date, strike, option_type, underlying_contract_month, created_at)
VALUES (today, symbol, expiry, strike, opt_type, ucm, CURRENT_TIMESTAMP)
```

#### Step 8 — Live Market Snapshots

After historical bars, fetch today's live bid/ask/OI/volume:

```python
ticker = ib.reqMktData(opt, genericTickList="100,101,106", snapshot=False)
ib.sleep(5)  # wait for ticks
bid, ask, last, oi, volume = extract(ticker)
ib.cancelMktData(ticker.contract)
```

Tick types: 100=OptionVolume, 101=OptionOI, 106=OI.  
Upsert via `INSERT ON CONFLICT DO UPDATE` (creates rows even without historical bar data).

#### Offline Recompute — `recompute_greeks()`

Fills NULL IV/Greeks for existing rows using DB-stored underlying prices. No IB connection needed. Called from `main.py` after backfill completes.

---

## 2. Real-Time Collectors

### IB Connection Manager (`collectors/ib_connection.py`)

- Host: `127.0.0.1`, Port: `7496` (TWS paper), Client ID: `1`
- Mode: `readonly=True`
- Retry: 3 attempts with 5/10/15s backoff
- `ensure_connected()` for reconnection

### Futures Collector (`collectors/ib_futures.py`)

**`collect_futures_snapshot()`** — Front 24 months for CL + COIL:
1. Try `reqMktData(snapshot=True)` → `ticker.last` or `ticker.close` or `ticker.bid`
2. Fallback: 3-day `reqHistoricalData` if snapshot invalid
3. Upsert to `futures_curves`
4. Compute spreads: Brent-WTI, calendar spreads (M1-M2, M1-M6, M1-M12) → `spreads` table
5. Pacing: 0.3s between requests

**`collect_historical_curves()`** — Past 30 business days, 0.5s pacing, 10s pause after 6 requests.

### Options Collector (`collectors/ib_options.py`)

**`collect_options_snapshot()`** — Front 12 expirations, strikes within ±30% of underlying:
1. `reqSecDefOptParams` for chain metadata
2. `reqMktData(snapshot=True)` per option → IB-computed `modelGreeks` (IV, delta, gamma, vega, theta)
3. Store to `options_chains`
4. Compute vol surface per expiry → `vol_surface`

### News Collector (`collectors/news_collector.py`)

**`run_news_pipeline()`:**
1. **RSS feeds** (7 configured) — keyword-filtered (`feedparser`)
2. **GDELT real-time** — last 2 hours, max 75 articles
3. **Deduplicate** — URL MD5 hash + headline fuzzy match (60% threshold)
4. **Extract bodies** — BeautifulSoup on top 10 URLs
5. **Store raw** → `geopolitical_events` (category = `unclassified`)
6. **LLM classify** → update category, severity, supply_impact, coordinates

### Military Collector (`collectors/military_collector.py`)

**`run_military_pipeline()`:**
1. Extract from today's classified events via `military_agent` (LLM)
2. Fetch supplementary ACLED data (Middle East region, keyword-filtered)
3. Store → `military_events` + `military_deployments`
4. Generate military daily summary

### Production Tracker (`collectors/production_tracker.py`)

**`compute_daily_status()`:**
1. Per facility: aggregate active disruptions, check natural recovery
2. Country production: baseline − offline = current
3. Chokepoint status: severity-based reduction (Hormuz/Bab el-Mandeb/Suez)
4. Region supply summary: global offline % of 103 mbd demand
5. Tables: `facility_status`, `country_production`, `chokepoint_status`, `region_supply_summary`

---

## 3. Scheduler (`scheduler.py`)

APScheduler (BackgroundScheduler) with `US/Eastern` timezone. All jobs wrapped in timing/error logger — errors logged but **not re-raised**.

| Job | Schedule | What it runs |
|-----|----------|--------------|
| News | Every 2h at :00 | `run_news_pipeline()` |
| Military | Every 2h at :15 | `run_military_pipeline()` |
| Market (morning) | 10:00 M-F | `collect_futures_snapshot()` + `collect_options_snapshot()` |
| Market (midday) | 13:00 M-F | Same |
| Market (settlement) | 16:15 M-F | Same |
| EIA/FRED | 11:00 M-F | Incremental FRED + EIA backfill |
| AI Summaries | 08:00, 17:00 | Daily/military summaries |
| Scenarios | 17:30 M-F | Scenario analysis |
| Trade | 17:45 M-F | Trade recommendations |
| P&L | 18:00 M-F | P&L projection |

---

## 4. Database Schema (Key Tables)

| Table | Unique Key | Primary Data |
|-------|-----------|--------------|
| `futures_curves` | (date, symbol, contract_month) | settlement_price, volume |
| `options_chains` | (date, underlying, expiry_date, strike, option_type) | last_price, bid, ask, volume, OI, IV, delta, gamma, vega, theta, underlying_contract_month |
| `vol_surface` | (date, underlying, expiry_date) | atm_vol, skew_25d, smile_25d |
| `spreads` | (date, spread_type) | front_month, back_month, spread_value |
| `geopolitical_events` | append-only (dedup via URL hash) | timestamp, category, headline, summary, severity, supply_impact_mbd, lat/lon |
| `disruption_event` | append-only | facility_id, event_type, oil_impact_mbd, damage_pct, repair_estimate_days |
| `military_events` | append-only | date, side, event_type, loss_type, quantity |
| `facility_status` | (facility_id, date) | status, oil_offline_mbd, oil_online_mbd |
| `country_production` | (date, country) | baseline vs current oil/gas |
| `chokepoint_status` | (chokepoint, date) | status, reduction_pct, oil_transit_mbd |
| `backfill_status` | (source) | status, last_backfilled_date, total_records |

---

## 5. Configuration (`config.py`)

| Setting | Value | Purpose |
|---------|-------|---------|
| `FUTURES_SYMBOLS` | `["CL", "COIL"]` | WTI + Brent |
| `FUTURES_EXCHANGE` | `{"CL": "NYMEX", "COIL": "IPE"}` | Exchange mapping |
| `FUTURES_MONTHS_AHEAD` | 24 | Futures curve depth |
| `OPTIONS_EXPIRIES_AHEAD` | 12 | Option chain depth |
| `WAR_START_DATE` | `"2026-02-28"` | All backfill reference |
| `TWS_HOST/PORT/CLIENT_ID` | `127.0.0.1 / 7496 / 1` | IB connection |
| API keys | env vars | FRED, EIA, NewsAPI, Bing, ACLED, Claude, OpenAI |

---

## 6. Rate Limiting & Pacing

| Source | Limit | Implementation |
|--------|-------|----------------|
| IB Historical (futures) | ~60 req/10min | Batch 6, wait 65s |
| IB Historical (options) | 50 simultaneous | 45 concurrent async, 2s wave pause |
| IB Market Data | — | 0.3-1s between requests |
| GDELT | 15s minimum | Exponential backoff: 15/20/40/80/160/320s |
| NewsAPI | — | Standard rate limits |
| FRED/EIA | — | No documented limits |

---

## 7. Data Flow Diagram

```
STARTUP (main.py)
  │
  ├─ init_db()
  │
  ├─ BackfillManager.run_incremental()
  │    ├─ fred_backfill()  ─────────── FRED API ──────► futures_curves
  │    ├─ yahoo_backfill() ─────────── Yahoo Finance ─► futures_curves (+ volume)
  │    ├─ eia_backfill()  ──────────── EIA API ───────► (not persisted)
  │    ├─ gdelt_backfill() ─────────── GDELT + NewsAPI ► geopolitical_events
  │    │                                                ► disruption_event
  │    │                                                ► military_events
  │    ├─ ib_backfill()  ──────────── TWS daily bars ─► futures_curves
  │    ├─ ib_options_backfill() ───── TWS hourly bars ► options_chains
  │    │                              Black-76 Greeks   ► vol_surface
  │    │                              Live snapshots    ► bid/ask/OI/volume
  │    └─ production_backfill() ──── Internal ────────► facility_status
  │                                                    ► country_production
  │                                                    ► chokepoint_status
  │
  ├─ recompute_greeks()  ──────────── Offline IV fill ► options_chains
  ├─ compute_daily_status() ───────── Production ─────► region_supply_summary
  │
  ├─ start_scheduler()
  │    ├─ 2h:   news + military collectors
  │    ├─ 3×/d: futures + options snapshots
  │    ├─ 1×/d: FRED/EIA incremental
  │    └─ 1×/d: summaries + scenarios + trades + P&L
  │
  └─ start_app()  ────────────────── Dash UI (port 8050)
```
