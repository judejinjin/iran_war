# Physical Crude Oil Price Data — Research Notes

## Background: Physical vs. Futures Prices

Futures prices (WTI on NYMEX, COIL/Brent on ICE) are standardised exchange-traded
contracts. **Physical crude prices** are what refiners actually pay for delivered barrels
and are assessed by Price Reporting Agencies (PRAs) — primarily **Platts (S&P Global)**
and **Argus Media** — based on reported transactions in the OTC market. Physical prices
typically express as a **differential to a benchmark** (e.g. "Mars at Platts WTI +$2.40").

---

## Major Physical Benchmarks & Delivery Hubs

| Grade | Region | Pricing Basis | Assessed By |
|---|---|---|---|
| **Dated Brent** | North Sea (BFOETM basket) | Self-referential; ~70% of world crude priced off it | Platts (S&P Global) |
| **WTI Midland** | Permian Basin → Cushing OK / MEH TX | Platts WTI MEH/Midland | Platts |
| **LLS (Louisiana Light Sweet)** | US Gulf Coast (LOOP terminal) | Platts LLS vs. WTI | Platts |
| **Mars Blend** | US Gulf Coast (offshore) | Platts Mars vs. WTI | Platts |
| **ASCI** | US Gulf Coast medium sours (Mars, Poseidon, Southern Green Canyon) | Argus Sour Crude Index | Argus |
| **ANS (Alaska North Slope)** | Valdez, AK → West Coast | Platts ANS | Platts |
| **WCS (Western Canadian Select)** | Hardisty, AB | Platts/Argus WCS vs. WTI | Platts / Argus |
| **Dubai / Oman** | Fateh terminal, UAE / Mina al Fahal, Oman | Platts Dubai/Oman window; DME Oman futures | Platts + DME |
| **Murban** | Ruwais, UAE (ADNOC) | Official formula price + IFAD futures (Abu Dhabi) | ADNOC + ICE |
| **Urals (CIF Primorsk / Augusta)** | Baltic/Black Sea loading → NW Europe / Med | Platts Urals CIF Rotterdam/Augusta | Platts |
| **ESPO Blend** | Kozmino, Russia → Asia-Pacific | Platts ESPO CIF China | Platts |
| **Basrah Light / Heavy** | Basrah, Iraq | SOMO OSP (official selling price, formula) | SOMO |
| **Arab Light / Medium / Heavy** | Ras Tanura, Saudi Arabia | Aramco OSP | Saudi Aramco |

---

## Dated Brent — Deep Dive

### What Is Dated Brent?
Dated Brent (also called **North Sea Dated** or BFOETM) is the daily physical spot
price for Brent crude cargoes loading **10–25 days forward** from North Sea fields.
The underlying basket of grades is: **B**rent, **F**orties, **O**seberg, **E**kofisk,
**T**roll, and (since 2022) **M**idland US WTI — hence "BFOETM". It is:

- Assessed by **S&P Global Platts** at ~4:30 PM London time each business day
- Published as a spot price in $/bbl alongside a rolling forward curve
- The reference benchmark for ~70% of global physical crude contracts
- Distinct from the ICE Brent **futures** price (which is a paper/swap contract)

The **Brent Complex spread** — Dated Brent minus ICE Brent 1st nearby — measures
physical tightness vs. paper markets. When physical supply is tight, Dated Brent
trades at a premium (backwardation); when supply is loose it goes to a discount.

### Free Proxies for Dated Brent

The EIA's daily `RBRTE` series and FRED's `DCOILBRENTEU` are **both derived directly
from the Platts Dated Brent assessment**. The EIA surveys Platts and republishes the
figure, typically with a 1–2 day lag. Practically all free "Brent" data is this proxy.

**Status in this codebase:** `DCOILBRENTEU` is fetched via FRED as symbol `COIL` in
`fred_backfill.py` with daily granularity back to 1987. This is the best free
approximation of Dated Brent available without a Platts subscription.

