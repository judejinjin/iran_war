# Plan: Official Data Calibration for Oil Offline Calculation

## Problem Statement

The "Oil Offline (mbd)" figure on the Infrastructure tab is **entirely model-derived**:
the LLM estimates `oil_impact_mbd` from news headlines, those estimates feed into
`DisruptionEvent`, and `production_tracker.compute_daily_status()` rolls them up
against **hardcoded baseline constants** (`IR: 3.2 mbd`, `SA: 10.5 mbd`, etc.).

There is no feedback loop. The model has no way to know whether its estimates are
correct, and the baselines drift as geopolitical conditions change. The same
`_BASELINES` dict is also **duplicated** verbatim between `production_tracker.py`
and `infrastructure_agent.py`.

## Proposed Architecture

Replace the single-source LLM estimate with a **three-layer stack**:

```
Layer 1 (Authoritative, lagged):  EIA/JODI monthly actuals  → ground-truth calibration
Layer 2 (Near real-time, noisy):  LLM from news             → disruption signal (current)
Layer 3 (Derived):                Blended estimate           → displayed figure + confidence badge
```

---

## Layer 1 — EIA Monthly Actuals as Ground Truth (uses existing data)

### What already exists

`supply_demand_backfill.py` already fetches EIA international crude supply
(`activityId=1`, `productId=57`) monthly for all tracked countries and stores
it in the `supply_demand` table as `flow="supply", product="crude"`.
**This data is already in the DB — it is just not used by the production tracker.**

### New calibration step in `production_tracker.compute_daily_status()`

After Step 3 (country aggregation), add a Step 3b that looks up the most recent
EIA monthly actual for each country and computes a calibration ratio:

```
eia_actual_mbd   = latest SupplyDemand(flow=supply, product=crude, country=X) / 1000
model_current_mbd = CountryProduction.current_oil_mbd
calibration_ratio = eia_actual_mbd / model_current_mbd   (capped: 0.5 – 2.0)
eia_lag_days     = (today − eia_source_date).days
```

**Blended estimate logic:**

```python
if eia_lag_days <= 90:
    # Within EIA lag window — trust actuals; offset model by observed gap
    blended_mbd = eia_actual_mbd - (model_current_mbd - eia_actual_mbd) * 0.0
    confidence  = "eia_actual"
elif calibration_ratio is not None:
    # Beyond lag — project forward using calibrated model
    blended_mbd = model_current_mbd * calibration_ratio
    confidence  = "eia_calibrated"
else:
    blended_mbd = model_current_mbd
    confidence  = "model_only"
```

### New columns needed in `CountryProduction`

```python
eia_actual_oil_mbd  = Column(Float)   # most recent EIA monthly actual (mbd)
eia_source_date     = Column(Date)    # period of that EIA row
eia_lag_days        = Column(Integer) # days between EIA data date and today
calibration_ratio   = Column(Float)   # eia_actual / model_estimate
blended_oil_mbd     = Column(Float)   # the value displayed on the tab
blended_confidence  = Column(Text)    # "eia_actual" | "eia_calibrated" | "model_only"
```

---

## Layer 2 — Dynamic Baselines from EIA (replace hardcoded constants)

### Current problem

```python
# Duplicated verbatim in BOTH files:
#   collectors/production_tracker.py  (line 21)
#   agents/infrastructure_agent.py    (line 21)
_BASELINES = {
    "IR": {"oil": 3.2, "gas": 8.5},   # static — written once, never updated
    "SA": {"oil": 10.5, "gas": 10.0},
    ...
}
```

Saudi Arabia has made multiple OPEC+ production cuts since these values were set.
A hardcoded constant is guaranteed to be wrong within months.

### Fix: `_get_eia_baselines(session)` in `production_tracker.py`

Replace both `_BASELINES` dicts with a single function that averages the last
6 months of EIA monthly supply data, falling back to hardcoded values only when
EIA data is absent:

```python
_HARDCODED_FALLBACK = {
    "IR": {"oil": 3.2, "gas": 8.5},
    "SA": {"oil": 10.5, "gas": 10.0},
    "IQ": {"oil": 4.5, "gas": 3.0},
    "AE": {"oil": 3.2, "gas": 6.0},
    "KW": {"oil": 2.7, "gas": 1.8},
    "QA": {"oil": 1.8, "gas": 16.0},
    "OM": {"oil": 1.0, "gas": 4.0},
    "BH": {"oil": 0.2, "gas": 1.5},
}

def _get_eia_baselines(session) -> dict:
    """
    Return {country: {"oil": mbd, "gas": bcfd, "source": "eia"|"fallback"}}
    using the 6-month average of EIA monthly crude supply.
    Falls back to _HARDCODED_FALLBACK per-country if EIA data unavailable.
    """
    cutoff = date.today() - timedelta(days=180)
    rows = (
        session.query(SupplyDemand)
        .filter(
            SupplyDemand.flow == "supply",
            SupplyDemand.product == "crude",
            SupplyDemand.date >= cutoff,
        )
        .all()
    )
    by_country = defaultdict(list)
    for r in rows:
        if r.country in _HARDCODED_FALLBACK:
            by_country[r.country].append(r.value_kbd)

    result = {}
    for country, fallback in _HARDCODED_FALLBACK.items():
        if by_country[country]:
            avg_kbd = sum(by_country[country]) / len(by_country[country])
            result[country] = {
                "oil": round(avg_kbd / 1000.0, 3),   # kbd → mbd
                "gas": fallback["gas"],               # no EIA gas monthly
                "source": "eia",
            }
        else:
            result[country] = {**fallback, "source": "fallback"}
    return result
```

