# LLM Call Inventory

All calls use **Claude Sonnet 4.6** (`claude-sonnet-4-20250514`) via `agents/llm_client.py` singleton.

## Call Sites

| # | File | Function | LLM Method | Purpose | When |
|---|------|----------|------------|---------|------|
| 1 | `agents/geopolitical_agent.py:204` | `classify_batch()` | `simple_prompt` | **Batch classification + facility disruption extraction** (unified) | News pipeline, GDELT backfill |
| 2 | `agents/geopolitical_agent.py:141` | `classify_single_article()` | `simple_prompt` | Single article classification (fallback) | Fallback when batch fails |
| 3 | `agents/infrastructure_agent.py:141` | `extract_disruption_from_event()` | `simple_prompt` | Facility disruption extraction (legacy) | Production backfill only |
| 4 | `agents/military_agent.py:80` | `extract_military_data()` | `simple_prompt` | Extract military events & deployments from articles | News pipeline, backfill |
| 5 | `analysis/summarizer.py:99` | `generate_daily_summaries()` | `simple_prompt` | Daily geopolitical summary per category | Scheduler (08:00, 17:00), backfill |
| 6 | `analysis/summarizer.py:210` | `generate_military_daily_summary()` | `simple_prompt` | Daily military summary per side (Iran / Opposing) | Scheduler, backfill |
| 7 | `agents/scenario_agent.py:266` | `run_scenario_assessment()` | `agent_loop` | 6-scenario probability assessment with tool-use | Scheduler (17:30), on-demand |
| 8 | `agents/trading_agent.py:286` | `run_trading_agent()` | `agent_loop` | Options trade recommendations with tool-use | Scheduler, on-demand from UI |

## Details

### 1. classify_batch — Unified Classification + Disruption Extraction

- **System prompt:** `UNIFIED_BATCH_SYSTEM`
- **Input:** Up to 10 articles `{id, headline, summary}` + facility registry JSON (52 facilities)
- **Output:** JSON array with classification fields (`category`, `severity`, `supply_impact_mbd`, `lat/lon`, `location_name`) AND optional `disruption` object (`facility_match`, `event_type`, `oil_impact_mbd`, `gas_impact_bcfd`, `damage_pct`, `repair_estimate_days`, `cause`, `confidence`)
- **Note:** This consolidated call replaced what was previously 2 separate calls (classification + extraction per article)

### 2. classify_single_article — Single Article Classification

- **System prompt:** `CLASSIFICATION_SYSTEM`
- **Input:** headline, summary (≤1000 chars), source_url, timestamp
- **Output:** `{category, severity, supply_impact_mbd, latitude, longitude, location_name}`
- **Note:** No disruption extraction; used as fallback when batch call fails

### 3. extract_disruption_from_event — Legacy Disruption Extraction

- **System prompt:** `EXTRACTION_SYSTEM` + `EXTRACTION_PROMPT` template
- **Input:** Single event from DB (headline, summary ≤2000 chars, location, severity) + facility registry JSON
- **Output:** `{facility_match, event_type, oil_impact_mbd, gas_impact_bcfd, damage_pct, repair_estimate_days, cause, confidence}`
- **Note:** Only called from `backfill/production_backfill.py` for events classified before the unified approach. Not in normal pipeline or scheduler.

### 4. extract_military_data — Military Event Extraction

- **System prompt:** `MILITARY_SYSTEM`
- **Input:** Batch of military articles `[{id, headline, summary, lat, lon, location_name}]`
- **Output:** `[{id, headline, events: [{side, event_type, loss_type, quantity, unit_name, equipment, lat, lon}], deployments: [{...}]}]`

### 5. generate_daily_summaries — Geopolitical Daily Summaries

- **System prompt:** `GEO_SUMMARY_SYSTEM`
- **Input:** All classified events for a date, grouped by category (5 categories)
- **Output:** `{summary_text, severity_avg, total_supply_impact_mbd}` per category
- **Note:** Makes up to 5 calls per day (one per category with events)

### 6. generate_military_daily_summary — Military Daily Summaries

- **System prompt:** `MILITARY_SUMMARY_SYSTEM`
- **Input:** Military events + deployments for a date, per side
- **Output:** `{summary_text, escalation_score, total_personnel_losses, total_aircraft_losses, ...}`
- **Note:** Makes up to 2 calls per day (one per side with activity)

### 7. run_scenario_assessment — Scenario Probability Engine

- **System prompt:** `SCENARIO_SYSTEM`
- **Tools:** `get_latest_summaries`, `get_military_summary`, `get_latest_futures`, `get_latest_vol_metrics`, `get_previous_probabilities`
- **Input:** target_date; agent fetches data via tools
- **Output:** `{scenarios: {name: {probability, reasoning}}, overall_assessment, key_drivers}`
- **Scenarios:** Super Spike, Major Disruption, Moderate Escalation, Current State, De-escalation, Resolution

### 8. run_trading_agent — Trade Recommendation Engine

- **System prompt:** `TRADING_SYSTEM`
- **Tools:** `get_scenario_edges`, `get_options_chain`, `price_option`, `compute_trade_ev`
- **Input:** target_date, scenario probability edges (AI vs market implied)
- **Output:** Ranked trades `[{rank, underlying, structure, legs, entry_cost, max_loss, max_profit, expected_value, payoff_ratio, reasoning}]`

## LLM Client

- **File:** `agents/llm_client.py`
- **Singleton:** `get_llm_client()` returns shared `LLMClient` instance
- **Methods:**
  - `simple_prompt(system, user_prompt)` → single-turn, returns text
  - `agent_loop(system, user_prompt, tools, tool_handlers, max_iterations)` → iterative tool-use loop
  - `chat(system, messages, tools, max_tokens)` → raw Anthropic API call
- **Config:** `CLAUDE_KEY` env var, `CLAUDE_MAX_TOKENS` from config

## Normal Pipeline Call Flow (per news cycle)

```
news_collector.run_pipeline()
  → classify_events() → classify_batch() ×N        # Call #1 (unified)
  → extract_military_data()                         # Call #4
scheduler (daily)
  → generate_daily_summaries()                      # Call #5 (×5 categories)
  → generate_military_daily_summary()               # Call #6 (×2 sides)
  → run_scenario_assessment()                       # Call #7
  → run_trading_agent()                             # Call #8
```
