# Plan: Historical Calendar Spreads on Futures Tab

## Current State

### What exists
- **`FuturesCurve` table**: 11,088 rows for CL + COIL
  - Multi-contract IB curve snapshots: **301 observation dates** from **2025-08-20 to today**,
    with 12–24 contract months per date
  - FRED/Yahoo single front-month rows: 2026-01 onward (1 row per date)
- **`Spread` table**: already has `CL_M1-M12`, `CL_M1-M2`, `CL_M1-M6` spread types
  - Only **119 rows** (sparse — backfill hasn't been run fully)
  - Date range: 2026-02-23 to today
- **UI callback**: computes spreads on-the-fly from `FuturesCurve`, date range defaults
  to **last 30 days only** → only current contracts visible

### Why the chart shows "current live contracts only"
1. **30-day default date range** hides the 14 months of IB curve history already in the DB
2. **On-the-fly computation** doesn't query the Spread table (which could hold long history)
3. **No pre-IB history** — multi-contract curves only available from 2025-08-20 onwards;
   before that, only single front-month FRED data exists (can't compute M1-M12 spread)

---

## Proposed Improvements

### Layer A — Use What We Already Have (IB curves, 2025-08-20 to today)
### Layer B — EIA Historical Futures M1-M12 (1987 to today)

```
EIA RCLC1–RCLC12 (1987+)      IB multi-contract curves (2025-08+)
         ↓                               ↓
    Spread table (pre-computed)    Spread table (backfill gaps)
              ↘                  ↙
           UI: read Spread table → full history chart
```

---

## Step 1 — EIA Historical WTI Futures M1-M12 Backfill

**New file:** `backfill/eia_futures_backfill.py`

### Source
EIA API v2 endpoint: `https://api.eia.gov/v2/petroleum/pri/fut/data/`  
Series: `RCLC1` through `RCLC12` — "Cushing, OK Crude Oil Future Contract N ($/bbl)"  
Coverage: Daily, **1983-03-30 to present**  
Confirmed in EIA facets API: `RCLC1`, `RCLC2`, `RCLC4` are listed.

> **Note:** Correct facets param syntax must be confirmed against live API before
> implementation. Use `facets[series][0]=RCLC1&facets[series][1]=RCLC2` etc.

### What to store
Map `RCLC{n}` → offset `n-1` from today's front month:

```python
# On observation date d, "RCLC1" is M1 (nearest expiry), "RCLC12" is M12.
# We don't know the exact contract month from EIA — we derive it:
#   M1 contract_month = next expiry month after date d
#   M{n} contract_month = nth month ahead

_EIA_SERIES = {f"RCLC{i}": i for i in range(1, 13)}   # M1 through M12
```

Store each row into the **existing `FuturesCurve` table**:
- `symbol = "CL"`
- `source = "EIA"` (add a `source` column — see Step 2)
- `contract_month` = derived from the date + offset (e.g., for 2020-01-15, RCLC1 → "2020-02")
- `settlement_price` = the EIA value

This lets the existing spread computation logic work on EIA data identically to IB data.

**Function signature:**
```python
def run_backfill(start_from: date, session) -> int:
    """
    Fetch EIA WTI M1-M12 daily futures. Uses full history override on first run
    (same pattern as FRED Dubai in fred_backfill.py). Returns rows upserted.
    """
```

### Register in BackfillManager
- Add `"eia_futures"` to `BACKFILL_SOURCES`
- Add to `_get_runner()` and to `main.py` startup sources
- Add to `scheduler.py` `_run_eia_fred()` block (daily refresh, same cadence)

---

## Step 2 — Add `source` Column to `FuturesCurve`

**File:** `db/database.py`

Add a `source` column to distinguish IB vs FRED vs EIA rows:

```python
class FuturesCurve(Base):
    ...
    source = Column(Text, default="IB")   # "IB" | "FRED" | "EIA"
```

Add to `_migrate_schema()`:
```python
("futures_curves", "source", "TEXT DEFAULT 'IB'"),
```

This allows filtering by source and avoids conflicts between IB and EIA rows for the
same (date, symbol, contract_month) — the UniqueConstraint needs `source` added:

```python
__table_args__ = (UniqueConstraint("date", "symbol", "contract_month", "source"),)
```

> **Note:** The existing `UniqueConstraint("date", "symbol", "contract_month")` must be
> dropped and recreated. Since SQLite doesn't support `DROP CONSTRAINT`, this requires
> recreating the table or allowing duplicates by loosening the constraint. Simplest
> approach: **keep existing constraint** but only insert EIA rows for dates/contract months
> that don't already have an IB row (IB takes precedence).

---

## Step 3 — Backfill Missing Spread Rows from Existing IB Curves

The `Spread` table has only 119 rows despite 301 observation dates having full IB curves.
A gap-fill pass is needed.

**New function in `backfill/eia_futures_backfill.py`** (or a separate utility):

```python
def backfill_spreads_from_curves(session) -> int:
    """
    For every observation date in FuturesCurve that has >= 12 contract months,
    compute and upsert CL_M1-M2, CL_M1-M6, CL_M1-M12 and COIL equivalents
    into the Spread table. Skips dates already present. Returns rows inserted.
    """
```

This is a pure DB-to-DB operation — no external API calls. Can run at startup or
as part of the `eia_futures` backfill source.

---

## Step 4 — Update Calendar Spread Callback

**File:** `ui/callbacks/futures_cb.py`

### 4a — Read from `Spread` table (primary path)

Replace the on-the-fly `FuturesCurve` computation with a direct `Spread` query:

```python
# PRIMARY: fast query of pre-computed spreads
_SPREAD_TYPE_MAP = {
    ("CL",   "M1-M2"):  "CL_M1-M2",
    ("CL",   "M1-M6"):  "CL_M1-M6",
    ("CL",   "M1-M12"): "CL_M1-M12",
    ("COIL", "M1-M2"):  "COIL_M1-M2",
    ("COIL", "M1-M6"):  "COIL_M1-M6",
    ("COIL", "M1-M12"): "COIL_M1-M12",
}

rows = session.query(Spread).filter(
    Spread.spread_type == _SPREAD_TYPE_MAP[(sym, cal_spread_mode)],
    Spread.date >= start_date,
    Spread.date <= end_date,
).order_by(Spread.date).all()
points = [(r.date, r.spread_value) for r in rows if r.spread_value is not None]
```

### 4b — Fallback to on-the-fly for gaps

If `points` is empty (no pre-computed data for the date range), fall back to the
existing on-the-fly computation from `FuturesCurve`. This ensures no regression
while the EIA historical data is still being fetched.

### 4c — Widen default date range

Change the default in `ui/layouts/futures.py`:

```python
# Before (30 days):
default_start = today - timedelta(days=DEFAULT_TIMELINE_DAYS)  # 30 days

# After (full IB history, ~14 months):
default_start = date(2025, 8, 20)   # IB curve data start
```

Or better: default to `WAR_START_DATE` to show full war-period context.

### 4d — Add source annotation to chart

Add a small annotation or text below the spread chart indicating the data source
for the displayed date range:

- Before 2025-08-20: "EIA historical (if backfill complete)"
- 2025-08-20 to today: "IB live curves"

### 4e — Add M1 contract rollover markers

Vertical dashed lines on the spread chart when the front contract changes (roll date):

```python
# Detect roll dates from front_month changes in the Spread table
prev_front = None
for r in rows:
    if r.front_month != prev_front and prev_front is not None:
        spread_fig.add_vline(x=r.date, line_dash="dot", line_color="#444",
                             annotation_text=f"Roll → {r.front_month}")
    prev_front = r.front_month
```

---

## Step 5 — Layout Update

**File:** `ui/layouts/futures.py`

1. **Update default date range**: from `today - 30 days` to war start date

2. **Add historical data toggle** next to the spread mode selector:
   ```python
   dbc.Checklist(
       id="futures-spread-history-toggle",
       options=[{"label": "Show full history", "value": "full"}],
       value=[],
       inline=True,
   )
   ```
   When checked, forces `start_date = date(1987, 1, 1)` (EIA history start).

3. **Add roll markers toggle**:
   ```python
   dbc.Checklist(
       id="futures-spread-roll-markers",
       options=[{"label": "Show roll dates", "value": "rolls"}],
       value=["rolls"],
       inline=True,
   )
   ```

---

## File Changeset Summary

| File | Change | Phase |
|---|---|---|
| `db/database.py` | Add `source` col to `FuturesCurve`; update `_migrate_schema()`; update `Spread` UniqueConstraint note | A |
| `backfill/eia_futures_backfill.py` | **New** — EIA RCLC1-RCLC12 daily WTI fetch (1983+); `backfill_spreads_from_curves()` gap-filler | A+B |
| `backfill/backfill_manager.py` | Add `"eia_futures"` source | A |
| `main.py` | Add `"eia_futures"` to startup sources | A |
| `scheduler.py` | Add EIA futures to `_run_eia_fred()` | A |
| `ui/callbacks/futures_cb.py` | Read from Spread table (primary); on-the-fly fallback; roll markers; source annotations | A |
| `ui/layouts/futures.py` | Widen default range; history toggle; roll marker toggle | A |

---

## Data Coverage After Implementation

| Source | Symbol | Spread Types | Date Range | Resolution |
|---|---|---|---|---|
| EIA RCLC1-RCLC12 | CL only | M1-M2, M1-M6, M1-M12 | 1983 to today | Daily |
| IB multi-contract | CL + COIL | All three | 2025-08-20 to today | 3×/day snapshot |
| IB (gaps already in DB) | CL + COIL | All three | 2026-02-23 to today | Pre-computed in Spread |

**Limitation:** No free historical Brent multi-contract data before 2025-08-20. EIA
only provides WTI futures (RCLC). ICE Brent historical futures are commercial-only.
For Brent M1-M12 history, the tab will show IB data from 2025-08-20 onwards.

---

## Key Technical Notes

### EIA API v2 facets syntax (to verify before implementing)
```
GET /v2/petroleum/pri/fut/data/
  ?api_key=...
  &frequency=daily
  &data[0]=value
  &facets[series][0]=RCLC1
  &facets[series][1]=RCLC2
  ...
  &start=2026-01-01
  &length=5000
```
Confirmed `RCLC1` and `RCLC2` exist in facets. Live data test returned 0 rows — 
need to confirm correct parameter format or whether the v2 endpoint requires
different field names for this route.

### UniqueConstraint strategy
Do NOT modify the `FuturesCurve` UniqueConstraint (SQLite can't drop constraints
without table rebuild). Instead, in `eia_futures_backfill.py`:
```python
# Only insert EIA row if no IB row exists for same (date, symbol, contract_month)
existing = session.query(FuturesCurve).filter_by(
    date=obs_date, symbol=symbol, contract_month=contract_month
).first()
if not existing:
    session.add(FuturesCurve(..., source="EIA"))
```

### Contract month derivation for EIA data
EIA gives a daily price for "M1" but doesn't name the contract. Derive:
```python
from collectors.production_tracker import ...
# Actually use: next_expiry_after(obs_date) for M1, then add months for M2-M12
# CL expiry: 3 biz days before the 25th of the prior calendar month
# If obs_date < expiry(current month): M1 = current month
# Else: M1 = next month
```
Use the `_contract_expiry()` function already in `futures_cb.py` (should be moved
to a shared utility module — `utils/futures_utils.py` — so it can be imported by
the backfill without circular deps).