### Lag and Recency
- EIA updates `RBRTE` each evening (target: same business day)
- FRED mirrors EIA with 0–1 additional day lag
- As of the last release date checked (Apr 15, 2026), data runs through Apr 13, 2026
  (2-day lag typical around weekends/holidays)

### To Reduce Lag: Query EIA Directly
Fetching `RBRTED` from the EIA spot price endpoint gives same-day data before FRED
updates, avoiding the extra FRED mirror lag:

```python
import requests
from datetime import date

def fetch_dated_brent_eia(api_key: str, start_date: date) -> list[dict]:
    url = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
    params = {
        "api_key": api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": "RBRTED",
        "start": start_date.isoformat(),
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["response"]["data"]
    # Each item: {"period": "2026-04-16", "value": "123.28", "series": "RBRTED", ...}
```

### Dated Brent vs. ICE Brent Futures (`COIL`) — Key Differences

| Attribute | Dated Brent (physical) | ICE Brent Futures (`COIL`) |
|---|---|---|
| What it is | Assessed physical cargo price | Exchange-traded paper contract |
| Source | Platts assessment (OTC market) | ICE exchange (cleared) |
| Delivery | Physical 10–25 day forward | Cash-settled vs. Brent Index |
| Free proxy | FRED `DCOILBRENTEU` / EIA `RBRTED` | IB TWS live; IB backfill |
| Lag (free) | 1–2 business days | Real-time (IB) / next day (backfill) |

---

## Data Sources — Detailed Breakdown

### 1. EIA Open Data API (Free, daily, 1986–present)
**URL:** `https://api.eia.gov/v2/petroleum/pri/spt/data/`  
**What's available:**
- WTI Cushing spot: series `RWTC` (`EER_EPCWTI_PF4_Y35NY_DPB`) — daily 1986+
- Brent Europe spot (Dated Brent proxy): series `RBRTED` — daily 1987+
- **Nothing else** — no LLS, Mars, Dubai, Urals, etc.

```python
import requests
r = requests.get(
    "https://api.eia.gov/v2/petroleum/pri/spt/data/",
    params={
        "api_key": EIA_API_KEY,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": "RWTC",   # or RBRTED for Dated Brent proxy
        "start": "2024-01-01",
    }
)
```

**Verdict:** Good for WTI and Brent benchmarks only. The `RBRTED` series is the same
underlying Platts assessment as `DCOILBRENTEU` on FRED — already implemented via FRED.
EIA direct endpoint has marginally lower lag (~0–1 day vs. 1–2 for FRED).

---

### 2. FRED (Federal Reserve) API (Free, daily/monthly)
**What's available:**
- `DCOILWTICO` — WTI daily (from EIA, 1986+)
- `DCOILBRENTEU` — Brent daily (from EIA, 1987+)
- `POILDUBUSDM` — **Dubai crude monthly** (from IMF, 1992+) ✅
- `POILWTIUSDM` — WTI monthly (from IMF)
- `POILBREUSDM` — Brent monthly (from IMF)
- `POILAPSPUSDM` — APSP (average of WTI + Brent + Dubai) monthly

```python
from fredapi import Fred
fred = Fred(api_key=FRED_API_KEY)
dubai = fred.get_series("POILDUBUSDM", observation_start="2020-01-01")
```

**Verdict:** Dubai monthly is useful and free — the only free Middle East physical proxy.

---

### 3. IMF Primary Commodity Prices API (Free, monthly)
**URL:** `https://data.imf.org/en/datasets/IMF.RES:PCPS`  
**Crude series included:**
- `POILDUBUSDM` — Dubai (monthly 1992+)
- `POILBREUSDM` — Brent (monthly 1990+)
- `POILWTIUSDM` — WTI (monthly 1990+)
- `POILAPSPUSDM` — APSP average (monthly)

Can access programmatically via IMF JSON API:
```
https://www.imf.org/external/datamapper/api/v1/PCPS/WORLD?periods=POILDUBUSDM
```
Or download the Excel file monthly: `https://www.imf.org/-/media/files/research/commodityprices/monthly/external-data.xls`

