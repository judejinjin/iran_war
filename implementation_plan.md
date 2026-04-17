# Implementation Plan: Oil Super Spike Agentic Investment Analyzer

> This document breaks down the 7 phases from `project.md` into granular, file-by-file implementation tasks with dependencies, testing criteria, and execution order.

---

## Phase 1: Foundation (Week 1–2)

### 1.1 Environment Setup

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 1.1.1 | Create Conda environment | `environment.yml` | Anaconda installed | `conda activate oil && python --version` → 3.12 |
| 1.1.2 | Create `requirements.txt` with all packages from project.md §8 | `requirements.txt` | 1.1.1 | `pip install -r requirements.txt` completes without errors |
| 1.1.3 | Create `environment.yml` as Conda env spec (references `requirements.txt`) | `environment.yml` | 1.1.1 | `conda env create -f environment.yml` recreates env from scratch |

**environment.yml template:**
```yaml
name: oil
channels:
  - defaults
  - conda-forge
dependencies:
  - python=3.12
  - pip
  - pip:
    - -r requirements.txt
```

### 1.2 Configuration & Project Scaffold

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 1.2.1 | Create `config.py` — all configurable constants (DB path, IB host/port, API URLs, schedule times, WAR_START_DATE, search keywords, category lists) | `config.py` | 1.1.2 | `python -c "from config import *; print(WAR_START_DATE)"` |
| 1.2.2 | Verify `.env` has EIA_API_KEY, FRED_API_KEY, CLAUDE_KEY, TWS_HOST, TWS_PORT, TWS_CLIENT_ID | `.env` | — | Already exists, already tested |
| 1.2.3 | Create all `__init__.py` files and directory structure | `collectors/__init__.py`, `analysis/__init__.py`, `agents/__init__.py`, `ui/__init__.py`, `ui/layouts/__init__.py`, `ui/callbacks/__init__.py`, `ui/components/__init__.py`, `backfill/__init__.py`, `db/__init__.py` | — | All directories exist |
| 1.2.4 | Create `main.py` entry point (stub) — loads config, checks backfill, starts scheduler, launches Dash | `main.py` | 1.2.1 | `python main.py --help` runs without crash |

### 1.3 Database Layer

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 1.3.1 | Write `db/schema.sql` — all CREATE TABLE statements from project.md (geopolitical_events, daily_summaries, military_events, military_deployments, military_daily_summary, futures_curves, spreads, options_chains, vol_surface, scenario_probabilities, agent_analyses, positions, pnl_projections, backfill_status) | `db/schema.sql` | — | Valid SQL syntax |
| 1.3.2 | Write `db/database.py` — SQLAlchemy engine creation with WAL mode, session factory, ORM models for all 14 tables | `db/database.py` | 1.3.1, 1.2.1 | `python -c "from db.database import init_db; init_db()"` creates `db/oil_data.db` with all tables |
| 1.3.3 | Add Alembic migration scaffolding | `alembic.ini`, `alembic/` | 1.3.2 | `alembic current` shows head |

**Implementation notes for `db/database.py`:**
- Engine: `create_engine("sqlite:///db/oil_data.db", connect_args={"timeout": 30})`
- Enable WAL: `@event.listens_for(engine, "connect")` → `cursor.execute("PRAGMA journal_mode=WAL")`
- `init_db()` function: creates engine, runs `schema.sql` if tables don't exist
- One `SessionLocal = sessionmaker(bind=engine)` for scheduler writes
- One `get_readonly_session()` for UI reads (connect with `?mode=ro`)
- All table models as SQLAlchemy declarative classes

### 1.4 IB TWS Connection Manager

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 1.4.1 | Write IB connection manager — connect/disconnect, reconnect logic, connection health check | `collectors/ib_connection.py` | 1.2.1 | Connect to TWS on 7496, print account info, disconnect |
| 1.4.2 | Write futures data collector — request CL + COIL front 24 months, parse contract details, store in `futures_curves` and `spreads` tables | `collectors/ib_futures.py` | 1.4.1, 1.3.2 | Run collector, verify futures_curves table has rows for today |
| 1.4.3 | Write options data collector — request CL + COIL options chains (front 6 expiries), compute Greeks via Black-76, store in `options_chains` and `vol_surface` | `collectors/ib_options.py` | 1.4.1, 1.3.2 | Run collector, verify options_chains table has rows |

