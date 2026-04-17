# Downloading Historical Options Data via IBKR API

## 1. Contract Type: FOP (Futures Option), NOT OPT

CL and COIL are **futures**. Options on futures use security type **`FOP`** (Futures Option), not `OPT` (equity option).

In `ib_insync`:

```python
from ib_insync import FuturesOption

# CL option on NYMEX
opt = FuturesOption(
    symbol="CL",
    lastTradeDateOrContractMonth="20250718",  # YYYYMMDD expiry
    strike=65.0,
    right="C",           # "C" or "P"
    exchange="NYMEX",
    multiplier="1000",   # CL = 1000 bbl
    currency="USD",
)

# COIL option on IPE
opt = FuturesOption(
    symbol="COIL",
    lastTradeDateOrContractMonth="20250630",
    strike=72.0,
    right="P",
    exchange="IPE",
    currency="USD",
)
```

> **Note**: The existing `collectors/ib_options.py` uses `Option()` (secType=OPT). This works because `qualifyContracts()` resolves it, but `FuturesOption()` (secType=FOP) is the correct and unambiguous contract type for options on futures.

---

## 2. Discovering Available Chains: `reqSecDefOptParams()`

Already used in `collectors/ib_options.py`. Returns `OptionChain` objects with:

| Field | Description |
|-------|-------------|
| `exchange` | Exchange where options trade (e.g. "NYMEX", "IPE") |
| `underlyingConId` | conId of the underlying future |
| `tradingClass` | Trading class string (important for disambiguation) |
| `multiplier` | Contract multiplier (e.g. "1000" for CL) |
| `expirations` | List of expiry strings in `YYYYMMDD` format |
| `strikes` | List of available strike prices (floats) |

### Workflow

```python
# 1. Qualify the underlying future
und = Future(symbol="CL", exchange="NYMEX")
ib.qualifyContracts(und)

# 2. Get option chain metadata
chains = ib.reqSecDefOptParams(
    underlyingSymbol=und.symbol,
    futFopExchange="",              # leave blank to get all exchanges
    underlyingSecType=und.secType,  # "FUT"
    underlyingConId=und.conId,
)

# 3. Pick the relevant chain (usually the one with most expirations on correct exchange)
chain = [c for c in chains if c.exchange == "NYMEX"]
chain = max(chain, key=lambda c: len(c.expirations))

# 4. Enumerate: expirations × relevant_strikes × rights
expirations = sorted(chain.expirations)[:12]  # first 12 expiries
strikes = sorted(chain.strikes)
# Filter to strikes divisible by 10, within -50% to +200% of underlying
relevant_strikes = [s for s in strikes if und_price * 0.5 <= s <= und_price * 3.0 and s % 10 == 0]
```

### Computing Exact Contract Tickers

For each combination `(expiry, strike, right)`:

```python
contract = FuturesOption(
    symbol="CL",
    lastTradeDateOrContractMonth=expiry,   # "20250718"
    strike=strike,                          # 65.0
    right=right,                            # "C" or "P"
    exchange=chain.exchange,                # "NYMEX"
    multiplier=chain.multiplier,            # "1000"
    tradingClass=chain.tradingClass,        # from reqSecDefOptParams
    currency="USD",
)
qualified = ib.qualifyContracts(contract)
# If qualified is empty, the (expiry, strike) combo doesn't have a valid contract
```

> **Important**: `reqSecDefOptParams()` returns the Cartesian product of all expirations and all strikes, but not every combination is a valid contract. Always call `qualifyContracts()` to verify. Invalid combos will fail to qualify (empty list returned).

---

## 3. `reqHistoricalData()` for Option/FOP Contracts

### Available `whatToShow` Values

Per IB's "Available Data per Product" table:

| whatToShow | Options (OPT) | FOPs |
|------------|:---:|:---:|
| **TRADES** | ✅ | ✅ |
| **MIDPOINT** | ✅ | ✅ |
| **BID** | ✅ | ✅ |
| **ASK** | ✅ | ✅ |
| **BID_ASK** | ✅ | ✅ |
| HISTORICAL_VOLATILITY | ❌ | ❌ |
| OPTION_IMPLIED_VOLATILITY | ❌ | ❌ |
| ADJUSTED_LAST | ❌ | ❌ |

**CRITICAL**: `OPTION_IMPLIED_VOLATILITY` and `HISTORICAL_VOLATILITY` are **NOT available** for options or FOPs. They only work for stocks, ETFs, and indices. This means **IB does not return IV bars directly for option contracts**. You get OHLCV price bars only.

