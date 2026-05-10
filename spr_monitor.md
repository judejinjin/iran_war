i want to add a SPR tab to monitor strategic oil reserves around the world.
the tab should display an aggregate SPR chart over time as well major SPRs of countries like USA, China, Japan and EU nations.

---

# SPR Monitor — Implementation Proposal

## 1. Overview

A new **SPR** tab added to the existing Dash navigation (between "Physical" and "Options") that tracks Strategic Petroleum Reserve levels for the US, China, Japan, Germany, and a computed OECD aggregate. Given the Iran war context, SPR drawdown rates and remaining days-of-cover are primary signals for how long supply disruptions can be absorbed before they transmit to spot prices — making this directly relevant to the super spike thesis.

---

## 2. Data Sources

All primary sources are **free** and use APIs already integrated or trivially added.

| Country / Region | Source | Series / Endpoint | Frequency | Key Required |
|---|---|---|---|---|
| **USA SPR** | EIA API v2 | `PET.WCSSTUS1.W` (Strategic Petroleum Reserve stocks, Mbbl) | Weekly | `EIA_API_KEY` (already in `.env`) |
| **USA Commercial** | EIA API v2 | `PET.WCESTUS1.W` (commercial crude stocks, Mbbl) | Weekly | `EIA_API_KEY` |
| **OECD Total Stocks** | JODI Data API | `https://www.jodidata.org/api/` — product=`CRUDEOIL`, flow=`STOCKS`, country=OECD members | Monthly | None (free, no key) |
| **Japan SPR** | JODI Data API | country=`JPN`, flow=`GOVTSTOCKS` | Monthly | None |
| **China SPR** | JODI Data API | country=`CHN`, flow=`GOVTSTOCKS` | Monthly | None |
| **Germany / EU** | JODI Data API | country=`DEU` + `FRA` + `ITA` + `ESP` + `NLD`, flow=`GOVTSTOCKS` | Monthly | None |
| **IEA Days of Cover** | IEA Oil Market Report (PDF scrape / press release page) | Fallback: compute from EIA stocks ÷ 90-day avg consumption | Monthly | None |

> **JODI** (Joint Organisations Data Initiative) is a free, UN-backed oil statistics database. API docs: https://www.jodidata.org/api/. No key required, returns JSON.  
> **Days of Cover** (US) can be computed directly: `SPR_stock_Mbbl / (US_consumption_kbd / 1000)`.

---

## 3. Database Schema

Add one new table to `db/schema.sql` and a matching SQLAlchemy ORM model in `db/database.py`:

```sql
-- db/schema.sql (append)
CREATE TABLE IF NOT EXISTS spr_levels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE    NOT NULL,
    country_code    TEXT    NOT NULL,   -- 'US', 'CN', 'JP', 'DE', 'FR', 'IT', 'ES', 'NL', 'OECD'
    country_name    TEXT    NOT NULL,
    spr_mbbl        REAL,              -- government / strategic stock in million barrels
    commercial_mbbl REAL,              -- commercial crude stocks (US only from EIA)
    total_mbbl      REAL,              -- spr + commercial combined
    days_of_cover   REAL,              -- spr_mbbl / avg_daily_consumption
    source          TEXT    NOT NULL,  -- 'EIA', 'JODI', 'computed'
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, country_code)
);
```

**ORM model** (`db/database.py`):
```python
class SprLevel(Base):
    __tablename__ = "spr_levels"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    date            = Column(Date, nullable=False)
    country_code    = Column(Text, nullable=False)
    country_name    = Column(Text, nullable=False)
    spr_mbbl        = Column(Float)
    commercial_mbbl = Column(Float)
    total_mbbl      = Column(Float)
    days_of_cover   = Column(Float)
    source          = Column(Text, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    __table_args__  = (UniqueConstraint("date", "country_code"),)
```

---

## 4. New Modules

### 4.1 `backfill/spr_backfill.py`

Pattern matches `backfill/eia_backfill.py`. Fetches historical SPR data from war start date.

```
def run_backfill(start_from: date, session) -> int:
    - Call EIA v2 API for WCSSTUS1 (US SPR) and WCESTUS1 (US commercial) from start_from
    - Call JODI API for JP, CN, DE, FR, IT, ES, NL government stocks from start_from
    - Compute total_mbbl and days_of_cover for US rows
    - Upsert into spr_levels with INSERT OR REPLACE
    - Return total records inserted
```

Register in `backfill/backfill_manager.py`:
```python
BACKFILL_SOURCES = [...existing..., "spr"]
```

### 4.2 `collectors/spr_collector.py`

Runs on the daily scheduler (once per day, after market close). Fetches the latest week's EIA release (published every Wednesday) and most recent JODI monthly update.

```
def collect_latest() -> int:
    - Fetch last 4 weeks of EIA WCSSTUS1 and WCESTUS1 (to catch any revisions)
    - Fetch JODI latest month for all countries
    - Upsert into spr_levels
    - Return count of new/updated rows
```

Register in `scheduler.py` — daily at 18:30 ET (after EIA weekly petroleum status report release at 10:30 ET):
```python
scheduler.add_job(spr_collector.collect_latest, "cron", hour=18, minute=30, id="spr_daily")
```

### 4.3 `ui/layouts/spr.py`

Follows the exact same structure as `ui/layouts/futures.py` — dark theme, `dbc.Container`, card-based sections, `dcc.DatePickerRange` for filtering.