**Implementation notes for `collectors/ib_connection.py`:**
```python
from ib_insync import IB, util
import os

class IBConnection:
    def __init__(self):
        self.ib = IB()
        self.host = os.environ.get("TWS_HOST", "127.0.0.1")
        self.port = int(os.environ.get("TWS_PORT", "7496"))
        self.client_id = int(os.environ.get("TWS_CLIENT_ID", "1"))

    def connect(self):
        if not self.ib.isConnected():
            self.ib.connect(self.host, self.port, clientId=self.client_id, readonly=True)
        return self.ib

    def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()
```

### 1.5 Historical Backfill: Prices

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 1.5.1 | Write backfill manager — checks `backfill_status` table, orchestrates steps, resumes from interruption | `backfill/backfill_manager.py` | 1.3.2 | Call manager on empty DB → all sources marked `pending` |
| 1.5.2 | Write FRED backfill — fetch DCOILWTICO + DCOILBRENTEU from WAR_START_DATE to today, store in `futures_curves` | `backfill/fred_backfill.py` | 1.5.1 | Run → futures_curves has daily WTI + Brent from war start |
| 1.5.3 | Write Yahoo Finance backfill — fetch CL=F daily OHLCV, store as cross-check | `backfill/yahoo_backfill.py` | 1.5.1 | Run → data matches FRED within ±$1 tolerance |
| 1.5.4 | Write IB historical futures backfill — `reqHistoricalData()` for front 12 months, batch 6 contracts with 1-min pacing | `backfill/ib_backfill.py` | 1.4.1, 1.5.1 | Run → futures_curves has multi-month term structure for each historical day |
| 1.5.5 | Write EIA backfill — weekly petroleum status, monthly production | `backfill/eia_backfill.py` | 1.5.1 | Run → EIA data in DB from war start |

**Implementation notes for `backfill/backfill_manager.py`:**
```python
class BackfillManager:
    def __init__(self, session):
        self.session = session
        self.steps = [
            ("fred", FREDBackfill),
            ("yahoo", YahooBackfill),
            ("ib_futures", IBFuturesBackfill),
            ("eia", EIABackfill),
            ("gdelt", GDELTBackfill),       # Phase 2
            ("scenarios", ScenarioBackfill),  # Phase 4
        ]

    def needs_backfill(self) -> bool:
        """Check if any source is not 'complete'."""

    def run(self):
        """For each step not yet complete, instantiate and run."""
        for source, backfill_cls in self.steps:
            status = self.get_status(source)
            if status != "complete":
                self.update_status(source, "in_progress")
                try:
                    backfill_cls(self.session).run()
                    self.update_status(source, "complete")
                except Exception as e:
                    self.update_status(source, "pending", error=str(e))
                    raise
```

### 1.6 Basic Dash App with Futures Visualization

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 1.6.1 | Create Dash app shell — dark theme, tab navigation (7 tabs, placeholder content for tabs 1-2, 4-7) | `ui/app.py` | 1.1.2 | `python ui/app.py` → browser shows app with tabs |
| 1.6.2 | Create Futures tab layout — curve chart, spread chart, metrics panel | `ui/layouts/futures.py` | 1.6.1, 1.3.2 | Futures tab renders with chart placeholders |
| 1.6.3 | Create Futures tab callbacks — query DB for curves + spreads, render Plotly charts, date selector triggers re-render | `ui/callbacks/futures_cb.py` | 1.6.2, 1.4.2 | Select date → curve chart updates, spread chart updates |
| 1.6.4 | Wire `main.py` — on startup: init_db → backfill check → start APScheduler stub → launch Dash | `main.py` | 1.6.1, 1.5.1 | `python main.py` → backfill runs if needed → app starts on localhost:8050 |

### Phase 1 Completion Criteria
- [ ] Conda `oil` env with all deps installed
- [ ] SQLite DB with all 14 tables created
- [ ] IB TWS connects on port 7496 and fetches live CL/COIL futures + options
- [ ] Historical prices backfilled from WAR_START_DATE (FRED, Yahoo, IB, EIA)
- [ ] Dash app runs with Futures tab showing real curve data
- [ ] `main.py` orchestrates startup: DB init → backfill → app launch

---

## Phase 2: News & Geopolitical Intelligence (Week 2–3)

### 2.1 LLM Client

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 2.1.1 | Write Anthropic SDK wrapper — Claude Sonnet 4.6 client with tool-use loop, retry logic, token tracking, fallback to OpenAI/OpenRouter if Anthropic fails | `agents/llm_client.py` | 1.1.2 | Call with test prompt → Claude responds |

