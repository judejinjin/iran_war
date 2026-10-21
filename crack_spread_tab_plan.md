# Implementation Plan: Crack Spread Tab (USA Diesel)

## Overview

Add a new **Crack Spread** tab to the Oil Super Spike Analyzer that tracks and
visualises the US diesel (ULSD) crack spread — the refining margin from crude oil
into Ultra-Low Sulfur Diesel — alongside the 3-2-1 composite crack spread and
seasonal context.

The tab follows the existing 5-layer pattern used throughout the app:

```
DB model → Backfill module → BackfillManager registration →
  ui/layouts/crack_spread.py → ui/callbacks/crack_spread_cb.py →
    ui/app.py (tab + router + import)
```

---

## Background: Diesel Crack Spread

| Series | Source | Unit | Transform |
|---|---|---|---|
| WTI front-month | Already in DB as `FuturesCurve(symbol="CL")` | $/bbl | — |
| ULSD spot (No. 2 Heating Oil, NY Harbor) | FRED `DHOILNYH` | $/gal | × 42 → $/bbl |
| RBOB Gasoline spot | FRED `GASREGCOVW` or Yahoo `RB=F` | $/gal | × 42 → $/bbl |
| ICE Brent front-month | Already in DB as `FuturesCurve(symbol="COIL")` | $/bbl | — |

**Key spreads to display:**

- **Diesel crack** = ULSD ($/bbl) − WTI ($/bbl)
- **3-2-1 crack** = `(2 × RBOB_bbl + 1 × ULSD_bbl − 3 × WTI_bbl) / 3`
- **Diesel–Brent crack** = ULSD ($/bbl) − Brent ($/bbl)  *(EU refinery benchmark)*
- **Diesel–WTI seasonal** = rolling 5-year average band overlay

---

## Step 1 — Database Model

**File:** `db/database.py`

Add a `CrackSpreadPrice` ORM model to store the raw product prices used in
crack calculations. The existing `Spread` table can store derived spread values.

```python
class CrackSpreadPrice(Base):
    """
    Raw refined-product spot prices (ULSD, RBOB) used to compute crack spreads.
    price_per_gal  — as fetched from FRED ($/gal)
    price_per_bbl  — price_per_gal * 42 ($/bbl), computed on insert
    """
    __tablename__ = "crack_spread_prices"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    date          = Column(Date, nullable=False)
    symbol        = Column(Text, nullable=False)   # "ULSD" | "RBOB"
    source        = Column(Text, nullable=False)   # "FRED" | "EIA"
    price_per_gal = Column(Float)
    price_per_bbl = Column(Float)                  # price_per_gal * 42
    created_at    = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("date", "symbol", "source"),)
```

Existing `Spread` table already has `spread_type`, `spread_value`, `date` — use
it for derived crack values with `spread_type` values:

| `spread_type` | Description |
|---|---|
| `DIESEL_CRACK_WTI` | ULSD $/bbl − WTI $/bbl |
| `DIESEL_CRACK_BRENT` | ULSD $/bbl − Brent $/bbl |
| `CRACK_321_WTI` | 3-2-1 composite vs WTI |

Add `init_db()` call automatically picks up the new model since it uses
`Base.metadata.create_all(engine)` — **no migration script needed**.

---

## Step 2 — Backfill Module

**New file:** `backfill/crack_spread_backfill.py`

```python
"""
Crack Spread Backfill — fetches ULSD and RBOB spot prices from FRED,
converts to $/bbl, and computes diesel + 3-2-1 crack spreads vs WTI / Brent.
"""
```

### Logic

1. **Fetch ULSD** from FRED series `DHOILNYH` (No. 2 Heating Oil, NY Harbor,
   daily, 1986+). Multiply by 42 to get $/bbl. `price_per_bbl` must be computed
   explicitly in code (`price_per_gal * 42`) before inserting — there is no
   database trigger or ORM property to do this automatically.
2. **Fetch RBOB** from FRED series `WRBWHOLESALE` (Weekly Retail Gasoline Prices,
   RBOB, EIA via FRED). **Do NOT use `GASREGCOVW`** — that is US retail pump
   price and would overstate the 3-2-1 crack spread by ~$0.50-$1.00/gal
   ($21-$42/bbl). Use `WRBWHOLESALE` (wholesale/rack price) or fall back to
   Yahoo `RB=F` (RBOB front-month futures, already in `yahoo_backfill.py`
   infrastructure) for daily resolution.
