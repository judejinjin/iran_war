# Chokepoint Transit Reduction — Analysis & Proposal

## 1. How Transit Reduction Is Currently Calculated

### Event Routing
All `shipment_disruption` events on a target date are matched to one of three chokepoints
(`hormuz`, `bab_el_mandeb`, `suez`) using:
1. **Bounding-box match** on event lat/lon
2. **Keyword match** on headline + summary text
3. **Fallback** → Hormuz (any unmatched Gulf event)

### Reduction Formula (`production_tracker.py`)

```
avg_severity = mean(event.severity) for all routed events on that day

if avg_severity ≥ 8:
    reduction = min(0.50,  prev_reduction + 0.10 × n_incidents)   # partial_blockade
elif avg_severity ≥ 5:
    reduction = min(0.30,  prev_reduction + 0.05 × n_incidents)   # restricted
elif n_incidents > 0:
    reduction = prev_reduction                                      # hold
else:
    reduction = max(0,     prev_reduction − 0.02)                  # decay 2%/day

oil_transit_mbd = normal_oil_mbd × (1 − reduction)
```

**Baselines** (`config.py`):

| Chokepoint      | Normal oil (Mb/d) | Normal LNG (bcf/d) |
|-----------------|------------------:|-------------------:|
| Strait of Hormuz | 21.0             | 16.0               |
| Bab el-Mandeb   | 4.8               | 0.4                |
| Suez Canal      | 5.5               | 2.0                |

---

## 2. Known Issues with Current Logic

| Issue | Root Cause | Effect |
|---|---|---|
| **Instant spike to cap** | `0.10 × n_incidents` unbounded before cap; GDELT produces 10–30 articles/day per conflict | Reduction jumps to 0.5 on day 1 of any major incident |
| **Slow decay** | Fixed −2%/day → 25 days to halve, 50 days to clear | Reduction persists long after real-world reopening |
| **Article count ≠ incident count** | GDELT re-fires for every news article about the same event | n_incidents inflated 10–30× vs. true physical incidents |
| **Hard cap at 0.5** | Code limit, not physical reasoning | Full Hormuz closure (which should = 1.0) is not representable |
| **Hormuz default fallback** | Any unmatched disruption event routes to Hormuz | Hormuz perpetually over-counted vs. Bab el-Mandeb / Suez |

---

## 3. Proposed Fix — Severity-Weighted Score with Decay

Replace raw event count with a **de-duplicated severity signal** and an **exponential decay**:

```python
# De-duplicate: cluster events within 6-hour windows and same chokepoint
# Use max severity per cluster, not count

severity_score = sum(max_severity_per_cluster) / MAX_DAILY_SCORE  # normalise to [0, 1]

# Exponential decay: half-life = 7 days
HALF_LIFE_DAYS = 7
alpha = 1 - 0.5 ** (1 / HALF_LIFE_DAYS)   # ≈ 0.095

reduction = alpha * severity_score + (1 - alpha) * prev_reduction
reduction = min(1.0, reduction)  # full blockade now representable
```

This gives physically meaningful numbers: a genuine Hormuz closure
(severity 10, confirmed) drives reduction toward ~1.0 over several days
and clears within 2–3 weeks once incidents stop.

---

## 4. Proposal — Real-Time Tanker Count Tracking for Hormuz

### 4.1 What We Want to Measure

The most direct ground-truth signal for Hormuz flow is the **number of tankers
transiting the strait per day** — directly observable via AIS (Automatic
Identification System) vessel tracking.

Target metrics:
- **Daily tanker count** (crude + product + LNG tankers crossing 56°E in the Strait)
- **Direction** (northbound = loaded, southbound = ballast)
- **Transit delay** (average hours in strait vs. historical baseline)
- **Vessel size mix** (VLCC / Suezmax / Aframax)

---

### 4.2 Data Sources

#### Primary — AIS Vessel Tracking

| Source | Data | Cost | Access |
|---|---|---|---|
| **MarineTraffic API** | Real-time + historical AIS positions, vessel type, port calls | Free: 100 credits/mo; Pro: ~$150+/mo | REST API (`/exportvessel`, `/getexpectedarrivals`) |
| **VesselFinder** | AIS positions, vessel ETA | Free tier limited; Commercial API available | REST API |
| **AISHub** | Aggregated AIS from receiver network | Free for data sharing members | UDP/REST feed |
| **Spire Maritime** | Global AIS, vessel predictions | Enterprise subscription | REST/Kafka |
| **exactEarth (Kongsberg)** | Satellite AIS (covers blind spots in Hormuz) | Subscription | REST API |

**Recommended entry point**: MarineTraffic `/getexpectedarrivals` or geofence
zone vessel count endpoint — free tier sufficient for daily batch pull.

#### Secondary — Proxy Signals (no API cost)