**Implementation notes for `agents/llm_client.py`:**
```python
import anthropic, os

class LLMClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["CLAUDE_KEY"])
        self.model = "claude-sonnet-4-20250514"

    def chat(self, system: str, messages: list, tools: list = None, max_tokens: int = 4096):
        """Single call, returns response."""

    def agent_loop(self, system: str, user_prompt: str, tools: list, tool_handlers: dict, max_iterations: int = 10):
        """Full tool-use loop: call → check for tool_use → execute → return results → repeat until text response."""
```

### 2.2 News Collection Pipeline

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 2.2.1 | Write RSS feed fetcher — parse Google News, Reuters, OilPrice, Al Jazeera, BBC RSS feeds for Iran war keywords | `collectors/news_collector.py` (RSS section) | 1.1.2 | Run → returns list of article dicts (headline, url, date, source) |
| 2.2.2 | Write GDELT API fetcher — query DOC 2.0 API for keyword matches, parse JSON response | `collectors/news_collector.py` (GDELT section) | 1.1.2 | Run → returns GDELT articles with metadata |
| 2.2.3 | Write article body extractor — BeautifulSoup scraper for article text from URLs | `collectors/news_collector.py` (scraper section) | 1.1.2 | Given URL → returns article body text |
| 2.2.4 | Write deduplication engine — fuzzy headline matching (thefuzz, Jaccard > 0.6), URL dedup | `collectors/news_collector.py` (dedup section) | 1.1.2 | Given 10 articles with 3 duplicates → returns 7 unique |
| 2.2.5 | Write fallback fetchers — NewsAPI, Bing News (only called if primary < 5 articles) | `collectors/news_collector.py` (fallback section) | 1.1.2 | With API keys → returns supplementary articles |
| 2.2.6 | Integrate full news pipeline: fetch all → dedup → store raw in `geopolitical_events` | `collectors/news_collector.py` (orchestration) | 2.2.1–2.2.5, 1.3.2 | Run pipeline → events in DB |

### 2.3 AI Classification & Summarization

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 2.3.1 | Write geopolitical agent — classifies each article into 5 categories, extracts severity (1–10), estimates supply impact (mbd), geolocates events (lat/lng) | `agents/geopolitical_agent.py` | 2.1.1 | Given article → returns classification dict |
| 2.3.2 | Write summarizer — generates daily summary per category using today's classified events | `analysis/summarizer.py` | 2.3.1 | Given day's events → produces 5 category summaries stored in `daily_summaries` |
| 2.3.3 | Integrate classification into news pipeline — after store, classify each new article, update geopolitical_events with category/severity/impact/coords | `collectors/news_collector.py` (classification step) | 2.3.1 | Run pipeline → events in DB have categories + severities |

### 2.4 Military Intelligence

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 2.4.1 | Write military collector — filters military_operations from news pipeline, fetches ACLED API data if key available | `collectors/military_collector.py` | 2.2.6 | Run → military events available |
| 2.4.2 | Write military agent — extracts structured data (side, loss type, quantity, unit name, equipment, deployment status, coords) from military news | `agents/military_agent.py` | 2.1.1 | Given military article → returns structured military event |
| 2.4.3 | Write military daily summary generator — aggregates day's military events into per-side daily summary (losses, deployment counts, escalation score) | `analysis/summarizer.py` (military section) | 2.4.2 | Run → military_daily_summary rows for today |
| 2.4.4 | Integrate military pipeline — after news classification, extract military data, store in military_events + military_deployments + military_daily_summary | `collectors/military_collector.py` (orchestration) | 2.4.1–2.4.3, 1.3.2 | Full pipeline → all military tables populated |

### 2.5 GDELT Historical Backfill

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 2.5.1 | Write GDELT backfill — iterate day-by-day from WAR_START_DATE, fetch articles, classify, extract military data, generate retroactive summaries | `backfill/gdelt_backfill.py` | 2.2.2, 2.3.1, 2.4.2, 1.5.1 | Run → geopolitical_events + daily_summaries + military tables populated from war start |
| 2.5.2 | Register GDELT backfill in backfill_manager | `backfill/backfill_manager.py` | 2.5.1 | Backfill manager recognizes "gdelt" source |

