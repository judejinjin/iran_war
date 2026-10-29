# Implementation Plan: Historical Calendar Spreads on Futures Tab

## Problem Statement

Calendar spreads on the Futures tab currently show **only the live date range** — the
chart goes blank for any period before the IB backfill captured a full multi-contract
curve. The root cause:

- **FRED and Yahoo backfills** store only one row per date: `contract_month = obs_date`.  
  On 2026-01-15 there is one row `CL / 2026-01 / $75.20`. No M2, M6, M12 data.
- **IB backfill** fetches the full forward curve (all 12+ contracts) for each date —
  this is the *only* source with multi-contract rows.
- The spread algorithm groups rows by date, sorts by `contract_month`, then takes
  `contracts[0]` as M1 and `contracts[offset]` as Mn.  
  For FRED/Yahoo dates, `len(contracts) == 1`, so `len > offset` is always False → blank.

---

## Proposed Architecture

```
Phase 1: Historical contracts backfill (Yahoo Finance, expired contract tickers)
    ↓ populates FuturesCurve with M1–M12+ rows for each historical date
Phase 2: Pre-compute spread cache in Spread table
    ↓ CL_M1M2, CL_M1M6, CL_M1M12, COIL_M1M2, etc. — one row per date per type
Phase 3: Update futures_cb.py to read from Spread cache with on-the-fly fallback
Phase 4: UI improvements — extended default range, spread percentile, annotations
```

---

## Phase 1 — Historical Contracts Backfill

### New file: `backfill/historical_contracts_backfill.py`

Yahoo Finance carries individual expired futures contracts by their specific ticker
codes. This is the **only free daily-resolution source** for expired contract history
going back several years.

#### WTI (CL) ticker format

```
CL{month_code}{2-digit-year}=F
```

| Month | Code | Example |
|---|---|---|
| Jan | F | CLF26=F |
| Feb | G | CLG26=F |
| Mar | H | CLH26=F |
| Apr | J | CLJ26=F |
| May | K | CLK26=F |
| Jun | M | CLM26=F |
| Jul | N | CLN26=F |
| Aug | Q | CLQ26=F |
| Sep | U | CLU26=F |
| Oct | V | CLV26=F |
| Nov | X | CLX26=F |
| Dec | Z | CLZ26=F |

#### Brent (COIL) ticker format

ICE Brent futures on Yahoo use the `BZ` prefix:

```
BZ{month_code}{2-digit-year}=F
```

Example: `BZF26=F` (Jan 2026 Brent), `BZZ27=F` (Dec 2027 Brent).

#### How it works

For each `(symbol, year, month)` combination in the requested date range:

1. Build the Yahoo ticker string (e.g., `CLK26=F`)
2. Download daily OHLCV via `yf.Ticker(ticker).history(period="max")`
3. Upsert each row into `FuturesCurve` as:
   ```
   date=obs_date, symbol="CL", contract_month="2026-05", settlement_price=close
   ```
4. The `UniqueConstraint("date", "symbol", "contract_month")` ensures idempotency

#### Contract coverage

To support M1-M12 spreads across the full history, we need at least 13 simultaneous
contracts per date. Backfill N years of monthly contracts:

```
years × 12 months × 2 symbols = contracts to fetch
```

Default: 3 years back = 72 CL + 72 BZ = 144 yfinance requests (fast, no rate limit).

#### Function signature

```python
def run_backfill(start_from: date, session, years_back: int = 3) -> int:
    """
    Fetch individual expired/live futures contract prices from Yahoo Finance.
    Covers contract_months from (today - years_back) to (today + 12 months ahead).
    Returns total FuturesCurve rows inserted/updated.
    """
```

#### Limitations

- Yahoo has some gaps on expired Brent (`BZ`) contracts — fall back gracefully to `None`
  (skip, log warning). WTI (`CL`) coverage is excellent back to ~2010.
- Yahoo does not carry WTI contracts more than ~12 months beyond today (IB handles those).
- Rate-limiting: yfinance is free/unofficial. Add a small `time.sleep(0.1)` between
  requests to avoid hitting limits. 144 requests with 0.1s delay ≈ 15 seconds total.

---

## Phase 2 — Pre-Compute Calendar Spread Cache

### New function: `backfill/spread_cache_backfill.py`

After the historical contracts backfill populates `FuturesCurve` with multi-contract
rows, compute and cache all spread series into the existing `Spread` table.

```
spread_type  = "CL_M1M2" | "CL_M1M6" | "CL_M1M12"
              "COIL_M1M2" | "COIL_M1M6" | "COIL_M1M12"
front_month  = M1 contract month (e.g., "2026-05")
back_month   = Mn contract month (e.g., "2027-04")
spread_value = M1_price - Mn_price
```

#### Algorithm

For each date in `FuturesCurve`:
1. Sort all contracts for that `(date, symbol)` by `contract_month` ascending
2. If at least `offset + 1` contracts exist with non-null prices:
   - Compute `spread = contracts[0].price - contracts[offset].price`
   - Upsert into `Spread` with `spread_type = f"{symbol}_M1M{offset+1}"`
3. Skip dates with insufficient contracts (graceful — FRED/Yahoo-only dates)

This runs once on backfill, then incrementally as new IB curve data arrives.

#### Function signature

```python
def run_backfill(start_from: date, session) -> int:
    """
    Compute and cache calendar spread values into the Spread table
    from all available FuturesCurve data.
    Returns number of Spread rows inserted/updated.
    """
```

