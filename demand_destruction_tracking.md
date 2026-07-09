# Demand Destruction Tracking — Research Proposal

**Date:** May 10, 2026  
**Context:** Oil Super Spike Analyzer — addendum to Supply/Demand tab

---

## What "Demand Destruction" Means in Data

A sustained fall in petroleum consumption driven by price shock, recession, behavioral change, or policy. Measuring it requires either **actual consumption data** (lagged but accurate) or **high-frequency proxies** (fast but noisy). A robust signal layer uses both.

---

## Tier 1 — Actual Consumption Data
### Accuracy: ★★★★★ | Lag: ~5 days | Geography: US | Cost: Free

### EIA Weekly Petroleum Status Report
Published every Wednesday for the prior week. "Product supplied" = implied demand (refinery output + imports − exports − inventory change). **Already have EIA API key; existing `_fetch_eia_series()` works.**

| Series ID | Metric |
|---|---|
| `PET.WGFUPUS2.W` | US gasoline supplied (kbd) |
| `PET.WDIRPUS2.W` | US distillate / diesel supplied (kbd) |
| `PET.WKJUPUS2.W` | US jet fuel supplied (kbd) |
| `PET.WRPUPUS2.W` | US residual fuel supplied (kbd) |
| `PET.WCRRIUS2.W` | US refinery utilization % |

Refinery utilization < 85% is itself a demand destruction signal. All series IDs slot directly into the existing EIA backfill fetcher with zero new infrastructure.

### EIA Retail Pump Prices (price-elasticity companion)
`PET.EMM_EPMR_PTE_NUS_DPG.W` — when gasoline crosses ~$4.50/gal, demand falls measurably within 4–6 weeks. Plotting price vs. product supplied gives an elasticity curve usable in scenario analysis.

**Implementation:** Add new series IDs to `eia_backfill.py`; store in a new `demand_weekly` table; surface on a sub-tab of Supply/Demand.

---

## Tier 2 — High-Frequency Proxies
### Accuracy: ★★★★ | Lag: Daily | Geography: Global | Cost: Free

### OpenSky Network — Aviation Demand Index
Jet fuel is ~8% of global oil demand. Daily commercial flight counts are a clean, real-time proxy.

- **API:** `https://opensky-network.org/api/flights/all?begin=&end=` (no key required)
- Aggregate departure counts by day and normalize against a 2019 baseline → "Aviation Demand Index (0–100)"
- Granular enough to detect route cancellations from war escalation or recession
- Drops in trans-Pacific / trans-Atlantic routes signal Chinese / European demand weakness specifically

**Implementation:** New lightweight collector `collectors/aviation_collector.py`; scheduled daily.

### Carbon Monitor — Fuel Consumption by Sector
Daily CO₂ by sector (transport, industry, power) by country → directly implies fuel burn.

- **API:** `https://api.carbonmonitor.org/api/data` (free, ~5-day lag)
- Covers US, China, EU, India — the four largest demand blocs
- Transport CO₂ → gasoline + jet fuel + diesel proxy
- Industry CO₂ → fuel oil + gas proxy
- Enables cross-country demand comparison that EIA weekly cannot provide

**Implementation:** New `collectors/carbon_monitor_collector.py`; backfill from 2020.

---

## Tier 3 — Economic Leading Indicators
### Accuracy: ★★★ | Lag: 3–5 weeks | Geography: US/Global | Cost: Free

Already have FRED API key and `fred_backfill.py`. These series add a forward-looking economic layer — PMI below 48 reliably predicts diesel/industrial fuel demand contraction within ~2 months.

| FRED Series | Metric | Lead Time |
|---|---|---|
| `ISM/MAN_PMI` | US manufacturing PMI | 4–6 weeks |
| `INDPRO` | US industrial production index | 3–4 weeks |
| `DGORDER` | Durable goods orders | 4 weeks |
| `JTSJOL` | Job openings (labor market proxy) | 5 weeks |
| `GEPUPPP` | Global Economic Policy Uncertainty | ~Real-time |

**Implementation:** Extend `fred_backfill.py` with these series IDs; composite into a "Macro Demand Pressure Score" for the UI.