### 2.6 Geopolitical & Military UI

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 2.6.1 | Write reusable map component — `dash-leaflet` map centered on Middle East, accepts markers as props (lat, lng, category, severity, popup text), supports date-range animation | `ui/components/map_view.py` | 1.6.1 | Render map with sample markers |
| 2.6.2 | Write reusable timeline component — Plotly timeline/Gantt with color-coded events, drill-down on click | `ui/components/timeline.py` | 1.6.1 | Render timeline with sample events |
| 2.6.3 | Write reusable summary card component — category name, severity badge, summary text, supply impact | `ui/components/summary_card.py` | 1.6.1 | Render card with sample data |
| 2.6.4 | Create Geopolitical tab layout — 5 summary cards + event map + timeline, date selector, category filter, severity filter | `ui/layouts/geopolitical.py` | 2.6.1–2.6.3, 1.3.2 | Tab renders with real data |
| 2.6.5 | Create Geopolitical tab callbacks — query DB for events/summaries, filter by date/category/severity, update map markers + timeline + cards | `ui/callbacks/geopolitical_cb.py` | 2.6.4 | Change filters → UI updates |
| 2.6.6 | Create Military tab layout — two-column losses dashboard, theater map, losses timeline, deployment timeline, escalation chart | `ui/layouts/military.py` | 2.6.1, 1.3.2 | Tab renders with real military data |
| 2.6.7 | Create Military tab callbacks — query military tables, update all charts and maps | `ui/callbacks/military_cb.py` | 2.6.6 | Date range change → all military views update |

### Phase 2 Completion Criteria
- [ ] News pipeline fetches from 6 RSS feeds + GDELT, deduplicates, classifies into 5 categories
- [ ] Claude agent classifies articles with severity, supply impact, geolocation
- [ ] Military agent extracts structured data (losses, deployments, equipment)
- [ ] Daily summaries generated for all 5 categories + military daily summary
- [ ] GDELT historical backfill populates all news/military data from war start
- [ ] Geopolitical tab shows summary cards, event map, timeline with real data
- [ ] Military tab shows losses, deployments, theater map, escalation timeline

---

## Phase 3: Options Data & Analytics (Week 3–4)

### 3.1 Options Data Collection

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 3.1.1 | Enhance `collectors/ib_options.py` — full options chain fetch for CL + COIL front 6 expiries, compute IV, store in `options_chains` | `collectors/ib_options.py` | 1.4.3 | Run → options_chains has rows for all strikes/expiries |
| 3.1.2 | Write Black-76 Greeks engine — delta, gamma, vega, theta for each option; compute ATM vol, 25-delta skew, butterfly | `analysis/options_analysis.py` | 3.1.1 | Given chain → compute Greeks that match IB within ±0.01 |
| 3.1.3 | Write vol surface aggregator — compute ATM vol, 25-delta risk reversal, 25-delta butterfly per expiry, store in `vol_surface` | `analysis/options_analysis.py` (vol surface section) | 3.1.2 | Run → vol_surface table populated for today |

### 3.2 Options UI

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 3.2.1 | Create Options tab layout — vol surface heatmap, vol smile chart, skew tracker, OI profile, daily change table | `ui/layouts/options.py` | 3.1.3, 1.6.1 | Tab renders with chart containers |
| 3.2.2 | Create Options tab callbacks — query options_chains + vol_surface, render heatmaps and line charts, expiry selector, date selector | `ui/callbacks/options_cb.py` | 3.2.1 | Select expiry → smile chart updates, heatmap updates |

### Phase 3 Completion Criteria
- [ ] Options chains fetched from IB for CL + COIL (front 6 expiries)
- [ ] Greeks computed via Black-76, vol surface metrics stored
- [ ] Options tab shows vol surface heatmap, smile chart, skew tracker, OI profile
- [ ] Historical data shows vol evolution over time

---

## Phase 4: Scenario Engine (Week 4–5)

### 4.1 Scenario Framework

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 4.1.1 | Define scenario enum/config — 6 scenarios with name, Brent range, description (from project.md §4.5) | `config.py` (add SCENARIOS section) | — | Import works |
| 4.1.2 | Write scenario agent — Claude tool-use agent that ingests daily geopolitical summaries, military escalation scores, futures curve shape, options skew, and outputs probability distribution across 6 scenarios with reasoning | `agents/scenario_agent.py` | 2.1.1, 2.3.2, 2.4.3 | Call agent with today's data → returns 6 probabilities summing to ~1.0 with reasoning text |