### Example Request

```python
bars = ib.reqHistoricalData(
    contract=qualified_option,
    endDateTime="",                      # current moment
    durationStr="6 M",                   # up to 6 months back
    barSizeSetting="1 day",              # daily bars
    whatToShow="TRADES",                 # or "BID_ASK" (counts as 2 requests)
    useRTH=True,
    formatDate=1,
)

for bar in bars:
    print(bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume)
```

### What the Bars Contain

For `whatToShow="TRADES"`:
- `bar.date` — date (for daily bars, YYYYMMDD)
- `bar.open` — first trade price
- `bar.high` — highest trade price
- `bar.low` — lowest trade price
- `bar.close` — last trade price (or settlement price for EOD)
- `bar.volume` — total traded volume
- `bar.barCount` — number of trades
- `bar.average` — VWAP

For `whatToShow="BID_ASK"`:
- `bar.open` — time-average bid
- `bar.high` — max ask (confusing naming)
- `bar.low` — min bid
- `bar.close` — time-average ask
- `bar.volume` — N/A

---

## 4. Critical Limitations

### 4a. No Expired Options/FOPs Historical Data

From IB's documentation:

> **Unavailable Historical Data:**
> - Expired options, FOPs, warrants and structured products.
> - End of Day (EOD) data for options, FOPs, warrants and structured products.

This means:
- You can **only** get historical data for **currently listed** (non-expired) options
- Once an option expires, its historical data becomes permanently unavailable
- You **cannot** backfill historical data for options that have already expired
- The "EOD data unavailable" note refers specifically to the daily summary/settlement bars — intraday bars for active options ARE available

### 4b. No Implied Volatility in Historical Bars

Since `OPTION_IMPLIED_VOLATILITY` is not available for FOPs, you must **compute IV yourself** from the option prices. Methods:

1. **`calculateImpliedVolatility(contract, optionPrice, underPrice)`** — IB's built-in calculator. Works for a single point in time. Not usable for historical bars.

2. **Black-76 model** — The standard pricing model for options on futures. Given the option close price, underlying future close price, strike, time to expiry, and risk-free rate, solve for the volatility parameter. This is what we need for historical bars.

### 4c. Pacing Rules

| Rule | Limit |
|------|-------|
| Max simultaneous open requests | 50 |
| Max requests per 10 minutes | 60 |
| `BID_ASK` requests | Count as **2** requests each |
| Identical request within 15 seconds | Pacing violation |

**Impact calculation** for our use case:
- 2 symbols (CL, COIL) × 12 expiries × ~18 strikes (divisible by 10, -50%/+200%) × 2 rights = **~864 option contracts**
- At 60 req/10 min = **~145 minutes** to download all daily bars for all contracts
- With BID_ASK (counting double): **~290 minutes**

### 4d. Duration Limits

For daily bars (`1 day`), valid durations:
- `1 D` through `1 Y`
- Since expired FOPs data is unavailable, the effective lookback is limited to how long the option has been listed (typically a few months for near-term expiries)

---

## 5. Recommended Approach: Tiered Strategy

Since we cannot backfill expired options and IV is not directly available, the best approach is:

### Tier 1: Daily Snapshot Collection (Primary — current approach in `ib_options.py`)

Continue using `reqMktData()` snapshots to capture live Greeks/IV 3×/day. This is the only way to get IB-computed IV and Greeks. Data accumulates day-by-day.

### Tier 2: Historical Price Backfill for Active Options

For currently listed options only:

```
For each symbol (CL, COIL):
  1. reqSecDefOptParams() → get expirations + strikes
   2. Filter to front 12 expiries, strikes divisible by 10 within -50%/+200%
  3. For each (expiry, strike, right):
     a. FuturesOption(...) → qualifyContracts()
     b. reqHistoricalData(whatToShow="TRADES", duration="6 M", bar="1 day")
     c. Save bars: date, close_price, volume
     d. Compute IV via Black-76 using:
        - option_close_price (from bar)
        - underlying_close_price (from futures_daily table)
        - strike, time_to_expiry, risk_free_rate
     e. Compute delta, gamma, vega, theta via Black-76
     f. Store in options_chains table
  4. Respect pacing: batch 6 requests, wait 65 seconds
```

### Tier 3: OPTION_IMPLIED_VOLATILITY on Underlying (ATM IV History)

Although `OPTION_IMPLIED_VOLATILITY` doesn't work on FOPs, it **does** work on **Stocks and Indices**. As a workaround, you can request it on an **oil ETF** (e.g., USO) or check if it works on the future itself (worth testing — the IB table says "N" for futures, but some users report it works on certain futures).