3. **Override `start_from` for first run**: `BackfillManager` sets
   `start_from = war_start` (2026-01-01) on first run. ULSD history goes back to
   1986, providing critical seasonal context. The backfill should check
   `BackfillStatus` for prior completion and default to `date(1986, 1, 1)` when
   no prior records exist — same pattern as `FRED_DUBAI_SERIES` in
   `fred_backfill.py` which uses `_SERIES_START` override.
4. **Upsert** rows into `crack_spread_prices` for both symbols.
5. **Join** against existing `FuturesCurve` rows for `CL` (WTI) and `COIL`
   (Brent) by date to compute spreads.
6. **Upsert** results into `Spread` table for the three `spread_type` values.
   Note: `Spread.front_month` and `Spread.back_month` are repurposed here to
   hold product symbols (e.g., `front_month="ULSD"`, `back_month="CL"`) rather
   than calendar months. This is semantically non-standard but works given the
   `UniqueConstraint("date", "spread_type", "front_month")`.

### Function signature

```python
def run_backfill(start_from: date, session) -> int:
    """Returns total crack_spread_prices rows inserted/updated."""
```

---

## Step 3 — BackfillManager Registration

**File:** `backfill/backfill_manager.py`

1. Add `"crack_spread"` to the **`BACKFILL_SOURCES` module-level constant** (not
   to `run_incremental()` directly — that function has no local default list; it
   falls back to `BACKFILL_SOURCES`):

   ```python
   BACKFILL_SOURCES = [
       "fred", "yahoo", "ib_futures", "ib_options", "eia", "gdelt",
       "dated_brent", "scenarios", "spr", "cushing", "crack_spread",  # ← add
   ]
   ```

2. Add a `"crack_spread"` branch in `_get_runner()`:

   ```python
   elif source == "crack_spread":
       from backfill.crack_spread_backfill import run_backfill
       return run_backfill
   ```

**File:** `main.py`

The startup call `bm.run_incremental(sources=["fred", "yahoo", "eia", "cushing"])`
is **explicit** and does NOT fall back to `BACKFILL_SOURCES`. Add `"crack_spread"`
to this list so it runs on every startup:

```python
bm.run_incremental(sources=["fred", "yahoo", "eia", "cushing", "crack_spread"])
```

---

## Step 4 — Scheduler Hook

**File:** `scheduler.py`

Crack spreads derive from FRED data (daily updates, not intraday). The correct
approach is to extend the existing `_run_eia_fred()` function — **not** add a
separate 60-minute interval job (FRED only publishes once daily and the actual
scheduler uses `CronTrigger`, not `"interval"` triggers):

```python
def _run_eia_fred():
    """Scheduled: EIA + FRED weekly data + Dated Brent + crack spreads."""
    # ... existing fred/eia/dated_brent blocks ...

    try:
        from datetime import date
        from db.database import get_session
        from backfill.crack_spread_backfill import run_backfill as crack_backfill
        session = get_session()
        count = crack_backfill(start_from=date.today() - timedelta(days=7), session=session)
        session.close()
        results["crack_spread"] = f"{count} records"
    except Exception as e:
        logger.error(f"Crack spread update failed: {e}")
        results["crack_spread"] = str(e)
```

This runs at **11:00 ET weekdays** via the existing `CronTrigger`, matching how
`dated_brent` is already handled in the same function.

---

## Step 5 — Layout

**New file:** `ui/layouts/crack_spread.py`

### Controls row
- **Date range picker** (`crack-date-range`) — default last 5 years
- **Crack type toggle** (checklist `crack-type-toggle`):
  - Diesel Crack vs WTI *(default selected)*
  - Diesel Crack vs Brent
  - 3-2-1 Crack vs WTI
- **Show seasonal band** checkbox (`crack-seasonal-toggle`)

### Charts (top → bottom)