**Implementation notes for `agents/scenario_agent.py`:**

Tools the scenario agent needs access to:
- `get_latest_summaries()` — today's 5 category summaries + severity scores
- `get_military_summary()` — today's military daily summary + escalation score
- `get_latest_futures()` — current CL/COIL front-month prices + curve shape (contango/backwardation)
- `get_latest_vol_metrics()` — current ATM vol, skew, butterfly
- `get_previous_probabilities()` — yesterday's scenario probabilities (for continuity)

Agent system prompt should emphasize:
- Probabilities must sum to 1.0 (±0.01 tolerance)
- Each probability change from yesterday must be justified
- Supply impact estimates feed into scenario selection
- Military escalation score is a key input
- Output structured JSON: `{scenario_name: {probability, reasoning}}`

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 4.1.3 | Write scenario probability updater — calls scenario agent, validates output (probabilities sum to ~1.0), stores in `scenario_probabilities` | `analysis/scenarios.py` | 4.1.2 | Run → scenario_probabilities has 6 rows for today |

### 4.2 Retroactive Scenario Backfill

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 4.2.1 | Write scenario backfill — for each past week since WAR_START_DATE, run scenario agent on that week's historical data to produce weekly probability snapshots | `backfill/backfill_manager.py` (add scenarios step) | 4.1.3, 2.5.1 | Run → scenario_probabilities has weekly entries from war start |

### 4.3 Scenarios UI

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 4.3.1 | Create Scenarios tab layout — probability bar chart, probability timeline (stacked area), reasoning panel, expected value display | `ui/layouts/scenarios.py` | 4.1.3, 1.6.1 | Tab renders |
| 4.3.2 | Create Scenarios tab callbacks — query scenario_probabilities, compute expected Brent/WTI, render charts, click scenario → show reasoning | `ui/callbacks/scenarios_cb.py` | 4.3.1 | Date change → bars update, click → reasoning shown |

### Phase 4 Completion Criteria
- [ ] Scenario agent produces daily probabilities for 6 scenarios
- [ ] Probabilities sum to ~1.0, each has reasoning text
- [ ] Historical weekly probabilities backfilled from war start
- [ ] Scenarios tab shows probability bars, timeline, reasoning, expected values

---

## Phase 5: Agentic Mispricing Analysis (Week 5–6)

### 5.1 Market-Implied Distribution

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 5.1.1 | Implement Breeden-Litzenberger extraction — take call prices from options_chains, interpolate with cubic spline, compute second derivative to get risk-neutral PDF | `analysis/options_analysis.py` (add BL section) | 3.1.1 | Given chain → produces smooth probability density curve |
| 5.1.2 | Map market-implied PDF to scenario price ranges — integrate PDF over each scenario's Brent range to get market-implied probability per scenario | `analysis/mispricing.py` | 5.1.1, 4.1.1 | Returns 6 market-implied probabilities |

### 5.2 AI vs Market Comparison

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 5.2.1 | Compute edge per scenario — `edge = AI_prob - market_implied_prob` for each of 6 scenarios | `analysis/mispricing.py` (add edge section) | 5.1.2, 4.1.3 | Returns edge dict, positive = underpriced |
| 5.2.2 | Write trading agent — Claude agent that evaluates edges, recommends optimal strikes/expiries/structures (calls, call spreads, strangles, ratio spreads), computes expected value per trade | `agents/trading_agent.py` | 2.1.1, 5.2.1 | Call agent → returns ranked trade list with EV, max loss, payoff ratio |
| 5.2.3 | Write trade recommender orchestrator — runs daily after scenario update, calls mispricing analysis + trading agent, stores results in `agent_analyses` | `analysis/trade_recommender.py` | 5.2.2 | Run → agent_analyses has today's mispricing + trade recommendations |

**Implementation notes for `agents/trading_agent.py`:**

Tools the trading agent needs:
- `get_scenario_edges()` — AI vs market probability edges per scenario
- `get_options_chain(underlying, expiry)` — current chain for strike selection
- `price_option_black76(strike, expiry, vol, rate)` — reprice at scenario target
- `compute_expected_value(trade_legs, scenario_probs, scenario_prices)` — EV calculation
- `get_current_futures()` — current underlying prices for delta reference