---

## Phase 3 — Update `futures_cb.py`

### Main spread chart callback

Replace the on-the-fly computation with a **two-source query**:

```python
# 1. Primary: query precomputed Spread table (covers full history)
cached = session.query(Spread).filter(
    Spread.spread_type == f"{sym}_M1M{offset+1}",
    Spread.date >= start_date,
    Spread.date <= end_date,
).order_by(Spread.date).all()

# 2. Fallback: compute on-the-fly for dates not yet in Spread cache
# (e.g., today if cache not yet refreshed)
if not cached or cached[-1].date < end_date - timedelta(days=2):
    # existing on-the-fly code for the gap
    ...

# Merge and deduplicate by date (Spread cache takes priority)
```

### Extended date range for spread section

Add a **separate date range control for the spread chart** (or allow the global range
to span years). The current default of 30 days is too short for spread context.

Add to the layout next to `futures-cal-spread-toggle`:

```python
dcc.DatePickerRange(
    id="futures-spread-date-range",
    start_date=date.today() - timedelta(days=365),
    end_date=date.today(),
    display_format="YYYY-MM-DD",
)
```

### Spread percentile card

Below the spread chart, add a small metric row showing:
- Current spread value
- Historical percentile (last 3 years)
- 52-week range (min/max)

```
CL M1-M12: -$2.14    [3-yr pct: 28th]    [52W range: -$4.80 to +$0.30]
```

Computed from the `Spread` table — a simple percentile rank query.

---

## Phase 4 — Scheduler & BackfillManager

### `backfill/backfill_manager.py`

Add two new source keys:
1. `"historical_contracts"` — runs `historical_contracts_backfill.run_backfill()`
2. `"spread_cache"` — runs `spread_cache_backfill.run_backfill()`

Register both in `BACKFILL_SOURCES` and `_get_runner()`.

### `main.py`

Add both to the startup `run_incremental` sources:

```python
bm.run_incremental(sources=[
    "fred", "yahoo", "eia", "cushing", "crack_spread",
    "historical_contracts", "spread_cache",
])
```

The `historical_contracts` backfill runs after `fred` / `yahoo`, then `spread_cache`
runs after `historical_contracts` to recompute from the newly populated data.

### `scheduler.py`

Extend `_run_eia_fred()` to also refresh the spread cache daily (after FRED + crack spread):

```python
try:
    from backfill.spread_cache_backfill import run_backfill as spread_cache_backfill
    _sc_session = get_session()
    _sc_count = spread_cache_backfill(
        start_from=date.today() - timedelta(days=60),
        session=_sc_session,
    )
    _sc_session.close()
    results["spread_cache"] = f"{_sc_count} records"
except Exception as e:
    ...
```

`historical_contracts` runs once at startup (first run covers full history) then
daily at 11:00 ET via the same block for the rolling 13-month window.

---

## File Changeset Summary

| File | Change | Phase |
|---|---|---|
| `backfill/historical_contracts_backfill.py` | **New** — Yahoo expired contract fetch | 1 |
| `backfill/spread_cache_backfill.py` | **New** — pre-compute Spread table from FuturesCurve | 2 |
| `backfill/backfill_manager.py` | Add `"historical_contracts"` + `"spread_cache"` | 2 |
| `main.py` | Add both to startup `run_incremental` sources | 2 |
| `scheduler.py` | Extend `_run_eia_fred()` with both refresh blocks | 2 |
| `ui/callbacks/futures_cb.py` | Spread chart reads from `Spread` table + on-the-fly fallback; new date range input; percentile card | 3 |
| `ui/layouts/futures.py` | Add spread date range picker; percentile metrics row | 3 |

---

## What the user sees after implementation

| Before | After |
|---|---|
| Spread chart blank before ~2026-01-01 | Full spread history from Jan 2023 (3yr) |
| Default date range 30 days → tiny spread chart | Default 1 year for spread section |
| No spread context | Percentile rank + 52-week range shown below chart |
| Single data source (IB only) | IB + Yahoo historical, clearly labelled |

---

## Data Availability Notes

| Source | WTI CL | Brent COIL | Depth | Free |
|---|---|---|---|---|
| Yahoo expired contracts | ✅ excellent (2010+) | ⚠️ partial (BZ, some gaps) | Daily OHLCV | ✅ |
| IB historical (existing) | ✅ | ✅ | Daily + intraday | Requires TWS |
| FRED (existing) | ✅ spot only | ✅ spot only | Daily, 1987+ | ✅ |
| Quandl CME | ✅ | ✅ | Daily 1983+ | Free tier limited |

Brent gaps in Yahoo are not critical: the Brent spread is secondary to WTI. Where
`BZ` tickers have no data, fall back to COIL rows already in the DB from IB captures.

---

## Testing Checklist

- [ ] `historical_contracts_backfill` inserts rows with distinct `contract_month` values (not all same as `obs_date`)
- [ ] For a given date, multiple contracts exist for CL in `futures_curves` after backfill
- [ ] `spread_cache_backfill` populates `Spread` with `spread_type = "CL_M1M12"` rows spanning full date range
- [ ] Spread chart shows data back to `start_date - 3 years` after backfill
- [ ] On-the-fly fallback still works when Spread cache is empty
- [ ] `--skip-backfill` doesn't crash the spread chart (graceful empty state)
- [ ] Percentile card updates when spread date range changes
