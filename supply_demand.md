i want to add a new tab supp./demand
1. supply should be the oil pruduction from countries around the world
2. demand should be the oil consumption from countries around the world.

the tab should show aggregate figures in tables and charts
it should allow users to filter by country
it should allow users to filter by major oil products too: like gasoline, diesel, and other major oil downstream products.

please elaborate on how to collect data and build a UI for it.

---

## Proposal: Supply / Demand Tab

---

### 1. Data Source — EIA International API v2

The same endpoint already used for SPR international data works here. No new API key required.

**Base URL:** `https://api.eia.gov/v2/international/data/`

The two key facets that switch between supply and demand:

| Concept | `activityId` |
|---|---|
| Supply (production) | `1` |
| Consumption (demand) | `2` |

**Product IDs** (the "filter by downstream product" requirement):

| Product | `productId` |
|---|---|
| Total petroleum & other liquids | `5` |
| Crude oil incl. lease condensate | `53` |
| Motor gasoline | `26` |
| Distillate fuel oil (diesel/heating) | `27` |
| Jet fuel / kerosene | `24` |
| Residual fuel oil | `28` |
| LPG & natural gas liquids | `6` |

**Frequency:** monthly (same as SPR international). Values are in **thousand barrels per day (kbd)**.

**Countries to track:**

Major producers (supply focus): SA, RU, US, IQ, AE, IR, KW, NG, LY, VE, CN, BR, CA, MX, NO  
Major consumers (demand focus): US, CN, IN, JP, RU, DE, KR, FR, SA, BR, SG, AU, GB, IT, ES

We store the same set for both — the UI filters by selected view.

---

### 2. Database Schema

Add one new table (mirrors the pattern of `spr_levels`):

```sql
CREATE TABLE IF NOT EXISTS supply_demand (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        DATE    NOT NULL,          -- end-of-month date (same convention as SPR)
    country     TEXT    NOT NULL,          -- ISO-2 code: "US", "SA", "CN", …
    flow        TEXT    NOT NULL,          -- "supply" | "demand"
    product     TEXT    NOT NULL,          -- "total" | "crude" | "gasoline" | "diesel" |
                                           --  "jet_fuel" | "residual" | "lpg"
    value_kbd   REAL    NOT NULL,          -- thousand barrels per day
    source      TEXT    DEFAULT 'EIA',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, country, flow, product)
);
CREATE INDEX IF NOT EXISTS idx_sd_date    ON supply_demand(date);
CREATE INDEX IF NOT EXISTS idx_sd_country ON supply_demand(country);
CREATE INDEX IF NOT EXISTS idx_sd_flow    ON supply_demand(flow);
```

ORM model `SupplyDemand` added to `db/database.py` (same SQLAlchemy pattern as `SprLevel`).

---

### 3. Config Additions (`config.py`)

```python
# ─── Supply / Demand ─────────────────────────────────────────────────────────
SD_PRODUCTS = {
    "total":    {"label": "Total Petroleum",  "eia_product_id": "5"},
    "crude":    {"label": "Crude Oil",        "eia_product_id": "53"},
    "gasoline": {"label": "Gasoline",         "eia_product_id": "26"},
    "diesel":   {"label": "Diesel / Heating", "eia_product_id": "27"},
    "jet_fuel": {"label": "Jet Fuel",         "eia_product_id": "24"},
    "residual": {"label": "Residual Fuel",    "eia_product_id": "28"},
    "lpg":      {"label": "LPG / NGL",        "eia_product_id": "6"},
}

SD_COUNTRIES = {
    # Major producers
    "SA": "Saudi Arabia", "RU": "Russia",   "US": "United States",
    "IQ": "Iraq",         "AE": "UAE",      "IR": "Iran",
    "KW": "Kuwait",       "NG": "Nigeria",  "LY": "Libya",
    "VE": "Venezuela",    "CN": "China",    "BR": "Brazil",
    "CA": "Canada",       "MX": "Mexico",   "NO": "Norway",
    # Additional major consumers
    "IN": "India",  "JP": "Japan",  "DE": "Germany",
    "KR": "S. Korea", "FR": "France", "GB": "UK",
    "IT": "Italy",  "ES": "Spain",  "SG": "Singapore", "AU": "Australia",
}

SD_DEFAULT_COUNTRIES = ["US", "SA", "RU", "CN", "IN"]  # pre-selected in UI
```

---

### 4. Backfill Module (`backfill/supply_demand_backfill.py`)

```python
"""
Supply/Demand Historical Backfill — global oil production & consumption.
Source: EIA API v2 international (/international/data/)
  - activityId=1  →  Supply (production)
  - activityId=2  →  Consumption (demand)
"""

def run_backfill(start_year: int = 2015):
    for flow, activity_id in [("supply", "1"), ("demand", "2")]:
        for product_key, prod_cfg in SD_PRODUCTS.items():
            rows = _fetch_eia_intl(
                activity_id=activity_id,
                product_id=prod_cfg["eia_product_id"],
                country_ids=list(SD_COUNTRIES.keys()),
                start=f"{start_year}-01",
            )
            _upsert(rows, flow, product_key)
```