---

## Tier 4 — News NLP Sentiment (Demand Destruction Signal)
### Accuracy: ★★ | Lag: 15 minutes | Geography: Global | Cost: Free (GDELT)

The least accurate but fastest channel — purely directional with wide uncertainty. Hooks directly into the existing GDELT pipeline and LLM agent.

**Mechanism:**
1. Extend `GDELT_QUERY` in `config.py` with demand-side terms:
   ```
   "demand destruction" OR "fuel demand" OR "airline cuts capacity" OR
   "factory shutdown" OR "recession" OR "fuel switching" OR "EV adoption"
   OR "driving less" OR "oil demand falls"
   ```
2. Feed article clusters to the existing LLM agent; score each −2 (severe destruction) to +2 (demand recovery)
3. Compute a 7-day rolling average → **Demand Sentiment Index**
4. Surface on dashboard alongside price chart

**Implementation:** Keyword additions to `config.py`; new scoring function in `agents/geopolitical_agent.py` or a new `agents/demand_agent.py`; minimal new code.

---

## Source Coverage Matrix

| Source | Accuracy | Lag | Geography | API Key | Already Wired |
|---|---|---|---|---|---|
| EIA weekly product supplied | ★★★★★ | 5 days | US | EIA key ✓ | Partial — new series IDs |
| EIA retail pump prices | ★★★★ | 5 days | US regional | EIA key ✓ | No |
| OpenSky flight counts | ★★★★ | Daily | Global | None needed | No |
| Carbon Monitor | ★★★ | 5 days | US/CN/EU/IN | None needed | No |
| FRED PMI / INDPRO | ★★★ | 3–5 weeks | US / global | FRED key ✓ | Partial |
| GDELT news NLP | ★★ | 15 min | Global | None needed | Yes — extend keywords |
| IEA Oil Market Report | ★★★★★ | 6 weeks | Global | Scrape | No |
| China customs crude imports | ★★★★ | 6 weeks | China | Scrape | No |

---

## Phased Implementation Plan

### Phase 1 — EIA Weekly Demand Series *(1–2 days, highest ROI)*
- Add 5 product-supplied series + pump prices to `eia_backfill.py`
- New `demand_weekly` DB table
- Sub-chart on Supply/Demand tab: US product demand waterfall by fuel type, YoY % change, refinery utilization gauge

### Phase 2 — FRED Leading Indicators *(1 day)*
- Extend `fred_backfill.py` with PMI, INDPRO, DGORDER
- Composite "Macro Demand Pressure" score (0–100)
- Display as KPI card + trend line on Supply/Demand tab

### Phase 3 — OpenSky Aviation Index *(2–3 days)*
- New `collectors/aviation_collector.py`
- Daily scheduler job
- Aviation demand index normalized to 2019 = 100
- Overlay on trend chart as secondary axis

### Phase 4 — GDELT Demand Sentiment *(1 day)*
- Extend `GDELT_QUERY` + `NEWS_KEYWORDS` in `config.py`
- New scoring pass in LLM agent pipeline
- Demand Sentiment Index widget on dashboard

### Phase 5 — Carbon Monitor *(2–3 days, optional)*
- New collector + backfill from 2020
- Enables non-US demand (China, India, EU) — fills the biggest gap in Phase 1

---

## Composite "Demand Destruction Score"

Phases 1–4 together enable a weighted composite:

$$
\text{DDS} = 0.40 \times \text{EIA signal} + 0.25 \times \text{Macro score} + 0.20 \times \text{Aviation index} + 0.15 \times \text{News sentiment}
$$

Score range: −100 (severe destruction) to +100 (demand recovery). Actionable threshold: DDS < −30 warrants a bearish demand adjustment to scenario price targets.

---

## Estimating Demand Destruction from Historical Data

Historical analysis lets us calibrate *how much* demand falls per dollar of price shock, and for how long — converting a qualitative narrative into a quantifiable model usable in scenario pricing.

### Historical Episodes to Anchor the Model

Five episodes provide clean before/after observations across different shock types:

