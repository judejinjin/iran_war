# Oil Super Spike Analyzer — Data Quality Report

**Generated:** 2026-04-15  
**Database:** `D:\oil\db\oil_data.db` (6.7 MB)

---

## Overall Table Summary

| Table | Rows | Status |
|---|---:|---|
| News/Geopolitical | 1,183 | OK |
| Daily Summaries | 122 | OK |
| Military Events | 50 | OK |
| Military Deployments | 54 | OK |
| Military Daily Summary | 38 | OK |
| Futures Curves | 2,437 | OK |
| Spreads | 182 | OK |
| Options Chains | 27,453 | OK |
| Vol Surface | 975 | OK |
| Scenarios | 24 | OK |
| Agent Analyses | 12 | OK |
| Positions | 0 | **EMPTY** |
| Facilities | 52 | OK |
| Facility Status | 2,392 | OK |
| Disruption Events | 14 | OK |
| Country Production | 376 | OK |
| Hormuz Status | 47 | OK |
| Chokepoint Status | 141 | OK |
| Backfill Status | 8 | LOW |

---

## CRITICAL — Options Chains (27,453 rows)

**Date range:** 2026-02-08 → 2026-04-15 (57 dates)  
**Underlyings:** CL (21,060 rows, 12 expiries) · COIL (6,393 rows, 12 expiries)

### 1. Call/Put Strike Mismatch

Nearly every expiry has **different strike counts for calls vs puts**. Deep OTM strikes with no MIDPOINT activity return no data from IB, creating asymmetric chains.

**Example — Apr 15, CL:**

| Expiry | Calls | Call Range | Puts | Put Range |
|---|---:|---|---:|---|
| 2026-04-16 | 3 | 80–110 | 9 | 70–270 |
| 2026-05-14 | 14 | 50–270 | 9 | 70–210 |
| 2026-06-16 | 12 | 50–270 | 12 | 50–250 |
| 2026-07-16 | 9 | 50–270 | 6 | 50–180 |
| 2026-08-17 | 13 | 70–270 | 7 | 50–170 |
| 2027-03-17 | 16 | 70–250 | 3 | 50–70 |

**Root cause:** IB MIDPOINT bars are only available for strikes with recent trading activity. Deep OTM puts and far-dated options often have none.

### 2. Massive Strike Count Drops (Apr 14)

The old per-row upsert was extremely slow, causing the backfill to time out before inserting all rows. Batch upsert was implemented but Apr 14 data reflects the broken period.

| Date | Symbol | Expiry | Change |
|---|---|---|---|
| 2026-04-14 | CL | 2026-04-16 | 38→13 (**-66%**) |
| 2026-04-14 | CL | 2026-05-14 | 48→25 (-48%) |
| 2026-04-14 | CL | 2026-07-16 | 44→17 (-61%) |
| 2026-04-14 | COIL | 2026-04-27 | 18→3 (**-83%**) |
| 2026-04-14 | COIL | 2026-10-27 | 30→9 (-70%) |
| 2026-04-14 | COIL | 2026-12-23 | 8→2 (-75%) |

### 3. Field Completeness

| Field | Filled | Total | % | Status |
|---|---:|---:|---:|---|
| last_price | 27,453 | 27,453 | 100.0% | OK |
| implied_vol | 21,838 | 27,453 | 79.5% | OK (deep OTM) |
| delta/gamma/vega/theta | 21,839 | 27,453 | 79.6% | OK |
| bid | 0 | 27,453 | 0.0% | **CRITICAL** |
| ask | 0 | 27,453 | 0.0% | **CRITICAL** |
| volume | 34 | 27,453 | 0.1% | **CRITICAL** |
| open_interest | 77 | 27,453 | 0.3% | **CRITICAL** |

**Root cause:** MIDPOINT bars don't include bid, ask, volume, or OI. These require separate data requests (BID_ASK bars or live market data snapshots).

---

## HIGH — Futures Curves (2,437 rows)

**Date range:** 1992-01-01 → 2026-04-15 (458 dates)

| Symbol | Rows | Dates | Months | Price Range | Null Px | Volume % | OI % |
|---|---:|---:|---:|---|---:|---:|---:|
| CL | 861 | 46 | 25 | $53.53–$112.95 | 0% | 58.9% | 0% |
| COIL | 586 | 46 | 25 | $60.60–$127.61 | 1.2% | 7.2% | 0% |
| DUB | 411 | 411 | 411 | $10.08–$130.08 | 0% | 0% | 0% |

**Issues:**
- **OI = 0%** for all futures symbols (MIDPOINT bars)
- COIL has 7 null prices (1.2%) — illiquid back months
- COIL volume coverage very low (7.2%)

---

## MEDIUM — News & Geopolitical (1,183 rows)

**Timestamp range:** 2016-11-21 → 2026-04-16

| Category | Count | Avg Severity | Has Supply Impact |
|---|---:|---:|---:|
| geopolitical_development | 511 | 4.7 | 35 |
| unclassified | 292 | N/A | 0 |
| shipment_disruption | 251 | 7.5 | 216 |
| military_operations | 90 | 6.8 | 33 |
| infrastructure_damage | 26 | 7.7 | 20 |
| production_shutin | 13 | 8.5 | 12 |

**Issues:**
- **292 "unclassified" events (25%)** — no severity, no supply impact
- Geo-coordinates only **51.5%** filled (map gaps)
- Severity/supply_impact **75.3%** (dragged down by unclassified)

---

## MEDIUM — Military Intelligence

| Table | Rows | Date Range |
|---|---:|---|
| military_events | 50 | 2026-03-12 → 2026-04-14 |
| military_deployments | 54 | — |
| military_daily_summary | 38 | 2026-03-12 → 2026-04-15 |

**Issues:**
- **Thin dataset** (50 events total)
- Escalation scores jump abruptly (2→8) due to coverage gaps

---

## LOW — Backfill Status

| Source | Status | Last Date | Records | Error |
|---|---|---|---:|---|
| dme | complete | N/A | 0 | — |
| eia | in_progress | N/A | 0 | — |
| fred | complete | N/A | 461 | Internal Server Error |
| gdelt | complete | 2026-04-15 | 0 | — |
| ib_futures | **pending** | N/A | 0 | — |
| ib_options | **pending** | N/A | 27,519 | Failed to connect to TWS after 3 attempts |
| scenarios | pending | N/A | 0 | — |
| yahoo | complete | N/A | 39 | 'NoneType' object is not subscriptable |

---

## Infrastructure & Production (healthy)

- **52 facilities** across 8 countries, 59+ mbd total capacity
- **2,392 facility status records** (2026-02-28 → 2026-04-15)
- **14 disruption events** totaling 30+ mbd impact
- **376 country production records** (8 countries)
- Chokepoints (Hormuz/Bab el-Mandeb/Suez): 141 status rows

## Vol Surface (healthy)

- **975 rows**, 47 dates, CL (545) + COIL (430)
- ATM vol populated for all rows
- Skew null for ~50% (far-dated expiries with insufficient strikes)

## Scenarios & Analyses

- **24 scenario probabilities** across 6 scenarios (Apr 3–14)
- **12 agent analyses**: 6 trade recommendations, 6 mispricing
- Note: trade_recommendation confidence avg = 286.7% (likely a scale bug)