Agent outputs structured JSON:
```json
[
  {
    "rank": 1,
    "underlying": "COIL",
    "structure": "call_spread",
    "legs": [{"strike": 120, "expiry": "2026-06", "type": "CALL", "side": "BUY"}, ...],
    "entry_cost": 2.50,
    "max_loss": 2.50,
    "expected_value": 8.75,
    "payoff_ratio": 3.5,
    "reasoning": "..."
  }
]
```

### 5.3 Analysis UI

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 5.3.1 | Create Analysis tab layout — mispricing heatmap (strike × expiry showing edge), trade recommendations panel, WTI vs Brent comparison, agent reasoning panel | `ui/layouts/analysis.py` | 5.2.3, 1.6.1 | Tab renders |
| 5.3.2 | Create Analysis tab callbacks — query agent_analyses, parse recommended_trades JSON, render heatmap + trade list + reasoning | `ui/callbacks/analysis_cb.py` | 5.3.1 | Shows today's recommendations, click trade → details expand |

### Phase 5 Completion Criteria
- [ ] Breeden-Litzenberger extracts market-implied distribution from options chain
- [ ] Edge computed: AI prob vs market-implied prob per scenario
- [ ] Trading agent recommends specific trades with EV, max loss, payoff ratio
- [ ] Analysis tab shows mispricing heatmap, ranked trades, agent reasoning

---

## Phase 6: Position Management & P&L (Week 6–7)

### 6.1 Position CRUD

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 6.1.1 | Write position CRUD helpers — add, edit, close, delete positions in `positions` table | `db/database.py` (add position helpers) | 1.3.2 | Add position → exists in DB, edit → updated, delete → gone |

### 6.2 P&L Projection Engine

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 6.2.1 | Write scenario P&L projector — for each open position × each scenario: reprice at scenario target price (futures: simple; options: Black-76 with adjusted vol), compute P&L, store in `pnl_projections` | `analysis/pnl_projector.py` | 6.1.1, 4.1.1, 3.1.2 | Given position + scenarios → pnl_projections rows |
| 6.2.2 | Write aggregate P&L calculator — sum per-position P&L per scenario, compute probability-weighted expected P&L | `analysis/pnl_projector.py` (aggregate section) | 6.2.1 | Returns {scenario: total_pnl, expected_pnl: weighted_sum} |

### 6.3 Portfolio UI

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 6.3.1 | Write payoff chart component — classic options payoff diagram at expiry with scenario price markers | `ui/components/payoff_chart.py` | 1.6.1 | Render payoff for sample position |
| 6.3.2 | Create Portfolio tab layout — position table (editable), add position form (dropdowns + inputs), scenario P&L matrix, aggregate P&L bar chart, payoff diagram | `ui/layouts/portfolio.py` | 6.1.1, 6.2.2, 6.3.1 | Tab renders with form + empty table |
| 6.3.3 | Create Portfolio tab callbacks — form submit → add position to DB, position table updates, P&L matrix re-computes, payoff chart updates | `ui/callbacks/portfolio_cb.py` | 6.3.2 | Add position → table updates, P&L matrix shows per-scenario projections |

### Phase 6 Completion Criteria
- [ ] Positions can be entered, edited, closed, deleted from UI
- [ ] P&L projected for each position across all 6 scenarios
- [ ] Aggregate portfolio P&L shown per scenario with probability weighting
- [ ] Payoff diagram renders correctly for options positions

---

## Phase 7: Integration & Polish (Week 7–8)

### 7.1 Full Scheduler Integration

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 7.1.1 | Write complete scheduler — APScheduler with all jobs from project.md §5.1: news (every 2h, 24/7), market data (3×/day at 10:00, 13:00, 16:15 ET), EIA/FRED (1×/day 11:00 ET), AI summaries (2×/day 08:00, 17:00 ET), scenario+analysis (1×/day 17:30 ET) | `scheduler.py` | All collectors + analysis modules | Scheduler starts, next run times displayed correctly |
| 7.1.2 | Add job execution logging — each job run logged with start time, duration, success/failure, record counts | `scheduler.py` (logging section) | 7.1.1 | Logs show job executions |