| Source | Signal | Lag |
|---|---|---|
| **OPEC Monthly Oil Market Report** | Hormuz transit barrels (Mb/d) | ~6 weeks |
| **IEA Oil Market Report** | Chokepoint flow estimates | ~4 weeks |
| **Lloyd's of London war risk premium** | Refines perceived threat in Hormuz | 1–2 days (requires scraping/subscription) |
| **Freight rate benchmarks** (BDTI, TD3C) | Indirect — spike = disruption | Same-day (Bloomberg/Reuters) |
| **EIA Weekly Petroleum Status** | US crude import origins (proxy for Gulf flows) | 1 week |

---

### 4.3 Implementation Plan

#### Step 1 — Define Geofence Zone

```python
HORMUZ_GEOFENCE = {
    # Strait narrows between Oman (N) and Iran (S)
    "lat_min": 26.0, "lat_max": 27.5,
    "lon_min": 56.0, "lon_max": 57.5,
    "crossing_lon": 56.5,   # virtual crossing line (E→W = outbound, W→E = inbound)
}
```

#### Step 2 — Daily Collector (`collectors/hormuz_ais_collector.py`)

```python
TANKER_VESSEL_TYPES = [
    "Crude Oil Tanker", "Product Tanker",
    "LNG Tanker", "LPG Tanker", "Chemical Tanker",
]

def fetch_hormuz_tanker_count(api_key: str, target_date: date) -> dict:
    """
    Query MarineTraffic geofence for tankers in Hormuz zone.
    Returns northbound/southbound counts, avg speed, avg delay.
    """
    ...
```

Persist to a new DB table `hormuz_transit` with columns:

```sql
CREATE TABLE IF NOT EXISTS hormuz_transit (
    date              DATE PRIMARY KEY,
    tanker_count_nb   INTEGER,   -- northbound (loaded, exiting Gulf)
    tanker_count_sb   INTEGER,   -- southbound (ballast, entering Gulf)
    vlcc_count        INTEGER,
    avg_speed_knots   REAL,
    avg_delay_hours   REAL,
    data_source       TEXT,
    fetched_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Step 3 — Calibrate Reduction to Tanker Count

Replace the severity heuristic with an **empirical flow model**:

```python
HORMUZ_NORMAL_TANKERS_PER_DAY = 18   # ~6,500/yr; EIA / IEA baseline

def tanker_count_to_reduction(tanker_count: int) -> float:
    """
    Map observed tanker count to reduction_pct.
    Normal ≈ 18/day → reduction = 0.
    Zero tankers → reduction = 1.0.
    """
    ratio = tanker_count / HORMUZ_NORMAL_TANKERS_PER_DAY
    return max(0.0, min(1.0, 1.0 - ratio))
```

This directly replaces the GDELT-incident heuristic with a **physical
observation** and eliminates all the article-count inflation issues.

#### Step 4 — Fallback Hierarchy

When AIS data is unavailable (API quota exceeded, outage):

```
1. AIS tanker count (primary)
2. GDELT severity-weighted score (improved formula from §3)
3. Roll forward previous day with +1% uncertainty widening
```

#### Step 5 — UI Integration

Add a **"Hormuz Transit"** card to the Infrastructure tab:

```
┌─────────────────────────────────────┐
│  Strait of Hormuz — Live Transit    │
│  Tankers today: 14  (normal: 18)    │
│  Reduction:     22%                 │
│  VLCCs:         6                   │
│  Avg delay:     +3.2 hrs            │
│  Source: AIS (MarineTraffic)        │
│  Updated: 2026-05-24 06:00 UTC      │
└─────────────────────────────────────┘
```

---

### 4.4 Cost & Effort Estimate

| Phase | Effort | Cost |
|---|---|---|
| DB table + ORM | 0.5 day | — |
| `hormuz_ais_collector.py` (MarineTraffic free tier) | 1 day | Free (100 credits/mo) |
| Calibration: tanker → reduction mapping | 0.5 day | — |
| UI card on Infrastructure tab | 0.5 day | — |
| **Pro AIS** (upgrade for real-time + history) | — | ~$150–500/mo |

Free tier (100 credits/mo) is sufficient for **daily batch pulls** at ~3 credits
per geofence query → ~30 queries/month → covers daily refresh.

---

### 4.5 Historical Validation

To validate the model, backfill against known disruption events:

| Date Range | Event | Expected Reduction |
|---|---|---|
| Jan–Dec 2024 | Houthi Red Sea campaign | Bab el-Mandeb: 40–70% |
| Mar 2021 | Ever Given (Suez) | Suez: ~100% for 6 days |
| Jul 2019 | IRGC tanker seizures | Hormuz: 5–15% (risk premium) |
| 2022 | Ukraine → rerouting | Bab el-Mandeb: +20% northbound |

Compare modelled `reduction_pct` to OPEC/IEA reported flow changes as
ground truth.