| Episode | Period | Brent Peak→Trough | Global Demand Change | Recovery Time |
|---|---|---|---|---|
| 2008 Financial Crisis | Jul 2008 – Feb 2009 | $147 → $35 | −1.6 Mb/d (−1.8%) | ~18 months |
| 2014–2016 Supply Glut | Jun 2014 – Jan 2016 | $115 → $28 | +0.4 Mb/d (demand held) | Minimal disruption |
| COVID-19 Lockdowns | Jan 2020 – Apr 2020 | $70 → $19 | −9.0 Mb/d (−9%) | 24+ months |
| 2022 Ukraine War Spike | Feb 2022 – Jun 2022 | $79 → $127 | −0.3 Mb/d (mild) | 6 months |
| 2023 Recession Fears | Nov 2022 – Mar 2023 | $100 → $73 | −0.5 Mb/d estimated | 9 months |

**Key insight:** Supply-driven price spikes (2022) destroy less demand than financial-crisis price collapses (2008), because the mechanism is different — affordability vs. activity collapse.

---

### Data Sources for Historical Calibration

#### IEA Oil Market Report (OMR)
The IEA publishes monthly global demand estimates, revisions, and year-on-year changes in the OMR. Historical OMR data tables (2000–present) are available via:
- **PDF scrape:** `https://www.iea.org/reports/oil-market-report-{month}-{year}` — tables embedded as PDFs
- **IEA Data Services API** (paid tier): `https://api.iea.org/stats/` — returns monthly demand by country/product
- **Free alternative:** IEA publishes annual "World Energy Balances" CSVs at `https://www.iea.org/data-and-statistics/data-product/world-energy-balances` — covers 1971–present, downloadable as bulk Excel

For this project the most practical path is the **free annual Excel** for calibration (already covers the 5 episodes above) plus the monthly OMR PDF scrape for the most recent 12 months of revisions.

#### FRED — Brent/WTI Daily Price (already wired)
`DCOILBRENTEU` and `DCOILWTICO` are already in `fred_backfill.py`. These provide the price series to align against IEA demand observations.

#### EIA International Energy Statistics
The `supply_demand_backfill.py` already pulls annual EIA international demand. This is the same underlying source the IEA uses for non-OECD countries — so the two are cross-validating rather than independent.

---

### Method 1 — Price Elasticity of Demand (OLS Regression)

The simplest calibrated model. Regress log-demand change against log-price change for each historical episode to estimate the **short-run price elasticity of demand (ε)**.

$$
\ln\left(\frac{D_t}{D_{t-1}}\right) = \alpha + \varepsilon \cdot \ln\left(\frac{P_t}{P_{t-1}}\right) + \beta \cdot \text{GDP\_growth}_t + u_t
$$

Where:
- $D_t$ = global petroleum demand (kbd), from IEA OMR annual or EIA international
- $P_t$ = Brent spot price (monthly average), from FRED `DCOILBRENTEU`
- $\text{GDP\_growth}_t$ = IMF World Economic Outlook GDP growth — controls for activity level
- $\varepsilon$ = estimated short-run price elasticity (expected range: −0.03 to −0.10)
- $\alpha$ = structural trend demand growth (~+1% per year pre-COVID)

**Literature benchmarks:**
- Short-run elasticity: **−0.05 to −0.08** (IEA consensus)
- Long-run elasticity: **−0.20 to −0.40** (as capital stock adjusts — smaller vehicles, EVs, efficiency)
- At $150/bbl Brent (+50% from $100 baseline), expected short-run demand loss: **−1.5 to −2.5 Mb/d globally**

**Implementation:** `analysis/demand_destruction.py` — load IEA Excel + FRED price → fit OLS → expose elasticity as a config parameter in `config.py`; plug into scenario price targets.

---

### Method 2 — Counterfactual Trend Deviation

Demand destruction is the gap between *what demand would have been* (trend extrapolation) and *what it actually was*. This avoids regression assumptions and is intuitive for scenario communication.

$$
\text{Destruction}_{t} = \hat{D}_{t}^{\text{trend}} - D_{t}^{\text{actual}}
$$