**Implementation notes for `scheduler.py`:**
```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

et = pytz.timezone("US/Eastern")
scheduler = BackgroundScheduler(timezone=et)

# News — every 2 hours, 24/7
scheduler.add_job(run_news_pipeline, CronTrigger(hour="*/2", minute=0, timezone=et), id="news")

# Market data — 3× daily on weekdays
for hour, minute, name in [(10, 0, "morning"), (13, 0, "midday"), (16, 15, "settlement")]:
    scheduler.add_job(run_market_data, CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri", timezone=et), id=f"market_{name}")

# EIA/FRED — once daily 11:00 ET weekdays
scheduler.add_job(run_eia_fred, CronTrigger(hour=11, minute=0, day_of_week="mon-fri", timezone=et), id="eia_fred")

# AI summaries — 08:00 and 17:00 ET
scheduler.add_job(run_ai_summary, CronTrigger(hour=8, minute=0, timezone=et), id="summary_morning")
scheduler.add_job(run_ai_summary, CronTrigger(hour=17, minute=0, timezone=et), id="summary_evening")

# Scenario + analysis — 17:30 ET weekdays
scheduler.add_job(run_scenario_analysis, CronTrigger(hour=17, minute=30, day_of_week="mon-fri", timezone=et), id="scenario")
```

### 7.2 Cross-Tab Linking & Navigation

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 7.2.1 | Add dcc.Store for shared state — selected date, selected scenario, selected underlying permeate across tabs | `ui/app.py` (add stores) | All tab callbacks | Change date on one tab → other tabs update |
| 7.2.2 | Scenario → Portfolio link — click scenario name → jump to Portfolio tab with that scenario highlighted in P&L matrix | `ui/callbacks/scenarios_cb.py`, `ui/callbacks/portfolio_cb.py` | 4.3.2, 6.3.3 | Click "Super Spike" → Portfolio tab opens, Super Spike column highlighted |

### 7.3 Backfill Resume & Error Handling

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 7.3.1 | Add resume logic to all backfill steps — read `last_backfilled_date` from `backfill_status`, continue from that date | All `backfill/*.py` files | 1.5.1 | Kill mid-backfill, restart → resumes from last checkpoint |
| 7.3.2 | Add exponential backoff retry to all API calls (IB, FRED, EIA, GDELT, RSS, Claude) | `collectors/*.py`, `agents/llm_client.py` | All collectors + agents | Simulate API failure → retries 3 times with exponential backoff |
| 7.3.3 | Add graceful degradation — if IB disconnects, show last-known data in UI with "stale" badge; if Claude API fails, skip analysis run and log warning | All relevant modules | All | Disconnect IB → UI shows stale badge, no crash |