```python
# Worth testing — may work despite documentation saying N
bars = ib.reqHistoricalData(
    contract=Future("CL", "NYMEX"),
    endDateTime="",
    durationStr="1 Y",
    barSizeSetting="1 day",
    whatToShow="OPTION_IMPLIED_VOLATILITY",
    useRTH=True,
    formatDate=1,
)
```

If this works, it gives the **ATM implied volatility history** of the underlying, which can populate the `atm_vol` field in the `vol_surface` table — a huge win for minimal API calls.

---

## 6. Black-76 IV Computation

For options on futures, the Black-76 model is standard. The formula:

```
C = e^(-rT) [F·N(d1) - K·N(d2)]
P = e^(-rT) [K·N(-d2) - F·N(-d1)]

d1 = [ln(F/K) + (σ²/2)T] / (σ√T)
d2 = d1 - σ√T
```

Where:
- F = futures price (underlying close)
- K = strike price
- T = time to expiry in years
- r = risk-free rate
- σ = implied volatility (solve for this)
- N() = standard normal CDF

Use `scipy.optimize.brentq` to solve for σ given the market option price.

```python
from scipy.optimize import brentq
from scipy.stats import norm
import math

def black76_price(F, K, T, r, sigma, option_type="C"):
    d1 = (math.log(F / K) + 0.5 * sigma**2 * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    df = math.exp(-r * T)
    if option_type == "C":
        return df * (F * norm.cdf(d1) - K * norm.cdf(d2))
    else:
        return df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))

def implied_vol_black76(market_price, F, K, T, r, option_type="C"):
    if market_price <= 0 or T <= 0:
        return None
    try:
        iv = brentq(
            lambda sigma: black76_price(F, K, T, r, sigma, option_type) - market_price,
            0.001, 5.0  # search between 0.1% and 500% vol
        )
        return iv
    except (ValueError, RuntimeError):
        return None
```

---

## 7. Implementation Plan

### File: `backfill/ib_options_backfill.py`

```
def run_backfill(start_from, session):
    1. Connect via IBConnection
    2. For each symbol in FUTURES_SYMBOLS:
       a. Qualify underlying Future
       b. Get current underlying price (last close from futures_daily table)
       c. reqSecDefOptParams() → chains
       d. Pick front 12 expiries, filter strikes divisible by 10 within -50%/+200%
       e. For each (expiry, strike, right):
          - Build FuturesOption contract
          - qualifyContracts() — skip if fails
          - reqHistoricalData(whatToShow="TRADES", duration="6 M", bar="1 day")
          - For each daily bar:
            * Look up underlying close from futures_daily for that date
            * Compute IV via Black-76
            * Compute Greeks (delta, gamma from Black-76)
            * Upsert into options_chains
          - Pacing: batch 6 requests, sleep 65s between batches
       f. Compute vol_surface entries from collected IVs
    3. Commit session
```

### Estimated Runtime

| Parameter | Value |
|-----------|-------|
| Symbols | 2 (CL, COIL) |
| Expiries | 12 per symbol |
| Strikes (filtered) | ~18 per expiry (divisible by 10, -50%/+200%) |
| Rights | 2 (C, P) |
| Total contracts | ~864 |
| Requests per 10 min | 60 |
| **Estimated total time** | **~145 minutes** |

### Wire into backfill_manager.py

```python
BACKFILL_SOURCES = [..., "ib_options"]

# In _get_runner():
elif source == "ib_options":
    from backfill.ib_options_backfill import run_backfill
    return run_backfill
```

---

## 8. Summary of Key Findings

| Question | Answer |
|----------|--------|
| Contract type for CL/COIL options? | `FOP` (FuturesOption) |
| Can we get IV bars directly? | **No** — `OPTION_IMPLIED_VOLATILITY` not available for FOPs |
| Can we get price bars? | **Yes** — TRADES, BID, ASK, BID_ASK, MIDPOINT |
| Can we backfill expired options? | **No** — expired FOPs historical data unavailable |
| How to compute IV? | Black-76 model from option price + underlying close |
| Pacing constraint? | 60 req/10 min; ~145 min for full chain of both underlyings |
| `reqSecDefOptParams()` → contract construction? | chain gives expirations + strikes + tradingClass + multiplier → `FuturesOption(symbol, expiry, strike, right, exchange, multiplier, tradingClass)` |
| How deep is historical data? | Only the life of the current contract; no expired FOPs data |