**Verdict:** Same Dubai data as FRED, monthly resolution only.

---

### 4. World Bank Pink Sheet (Free, monthly)
**URL:** `https://www.worldbank.org/en/research/commodity-markets`  
**Download:** Monthly XLS at `https://thedocs.worldbank.org/en/.../CMO-Pink-Sheet-{month}-{year}.xlsx`

Includes:
- Crude oil, Brent ($/bbl)
- Crude oil, Dubai ($/bbl)
- Crude oil, WTI ($/bbl)

Monthly only, good for long-run history. No API — must scrape or download manually.

---

### 5. DME (Dubai Mercantile Exchange) — Oman Futures (Free delayed / paid live)
**URL:** `https://www.dubaimerc.com`  
**What it is:** Physically-settled Oman crude futures. The most transparent Middle Eastern
physical crude price. Oman futures are used by ADNOC, Saudi Aramco, and most Gulf
producers to price Asian cargoes.

- **Free:** 30-min delayed quotes on the DME website
- **Paid (live):** Via CME Group DataMine, Bloomberg, Refinitiv
- **Symbol:** `OQD` on CME/DME; sometimes available via IB as `OQD` on DME exchange

**Verdict:** Best Middle East physical proxy if you can get it. Check IB TWS — DME is
accessed through CME's infrastructure so `ib_insync` may reach it.

---

### 6. ICE Futures — Murban Crude (IFAD) (Exchange-traded, free delayed)
**URL:** `https://www.theice.com/products/Oil`  
- ADNOC launched Murban futures in 2021 on ICE (ticker: `MBR`)
- Physically settled at Ruwais, UAE
- Accessible via IB TWS: symbol `MBR`, exchange `ICE`
- Free delayed data; live data requires ICE market data subscription

---

### 7. Platts (S&P Global Commodity Insights) — Paid, Enterprise
**URL:** `https://www.spglobal.com/commodityinsights`  
**What they assess (daily):**
- Dated Brent, BFO (Brent–Forties–Oseberg–Ekofisk), BFOET window
- WTI MEH, WTI Midland, LLS, Mars, Poseidon, Bonito, ANS
- Dubai/Oman, Murban, Upper Zakum, Das, Qatar Marine
- Urals CIF Rotterdam, Urals CIF Augusta
- ESPO CIF China, Sokol, ARCO
- Basrah Light, Iran Heavy, Arab Light/Medium/Heavy

**API:** Platts API v3 (`https://api.ci.spglobal.com`) — requires enterprise subscription.  
**Cost:** Not disclosed publicly; typically $50k–$200k+/year depending on coverage.

```python
# Platts API example (requires API key from S&P Global contract)
import requests
headers = {"appkey": PLATTS_API_KEY}
r = requests.get(
    "https://api.ci.spglobal.com/market-data/reference-data/v3/search",
    headers=headers,
    params={"query": "Dated Brent", "pageSize": 10}
)
```

---

### 8. Argus Media — Paid, Enterprise
**URL:** `https://www.argusmedia.com`  
**Key product: ASCI** (Argus Sour Crude Index) — the primary pricing benchmark for
US Gulf Coast medium-sour crude. Used in ~80% of domestic US sour crude contracts.  
Includes: Mars, Poseidon, Southern Green Canyon daily assessments.

Also covers: Urals, WCS, Basrah, ESPO, Sokol, Iranian grades (when tradeable).  
**API:** Available via enterprise subscription. No public pricing.

---

### 9. Nasdaq Data Link (Quandl) — Mixed free/paid
**URL:** `https://data.nasdaq.com`  
- Most crude price datasets that were free on old Quandl are now paywalled
- Some datasets remain free (e.g. EIA mirror data)
- `OPEC/ORB` — OPEC Reference Basket (free, daily 2003+) ✅

```python
import nasdaqdatalink
nasdaqdatalink.ApiConfig.api_key = NASDAQ_API_KEY  # free tier available
orb = nasdaqdatalink.get("OPEC/ORB", start_date="2020-01-01")
```