### 7.4 Performance & Logging

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 7.4.1 | Add loguru structured logging throughout — all collectors, agents, scheduler, backfill, and app startup | All `.py` files | — | Log files created, structured JSON entries |
| 7.4.2 | Add query caching — cache expensive DB queries (full day's data) with TTL matching dashboard refresh (5 min) | `db/database.py` (add cache layer) | 1.3.2 | Same query within 5 min → cache hit, no DB query |
| 7.4.3 | Add lazy loading for historical views — default last 30 days, load more on scroll/date-range expansion | UI callback files | All tab callbacks | Timeline default is 30 days, expand → loads more |

### 7.5 Final `main.py` Integration

| # | Task | Files | Dependencies | Test |
|---|------|-------|-------------|------|
| 7.5.1 | Finalize `main.py` — complete startup flow: load .env → init_db → check backfill → start scheduler → launch Dash on 0.0.0.0:8050 | `main.py` | All modules | `python main.py` runs entire system end-to-end |

### Phase 7 Completion Criteria
- [ ] All 6 scheduled jobs run automatically at correct times
- [ ] Cross-tab navigation works (date sync, scenario → portfolio link)
- [ ] Backfill resumes from interruption
- [ ] API failures handled gracefully with retries and fallbacks
- [ ] Structured logging throughout
- [ ] UI loads in < 2 seconds

---

## File Implementation Order (Critical Path)

The dependency chain dictates this strict build order:

```
Phase 1 — Foundation
  1.  environment.yml / requirements.txt
  2.  config.py
  3.  .env (exists)
  4.  db/schema.sql
  5.  db/database.py
  6.  collectors/ib_connection.py
  7.  collectors/ib_futures.py
  8.  collectors/ib_options.py
  9.  backfill/backfill_manager.py
  10. backfill/fred_backfill.py
  11. backfill/yahoo_backfill.py
  12. backfill/ib_backfill.py
  13. backfill/eia_backfill.py
  14. ui/app.py
  15. ui/layouts/futures.py
  16. ui/callbacks/futures_cb.py
  17. main.py (v1: backfill + dash)

Phase 2 — News & Geopolitical
  18. agents/llm_client.py
  19. collectors/news_collector.py
  20. agents/geopolitical_agent.py
  21. analysis/summarizer.py
  22. collectors/military_collector.py
  23. agents/military_agent.py
  24. backfill/gdelt_backfill.py
  25. ui/components/map_view.py
  26. ui/components/timeline.py
  27. ui/components/summary_card.py
  28. ui/layouts/geopolitical.py
  29. ui/callbacks/geopolitical_cb.py
  30. ui/layouts/military.py
  31. ui/callbacks/military_cb.py

Phase 3 — Options Analytics
  32. analysis/options_analysis.py
  33. ui/layouts/options.py
  34. ui/callbacks/options_cb.py

Phase 4 — Scenarios
  35. agents/scenario_agent.py
  36. analysis/scenarios.py
  37. ui/layouts/scenarios.py
  38. ui/callbacks/scenarios_cb.py

Phase 5 — Mispricing
  39. analysis/mispricing.py
  40. agents/trading_agent.py
  41. analysis/trade_recommender.py
  42. ui/layouts/analysis.py
  43. ui/callbacks/analysis_cb.py

Phase 6 — Portfolio
  44. analysis/pnl_projector.py
  45. ui/components/payoff_chart.py
  46. ui/layouts/portfolio.py
  47. ui/callbacks/portfolio_cb.py

Phase 7 — Integration
  48. scheduler.py
  49. main.py (final: full startup flow)
```

**Total files to create**: ~49 (excluding `__init__.py` files and existing files)

---

## Testing Strategy

### Unit Tests (per module)

| Module | What to Test | Method |
|--------|-------------|--------|
| `db/database.py` | Table creation, CRUD, WAL mode, session isolation | pytest + temp SQLite |
| `collectors/ib_futures.py` | Contract resolution, curve parsing, DB insert | Mock IB connection |
| `collectors/news_collector.py` | RSS parsing, GDELT response parsing, dedup, fallback trigger | Fixture RSS XML + mock HTTP |
| `agents/llm_client.py` | Tool-use loop, retry logic, token tracking | Mock Anthropic API |
| `agents/geopolitical_agent.py` | Classification output schema, severity range, coordinates | Mock LLM |
| `analysis/options_analysis.py` | Black-76 pricing vs known values, Greeks signs, BL extraction | Pure math tests |
| `analysis/mispricing.py` | Edge calculation, scenario mapping | Fixture probabilities |
| `analysis/pnl_projector.py` | Futures P&L, option P&L, aggregate | Known positions + targets |

### Integration Tests

| Test | Validates |
|------|-----------|
| `test_backfill_pipeline` | Empty DB → backfill → all tables populated → no gaps |
| `test_news_to_summary` | Fetch → dedup → classify → summarize → DB round-trip |
| `test_scenario_daily_run` | Summaries + market data → scenario agent → probabilities stored |
| `test_mispricing_daily_run` | Options chain + scenarios → BL extraction → edge → trade recs |
| `test_full_dashboard_load` | Start app → all 7 tabs render → no Python errors in callback |

### Manual Validation Checklist

- [ ] TWS running → futures curve populates → chart renders in < 2 sec
- [ ] News pipeline returns ≥ 5 articles per 2-hour run
- [ ] Claude classification matches human judgment on 10 sample articles
- [ ] Scenario probabilities sum to 1.0 and shift meaningfully after major news
- [ ] Mispricing heatmap shows non-zero edges for tail scenarios
- [ ] Position entry → P&L matrix updates → payoff diagram correct
- [ ] Kill and restart → backfill resumes without re-downloading completed data
- [ ] Run overnight → morning summary available by 08:15 ET

---

## Risk Checkpoints

At each phase boundary, validate before proceeding:

| After Phase | Gate Check |
|-------------|-----------|
| 1 | IB data flows, DB schema stable, basic UI works |
| 2 | News pipeline reliable (≥ 5 articles/cycle), classifcation accurate, maps render |
| 3 | Options Greeks match IB within tolerance, vol surface looks reasonable |
| 4 | Scenario probabilities track news events (not random), reasoning is coherent |
| 5 | Market-implied distribution is smooth, edge calculations make financial sense |
| 6 | P&L projections match manual calculation for simple test positions |
| 7 | Full system runs unattended for 24 hours without crashing |