Each fetch call returns up to 5 000 rows. For 25 countries × 7 products × 2 flows = 350 combinations, the API allows batching all countries in a single request per (flow × product) = 14 requests total. ~10 years of monthly data per request ≈ 3 000 rows per call — comfortably within the limit.

Estimated DB size: ~14 requests × ~2 500 rows = **~35 000 rows total** (small).

---

### 5. UI Layout (`ui/layouts/supply_demand.py`)

```
┌──────────────────────────────────────────────────────────────────┐
│  Controls row                                                    │
│  [Date Range picker]  [Flow: ◉ Supply  ○ Demand  ○ Balance]    │
│  [Product: ▾ Total Petroleum ▾]  [Countries: multi-select]      │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────┐  ┌───────────────────┐
│  KPI cards (auto for selected product)  │  │  World map        │
│  [World Total kbd]  [YoY Δ%]  [War Δ]  │  │  choropleth       │
└─────────────────────────────────────────┘  └───────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Trend Chart — Line chart, one trace per selected country        │
│  X = month,  Y = kbd.  Toggle between absolute and YoY % change │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌───────────────────────────────────────┐
│  Country Bar Chart   │  │  Supply–Demand Balance (if "Balance"  │
│  Latest month ranks  │  │  selected): bar chart  surplus/deficit│
│  Top 15, sorted desc │  │  per country, supply - demand = net   │
└──────────────────────┘  └───────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Data Table                                                      │
│  date | country | product | supply kbd | demand kbd | balance   │
│  sortable, paginated (50/page)                                   │
└──────────────────────────────────────────────────────────────────┘
```

**Control components:**

- `dcc.DatePickerRange` — default `start=2024-01-01`, `end=today`
- `dbc.RadioItems(id="sd-flow")` — options: Supply / Demand / Balance (net)
- `dcc.Dropdown(id="sd-product")` — single-select from `SD_PRODUCTS`
- `dcc.Dropdown(id="sd-countries", multi=True)` — default `SD_DEFAULT_COUNTRIES`
- `dbc.Switch(id="sd-yoy")` — toggle absolute ↔ YoY % on trend chart

---

### 6. Callback Logic (`ui/callbacks/supply_demand_cb.py`)

Single `@callback` drives all outputs from the five control inputs above plus `auto-refresh`.

**Data fetch pattern** (mirrors `spr_cb.py`):
```python
# Pull full history (no start_date filter) for YoY and balance calcs
rows = session.query(SupplyDemand).filter(
    SupplyDemand.country.in_(selected_countries),
    SupplyDemand.product == selected_product,
    SupplyDemand.date <= end_date,
).order_by(SupplyDemand.date).all()
```

**Balance mode:** `balance = supply_kbd − demand_kbd` per (country, month). Positive = surplus, negative = deficit.

**KPI cards (latest available month):**
1. World total kbd for selected product/flow
2. YoY change % vs same month prior year
3. War drawdown: difference vs `WAR_START_DATE` baseline

**Trend chart:** Plotly line chart, one trace per country. If YoY switch ON, convert to `(v_t / v_{t-12} − 1) × 100`.

**Bar chart:** Horizontal bars, latest month only, sorted descending. Color: green (supply) / red (demand) / diverging blue-red (balance).

**Choropleth map:** `px.choropleth` with `locationmode="ISO-3"` (EIA 3-letter codes mapped from our ISO-2 using a lookup dict). Color scale = Viridis for supply/demand, RdBu for balance.

**Data table:** Pivot supply + demand into one row per (date, country, product); compute balance column.

---

### 7. Scheduler Integration (`scheduler.py`)

Add a daily refresh job (EIA international updates monthly, but a daily check is cheap):

```python
scheduler.add_job(
    run_sd_refresh,
    trigger="cron", hour=7, minute=30,
    id="supply_demand_refresh",
)
```

`run_sd_refresh()` fetches only the last 3 months (avoids re-downloading 10 years each day).

---

### 8. Implementation Order

1. `db/schema.sql` + `db/database.py` — add `supply_demand` table & ORM model
2. `config.py` — add `SD_PRODUCTS`, `SD_COUNTRIES`, `SD_DEFAULT_COUNTRIES`
3. `backfill/supply_demand_backfill.py` — write & run once (14 API calls)
4. `ui/layouts/supply_demand.py` — scaffold layout
5. `ui/callbacks/supply_demand_cb.py` — wire callback
6. `ui/app.py` — register new tab
7. `scheduler.py` — add daily refresh job