**Layout structure:**
```
┌──────────────────────────────────────────────────────────────┐
│  Controls: Date Range | Country Filter (checklist)           │
├──────────────────────────────────────────────────────────────┤
│  Key Metrics Row: US SPR | OECD Total | Days of Cover (US)  │
│                   US Δ 1W | US Δ 1M                         │
├──────────────────────────────────────────────────────────────┤
│  [Left 8col] SPR Levels Over Time — line chart               │
│              One line per selected country; y-axis = Mbbl    │
│  [Right 4col] Days of Cover — line chart (US SPR ÷ demand)  │
├──────────────────────────────────────────────────────────────┤
│  [Left 6col] US SPR + Commercial Stocks — stacked bar chart  │
│              Highlights cumulative drawdown from war start   │
│  [Right 6col] Country Comparison — latest snapshot bar chart │
│               Countries ranked by SPR level (Mbbl)           │
├──────────────────────────────────────────────────────────────┤
│  Data Table: date | country | SPR Mbbl | Δ1W | Δ1M | source │
└──────────────────────────────────────────────────────────────┘
```

**Key component IDs:**
- `spr-date-range` — DatePickerRange
- `spr-country-filter` — Checklist: `["US", "CN", "JP", "DE", "FR", "IT", "OECD"]`
- `spr-metrics-row` — key metric cards
- `spr-levels-chart` — main time-series line chart
- `spr-days-cover-chart` — days of cover line chart
- `spr-us-stacked-chart` — US SPR + commercial stacked bars
- `spr-snapshot-chart` — latest cross-country bar chart
- `spr-data-table` — DataTable

### 4.4 `ui/callbacks/spr_cb.py`

Single `@callback` driven by `spr-date-range`, `spr-country-filter`, `auto-refresh`:

```python
@callback(
    Output("spr-metrics-row", "children"),
    Output("spr-levels-chart", "figure"),
    Output("spr-days-cover-chart", "figure"),
    Output("spr-us-stacked-chart", "figure"),
    Output("spr-snapshot-chart", "figure"),
    Output("spr-data-table", "data"),
    Input("spr-date-range", "start_date"),
    Input("spr-date-range", "end_date"),
    Input("spr-country-filter", "value"),
    Input("auto-refresh", "n_intervals"),
)
def update_spr(start_date, end_date, countries, _n):
    # Query spr_levels filtered by date range and country_code IN countries
    # Build all 5 outputs
    # Compute Δ1W / Δ1M diffs for metrics cards and table
```

---

## 5. Integration Points

### `ui/app.py` — add tab
```python
dbc.Tab(label="SPR", tab_id="tab-spr", tab_style=TAB_STYLE),
# Add between "Physical" and "Options"
```

Add to `render_tab()`:
```python
elif active_tab == "tab-spr":
    from ui.layouts.spr import layout
    return layout
```

### `ui/callbacks/__init__.py`
```python
from ui.callbacks import spr_cb  # noqa
```

### `config.py` — add EIA SPR series constants
```python
EIA_SPR_SERIES        = "PET.WCSSTUS1.W"   # US Strategic Petroleum Reserve, weekly Mbbl
EIA_COMMERCIAL_SERIES = "PET.WCESTUS1.W"   # US commercial crude stocks, weekly Mbbl
JODI_API_BASE         = "https://www.jodidata.org/api/data/"
SPR_COUNTRIES = {
    "US":   "United States",
    "CN":   "China",
    "JP":   "Japan",
    "DE":   "Germany",
    "FR":   "France",
    "IT":   "Italy",
    "ES":   "Spain",
    "NL":   "Netherlands",
    "OECD": "OECD Aggregate",
}
```

---

## 6. Key Metrics & Analytical Value

| Metric | Computation | Why It Matters |
|---|---|---|
| **US SPR Level** | Latest `spr_mbbl` where `country_code = 'US'` | Absolute buffer; currently ~350 Mbbl post-Biden drawdowns |
| **US Days of Cover** | `spr_mbbl / (US_demand_kbd / 1000)` | IEA emergency threshold = 90 days; below 60 = critical |
| **Cumulative War Drawdown** | `spr_mbbl(today) − spr_mbbl(WAR_START_DATE)` | How much buffer has been consumed since the conflict began |
| **OECD Total** | Sum across OECD `spr_mbbl` | Headline number cited by IEA in emergency releases |
| **Drawdown Rate (Δ/week)** | Rolling 4-week average weekly change | Extrapolates how many weeks until a critical threshold is breached |
| **China SPR Estimate** | JODI `CHN` government stocks | China SPR releases are a major unknown; JODI lags ~2 months but provides best public estimate |

---

## 7. Files to Create / Modify

| Action | File |
|---|---|
| **Create** | `backfill/spr_backfill.py` |
| **Create** | `collectors/spr_collector.py` |
| **Create** | `ui/layouts/spr.py` |
| **Create** | `ui/callbacks/spr_cb.py` |
| **Modify** | `db/schema.sql` — add `spr_levels` table |
| **Modify** | `db/database.py` — add `SprLevel` ORM model |
| **Modify** | `backfill/backfill_manager.py` — register `"spr"` source |
| **Modify** | `scheduler.py` — add daily SPR collector job |
| **Modify** | `config.py` — add SPR series IDs and `SPR_COUNTRIES` dict |
| **Modify** | `ui/app.py` — add SPR tab + router entry |
| **Modify** | `ui/callbacks/__init__.py` — import `spr_cb` |