`infrastructure_agent.py` imports this instead of defining its own dict:
```python
from collectors.production_tracker import _get_eia_baselines
```

---

## Layer 3 — JODI Oil as a Secondary Validation Source

### What is JODI?

The [Joint Organisations Data Initiative](https://www.jodidata.org) is a free
public monthly oil database self-reported by ~70 countries including all OPEC
members. It provides crude production, imports, exports, and stocks.

- **Endpoint:** `https://www.jodidata.org/api/data/` — already referenced in
  `config.py` as `JODI_API_BASE` but never implemented
- **Lag:** 2–3 months, same as EIA international
- **Coverage:** Iran, Iraq, Saudi Arabia, UAE, Kuwait, Qatar, Oman, Bahrain
- **License:** Free, public

### New file: `backfill/jodi_backfill.py`

```python
"""
JODI Oil Backfill — monthly crude production from the Joint Organisations
Data Initiative for the 8 tracked Gulf countries.
Stored in supply_demand table with source="JODI" for cross-validation.
"""

JODI_COUNTRY_MAP = {
    "IRN": "IR", "SAU": "SA", "IRQ": "IQ", "ARE": "AE",
    "KWT": "KW", "QAT": "QA", "OMN": "OM", "BHR": "BH",
}
JODI_PRODUCT = "CRUDEOIL"
JODI_FLOW    = "PRODUCTION"

def run_backfill(start_from: date, session) -> int:
    """Fetch JODI monthly production and upsert into supply_demand."""
```

Stored in existing `SupplyDemand` table with `source="JODI"`, enabling direct
comparison queries:

```sql
SELECT country,
       MAX(CASE WHEN source='EIA'  THEN value_kbd END) eia,
       MAX(CASE WHEN source='JODI' THEN value_kbd END) jodi
FROM supply_demand
WHERE flow='supply' AND product='crude'
GROUP BY country, date;
```

---

## `RegionSupplySummary` — add confidence column

```python
data_confidence = Column(Text, default="model_only")
# "eia_current"    — within EIA lag window, using actual data
# "eia_calibrated" — beyond lag, model adjusted by EIA ratio
# "model_only"     — no EIA data for any tracked country
```

---

## Infrastructure Tab UI Changes

### 1. Metric card — confidence badge

The "Oil Offline (mbd)" card gains a coloured badge below the number:

| Badge | Meaning |
|---|---|
| 🟢 EIA Actuals (±2–3 mo) | `eia_current` — EIA data within 90 days |
| 🟡 Model + EIA Calibrated | `eia_calibrated` — model anchored to last EIA actuals |
| 🔴 Model Estimate Only | `model_only` — no EIA data in DB |

### 2. Country production chart — EIA overlay

Add a second trace to the existing `infra-country-production-chart`:
- **Bars** (existing): model estimate
- **Diamond markers** (new): EIA actual with source date annotation in hover
- When divergence > 15%: bar turns orange with tooltip explaining the gap

### 3. New collapsible data quality panel

A new `dbc.Accordion` section below the country chart showing per-country:

| Country | Baseline Source | EIA Actual | Model Est. | Δ mbd | EIA Date | Confidence |
|---|---|---|---|---|---|---|
| Iran | EIA 6-mo avg | 2.9 mbd | 3.1 mbd | +0.2 | Sep 2026 | 🟡 |
| Saudi Arabia | EIA 6-mo avg | 9.8 mbd | 10.2 mbd | +0.4 | Sep 2026 | 🟡 |

---

## File Changeset Summary

| File | Change | Phase |
|---|---|---|
| `db/database.py` | Add 6 columns to `CountryProduction`; add `data_confidence` to `RegionSupplySummary` | 1 |
| `collectors/production_tracker.py` | Replace `_BASELINES` with `_get_eia_baselines()`; add calibration Step 3b | 1 |
| `agents/infrastructure_agent.py` | Remove duplicate `_BASELINES`; import from `production_tracker` | 1 |
| `ui/callbacks/infrastructure_cb.py` | Confidence badge on metric card; EIA overlay on country chart; data quality panel | 1 |
| `ui/layouts/infrastructure.py` | Add `dbc.Accordion` data quality panel component | 1 |
| `backfill/jodi_backfill.py` | **New** — JODI monthly production for 8 Gulf countries | 2 |
| `backfill/backfill_manager.py` | Register `"jodi"` in `BACKFILL_SOURCES` + `_get_runner()` | 2 |
| `main.py` | Add `"jodi"` to startup `run_incremental` sources | 2 |
| `scheduler.py` | Add JODI to daily EIA/FRED refresh block in `_run_eia_fred()` | 2 |

---

## Data Availability & Limitations

| Source | Countries | Lag | Free | Notes |
|---|---|---|---|---|
| EIA International *(already fetched)* | All 8 | 2–3 mo | ✅ | Already in `supply_demand` table |
| JODI Oil | All 8 | 2–3 mo | ✅ | Needs new backfill |
| IEA Oil Market Report | All | 2–3 wks | ❌ paywalled | Gold standard; not practical |
| Kpler / Vortexa (AIS tanker data) | Indirect via exports | Real-time | ❌ commercial | Best Iran proxy; not practical |

### The irreducible lag problem

No free official source publishes production data with less than 2 months lag.
This architecture gives the best achievable result:
- **Historical (>2 months ago):** EIA/JODI actuals are authoritative — model replaced
- **Recent (0–2 months):** LLM-from-news remains the only real-time signal, but now
  **anchored to a calibrated baseline** rather than a stale hardcoded constant
- **Confidence is always visible** on the tab so users know what they're looking at