| Chart ID | Content | Height |
|---|---|---|
| `crack-metrics-row` | 4 metric cards: Diesel Crack (today), 3-2-1 (today), ULSD spot, 5yr avg crack | — |
| `crack-main-chart` | Primary crack spread time series (all selected types, overlaid) | 400 px |
| `crack-seasonal-chart` | Current year vs 5-yr seasonal band | 300 px |
| `crack-components-chart` | Stacked: ULSD $/bbl + WTI $/bbl price history (inputs) | 300 px |
| `crack-distribution-chart` | Histogram of crack spread distribution + percentile marker | 280 px |
| `crack-recent-table` | Last 20 trading days, tabular | — |

---

## Step 6 — Callbacks

**New file:** `ui/callbacks/crack_spread_cb.py`

Single `@callback` with inputs:
```
crack-date-range (start_date, end_date)
crack-type-toggle (value)
crack-seasonal-toggle (value)
auto-refresh (n_intervals)
```

Outputs: all chart figures and table from Step 5.

### Query pattern (mirrors `physical_cb.py`)

```python
def _crack_series(session, spread_type, start, end):
    rows = (session.query(Spread)
            .filter(Spread.spread_type == spread_type,
                    Spread.date >= start,
                    Spread.date <= end)
            .order_by(Spread.date).all())
    return [(r.date, r.spread_value) for r in rows if r.spread_value is not None]
```

Seasonal band computation: group historical values by day-of-year, compute 25th
and 75th percentile per DOY, overlay as filled band on `crack-seasonal-chart`.

---

## Step 7 — Wire Up in app.py

**File:** `ui/app.py`

### 7a — Add tab (after "Supply/Demand", before "Options")

```python
dbc.Tab(label="Crack Spread", tab_id="tab-crack-spread", tab_style=TAB_STYLE),
```

### 7b — Add router case

```python
elif active_tab == "tab-crack-spread":
    from ui.layouts.crack_spread import layout
    return layout
```

### 7c — Register callbacks in `start_app()`

```python
import ui.callbacks.crack_spread_cb
```

---

## Step 8 — Config

**File:** `config.py`

Add FRED series constants (if not already present):

```python
FRED_ULSD_SERIES   = os.getenv("FRED_ULSD_SERIES",   "DHOILNYH")
FRED_RBOB_SERIES   = os.getenv("FRED_RBOB_SERIES",   "GASREGCOVW")
```

---

## File Changeset Summary

| File | Change |
|---|---|
| `db/database.py` | Add `CrackSpreadPrice` model |
| `backfill/crack_spread_backfill.py` | **New** — FRED ULSD + RBOB fetch + spread computation |
| `backfill/backfill_manager.py` | Add `"crack_spread"` to `BACKFILL_SOURCES` constant + `_get_runner()` |
| `main.py` | Add `"crack_spread"` to explicit `run_incremental(sources=[...])` call |
| `scheduler.py` | Extend `_run_eia_fred()` with crack spread refresh block |
| `ui/layouts/crack_spread.py` | **New** — tab layout |
| `ui/callbacks/crack_spread_cb.py` | **New** — all chart callbacks |
| `ui/app.py` | Add tab definition, router case, callback import |
| `config.py` | Add `FRED_ULSD_SERIES`, `FRED_RBOB_SERIES` constants |

---

## Data Availability Notes

- `DHOILNYH` (FRED): daily, starts **1986-01-02** — excellent history
- `GASREGCOVW` (FRED): weekly (Mon), starts **1990-08-27** — sufficient for
  seasonal band; 3-2-1 chart will be weekly resolution
- WTI (`CL`) and Brent (`COIL`) already in `futures_curves` — no new fetch needed
- No new API keys required (uses existing `FRED_API_KEY`)

---

## Testing Checklist

- [ ] `CrackSpreadPrice` table created on `init_db()` with no errors
- [ ] `crack_spread_backfill.run_backfill()` inserts ULSD + RBOB rows
- [ ] `Spread` rows generated for all three `spread_type` values
- [ ] Tab renders without errors when DB is empty (graceful `_empty()` figures)
- [ ] All 3 crack types toggle correctly on the main chart
- [ ] Seasonal band shows/hides via checkbox
- [ ] Metrics cards update on `auto-refresh`
- [ ] `--skip-backfill` flag still works (no crash if crack tables empty)