**Verdict:** OPEC Reference Basket is a useful free addition — it's a weighted average
of 13 OPEC member crudes and a good proxy for Middle East/heavy sour prices.

---

## Summary: What's Actually Feasible

| Source | Grades | Frequency | Cost | API-Ready |
|---|---|---|---|---|
| EIA API | WTI, Brent | Daily | Free | ✅ |
| FRED API | WTI, Brent, Dubai | Daily / Monthly | Free | ✅ |
| IMF API | WTI, Brent, Dubai, APSP | Monthly | Free | ✅ |
| World Bank Pink Sheet | WTI, Brent, Dubai | Monthly | Free | Manual download |
| Nasdaq Data Link | OPEC Reference Basket | Daily | Free (key needed) |  ✅ |
| DME / IB TWS | Oman futures (physical proxy) | Daily (futures) | IB fee | ✅ via IB |
| ICE Murban (MBR) | Murban (UAE) | Daily (futures) | ICE subscription | ✅ via IB |
| Platts API | Full coverage (20+ grades) | Daily | $$$$ enterprise | ✅ (paid) |
| Argus API | ASCI + 15+ grades | Daily | $$$$ enterprise | ✅ (paid) |

---

## Recommended Implementation for This Project

### Tier 1 — Implement now (free)
1. ✅ **Dated Brent (daily) via FRED** (`DCOILBRENTEU`) — already fetched as symbol `COIL`
   in `fred_backfill.py`; daily 1987+. This is the EIA's republication of the Platts
   Dated Brent assessment and is the industry-standard free proxy.
   - To reduce lag, switch `COIL` backfill to EIA direct (`RBRTED`) instead of FRED;
     identical data, ~0–1 day lag vs. 1–2 for FRED.
2. ✅ **Dubai monthly via FRED** (`POILDUBUSDM`) — added to `fred_backfill.py` as symbol `DUB`;
   stored in `FuturesCurve` with monthly frequency (1992+)
3. **OPEC Reference Basket** via Nasdaq Data Link (`OPEC/ORB`) — good heavy sour proxy
4. **Oman futures via IB TWS** — `symbol="OQD"`, `exchange="DME"` — if IB account has
   CME/DME data package

### Tier 2 — Add later (requires exchange data subscription)
5. **ICE Murban** (`MBR` on ICE) — UAE physical; IB requires ICE bundle
6. ✅ **DME Oman delayed scrape** — implemented in `backfill/dme_backfill.py`;
   scrapes CME Group public settlement page (product ID `DME_CME_PRODUCT_ID=460`)
   for OQD contract months; stores symbol `OQD` in `FuturesCurve` daily.

   > **Note:** DME rebranded to Gulf Mercantile Exchange in 2025; their contracts
   > continue trading on CME Globex infrastructure. If the CME product ID changes,
   > update `DME_CME_PRODUCT_ID` in `config.py`. The scraper will log a clear error
   > on 404/empty-table and return 0 (non-fatal).

### Tier 3 — Enterprise (not feasible without budget)
7. Platts / Argus for true intraday Dated Brent, LLS, Mars, ASCI, Urals, ESPO

### Key Series IDs for Tier 1

| Series | ID | Source | Frequency | History |
|---|---|---|---|---|
| Dated Brent (proxy) | `DCOILBRENTEU` | FRED (via EIA/Platts) | Daily | 1987+ |
| Dated Brent (lower lag) | `RBRTED` | EIA direct API | Daily | 1987+ |
| Dubai crude | `POILDUBUSDM` | FRED (via IMF) | Monthly | 1992+ |
| APSP Average | `POILAPSPUSDM` | FRED (via IMF) | Monthly | 1992+ |
| OPEC Ref Basket | `OPEC/ORB` | Nasdaq Data Link | Daily | 2003+ |

The Brent–Dubai EFS (Exchange of Futures for Swaps) spread is a key signal for
East-West crude flow arbitrage and can be approximated from COIL futures (already
collected) minus the monthly Dubai from FRED.