**Steps:**
1. Fit a linear or log-linear trend through 2015–2019 IEA annual demand (pre-COVID, pre-war)
2. Extrapolate the trend forward to 2026
3. Subtract actual 2020–2026 demand (from EIA international data, already in DB)
4. The residual is cumulative demand destruction in Mb/d-years

**Result from existing data:** This can be computed *right now* with data already in the `supply_demand` DB table — no new sources required. The `_yoy_series()` function in `supply_demand_cb.py` already computes YoY changes; extend it to compare against a trend line.

**Visualization:** Trend line vs. actual on the existing Supply/Demand chart; shaded area = cumulative destruction. Add as a toggle: "Show demand destruction vs. trend".

---

### Method 3 — Demand Shock Decomposition (Supply vs. Demand Driven)

Crude inventory changes disambiguate whether a price move is supply- or demand-driven — critical because they have opposite implications:

| Scenario | Crude Inventories | Price | Demand implication |
|---|---|---|---|
| Demand destruction | Rising ↑ | Falling ↓ | Demand genuinely weak |
| Supply disruption | Falling ↓ | Rising ↑ | Demand fine; supply cut |
| Both (war + recession) | Mixed | Volatile | Requires decomposition |

**Formula:**

$$
\text{Implied Demand}_t = \text{Production}_t + \text{Net Imports}_t - \Delta\text{Inventories}_t
$$

All three inputs are available:
- `Production` → `supply_demand` table (EIA international, already in DB)
- `Net Imports` → EIA weekly `PET.WCRIMUS2.W` (US only; global requires IEA)
- `ΔInventories` → EIA weekly `WCESTUS1` already in DB via `eia_backfill.py`

For the US this decomposition can run weekly with existing data. Globally it requires the IEA balance sheet (monthly, 6-week lag).

---

### Method 4 — Regime Classification (Machine Learning)

Once Methods 1–3 provide labelled historical observations, a simple classifier can tag *current conditions* as belonging to a known destruction regime:

| Regime | Characteristics | Demand loss estimate |
|---|---|---|
| **Mild** | PMI 46–49, price +20–40% | 0.3–0.8 Mb/d |
| **Moderate** | PMI 42–46, price +40–80%, recession fears | 0.8–2.5 Mb/d |
| **Severe** | PMI < 42 or lockdown-type shock, price +80%+ or −60%+ | 2.5–9.0 Mb/d |
| **Recovery** | PMI rising, inventories drawing | Demand rebounding |

**Features:** Brent 3-month change %, PMI level, inventory trend (3-week MA slope), aviation index, news sentiment score.  
**Model:** KNN or logistic regression trained on the 5 historical episodes — small enough that the whole training set is the episodes above.  
**Output:** Regime label + confidence score → feeds directly into the Demand Destruction Score formula.

---

### Practical Calibration Using Existing Project Data

The following can be done immediately without new data sources:

1. **Load IEA annual Excel** (free download, one-time) → store in `db/` as reference table
2. **Join with FRED Brent** already in DB → compute episode-level elasticities
3. **Join with EIA international** already in `supply_demand` table → compute counterfactual trend deviations for all 25 tracked countries
4. **Compute current implied regime** using PMI (add via FRED) + inventory trend (EIA weekly, already in DB) + news sentiment (GDELT, already running)

This gives a calibrated, model-backed demand destruction estimate with a **confidence interval** rather than a point guess — e.g., "current conditions consistent with Moderate regime: −1.2 ± 0.6 Mb/d global demand loss."

---

## Data Gaps and Limitations

- **Non-US actual demand:** EIA product supplied is US-only. China (16% of global demand) publishes monthly import data with 6-week lag via customs bureau — requires scraping, not an API. Carbon Monitor partially fills this.
- **Demand vs. inventory build confusion:** A rise in crude inventories can mean either weak demand OR strong supply. Must cross-reference product supplied (demand signal) with production data to disambiguate.
- **Annual EIA international data:** The Supply/Demand tab already pulls this (annual, 1-year lag) — weekly US data in Phase 1 provides the high-frequency complement.
- **News NLP false positives:** "Demand destruction" appears in bullish articles too (e.g., "fears of demand destruction prove unfounded"). LLM scoring must capture context, not just keyword presence.
