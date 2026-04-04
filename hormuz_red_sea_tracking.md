# Hormuz & Red Sea / Bab el-Mandeb Traffic Tracking

## Current State Assessment

### Strait of Hormuz — IMPLEMENTED (news-derived)

We already track Hormuz daily via the `HormuzStatus` table, driven by `shipment_disruption` news events:

| What We Have | How It Works |
|---|---|
| **Daily status** (`open` / `restricted` / `partial_blockade` / `full_blockade`) | Computed from avg severity of `shipment_disruption` events |
| **Oil transit volume** (mbd) | `21.0 × (1 - reduction_pct)` — currently showing 6.30 mbd blocked |
| **LNG transit volume** (bcf/d) | `16.0 × (1 - reduction_pct)` |
| **War risk insurance %** | Field exists, populated from news extraction |
| **Tanker diversions count** | Field exists, populated from news extraction |
| **Naval incidents count** | Field exists, populated from news extraction |
| **Slow-recovery logic** | -2% reduction per day if no new incidents |
| **UI panel** | Dedicated "Strait of Hormuz Transit Status" card on Infrastructure tab |
| **Bypass pipelines seeded** | Jask (1.0 mbd), Yanbu (4.5 mbd), Fujairah (2.0 mbd) as facilities |

**Limitations:**
- Entirely news-derived — no real-time vessel position data
- `tanker_diversions` and `naval_incidents` come from Claude's interpretation of headlines, not AIS telemetry
- Bypass pipelines tracked as individual facilities, not as a unified "bypass capacity" metric
- All `shipment_disruption` events assumed to be Hormuz-related — no geographic filtering

### Bab el-Mandeb / Red Sea — NOT IMPLEMENTED

Zero chokepoint tracking exists for:
- **Bab el-Mandeb Strait** (~4.8 mbd oil, ~3.5% of global seaborne trade)
- **Suez Canal** (~5.5 mbd oil + ~2 bcf/d LNG)
- **Red Sea shipping lanes** as a tracked entity

The only Red Sea reference is Yanbu Terminal's region field = "Red Sea" in the facility seed.

---

## What We Need — Implementation Plan

### Phase 1: Generalized Chokepoint Model

Replace the Hormuz-only `HormuzStatus` table with a general `ChokePointStatus` model that supports multiple straits.

**New/modified DB table:**

```python
class ChokepointStatus(Base):
    __tablename__ = "chokepoint_status"

    id                      = Column(Integer, primary_key=True)
    chokepoint              = Column(Text, nullable=False)   # "hormuz" | "bab_el_mandeb" | "suez"
    date                    = Column(Date, nullable=False)
    status                  = Column(Text, nullable=False)   # open | restricted | partial_blockade | full_blockade
    oil_transit_mbd         = Column(Float)
    lng_transit_bcfd        = Column(Float)
    normal_oil_mbd          = Column(Float)                  # hormuz=21.0, bab_el_mandeb=4.8, suez=5.5
    normal_lng_bcfd         = Column(Float)                  # hormuz=16.0, bab_el_mandeb=0.4, suez=2.0
    reduction_pct           = Column(Float, default=0.0)
    insurance_war_risk_pct  = Column(Float)
    tanker_diversions       = Column(Integer, default=0)
    naval_incidents         = Column(Integer, default=0)
    summary_text            = Column(Text)
    created_at              = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("chokepoint", "date"),)
```

**Chokepoint baseline constants:**

| Chokepoint | Normal Oil (mbd) | Normal LNG (bcf/d) | Key Actors |
|---|---|---|---|
| Hormuz | 21.0 | 16.0 | Iran (IRGN), IRGC naval mines |
| Bab el-Mandeb | 4.8 | 0.4 | Houthis (anti-ship missiles, drones, boat bombs) |
| Suez Canal | 5.5 | 2.0 | Egypt (administrative), spillover from Bab el-Mandeb |

**Migration:** Rename `hormuz_status` → `chokepoint_status`, add `chokepoint` column, backfill existing rows with `chokepoint="hormuz"`.

**Effort:** ~1 hour. Straightforward schema change + update references in `production_tracker.py`, `infrastructure_cb.py`, `seed_baselines.py`.

---

### Phase 2: Geographic Event Routing

Currently all `shipment_disruption` events feed into Hormuz status. We need geographic filtering to route events to the correct chokepoint.

**Approach — coordinate bounding boxes:**

```python
CHOKEPOINT_BOUNDS = {
    "hormuz": {
        "lat_min": 24.0, "lat_max": 27.5,
        "lon_min": 54.0, "lon_max": 58.0,
        "keywords": ["hormuz", "persian gulf", "strait of hormuz", "oman coast",
                     "IRGC naval", "iranian navy", "tanker seized"],
    },
    "bab_el_mandeb": {
        "lat_min": 11.5, "lat_max": 15.0,
        "lon_min": 42.0, "lon_max": 45.0,
        "keywords": ["bab el-mandeb", "bab al-mandab", "red sea", "houthi",
                     "ansar allah", "yemen", "aden gulf", "gulf of aden",
                     "mocha", "djibouti strait"],
    },
    "suez": {
        "lat_min": 29.5, "lat_max": 31.5,
        "lon_min": 32.0, "lon_max": 33.0,
        "keywords": ["suez canal", "suez blockade", "port said", "ismailia"],
    },
}
```

**Routing logic in `update_chokepoint_status()`:**
1. For each `shipment_disruption` event on the target date:
   - If event has lat/lon → match by bounding box
   - Else → match by keyword search in headline + summary
   - Default to `hormuz` if ambiguous (most Gulf-war events are Hormuz)
2. Aggregate severity per chokepoint separately
3. Update each chokepoint's reduction_pct independently

**Effort:** ~2 hours. Modify `update_hormuz_status()` → `update_chokepoint_statuses()`, add keyword/geo routing, update daily status pipeline.

---

### Phase 3: Enhanced News Collection for Red Sea

Current `NEWS_KEYWORDS` in config.py are heavily Hormuz/Iran-focused. Need Red Sea/Houthi keywords.

**Add to NEWS_KEYWORDS:**

```python
# Red Sea / Bab el-Mandeb / Houthi
"Bab el-Mandeb", "Red Sea attack", "Houthi ship", "Houthi tanker",
"Ansar Allah", "Yemen naval", "Red Sea shipping", "Gulf of Aden",
"Suez Canal disruption", "Red Sea insurance", "Cape of Good Hope diversion",
"Red Sea military", "Houthi drone ship", "Houthi missile ship",
```

**Also update the Claude classification prompt** in `geopolitical_agent.py` to:
- Distinguish Hormuz vs Red Sea vs Suez disruptions in the `location_name` field
- Extract the chokepoint name if the event involves a strait/shipping lane

**Effort:** ~30 min. Config change + prompt tweak.

---

### Phase 4: UI — Multi-Chokepoint Dashboard

Expand the Infrastructure tab's Hormuz panel to show all chokepoints.

**Option A — Tabbed cards** (one card per chokepoint, tabs to switch):
```
[Hormuz] [Bab el-Mandeb] [Suez]
┌──────────────────────────────────────┐
│ Status: PARTIAL BLOCKADE             │
│ Oil Transit: 2.4 / 4.8 mbd (50%)    │
│ LNG Transit: 0.2 / 0.4 bcf/d        │
│ War Risk Premium: 3.2%               │
│ Diversions: 12 tankers               │
│ Incidents: 4                         │
│ AI Summary: "Houthi anti-ship..."    │
└──────────────────────────────────────┘
```

**Option B — Side-by-side summary** (all three visible at once):
```
┌─────────────┬─────────────┬─────────────┐
│   HORMUZ    │ BAB EL-MANDEB│    SUEZ     │
│ RESTRICTED  │ PART.BLOCKADE│    OPEN     │
│ 14.7/21 mbd│  2.4/4.8 mbd│  5.5/5.5 mbd│
│ ▼ 30%      │  ▼ 50%      │  ▼ 0%       │
└─────────────┴─────────────┴─────────────┘
```

**Also add:**
- Time-series chart of all three chokepoints' `reduction_pct` over time
- Map markers for each chokepoint on the Leaflet map (with status-colored icons)

**Effort:** ~2 hours. Layout + callback updates.

---

### Phase 5 (Optional): Real Vessel Tracking APIs

News-derived chokepoint status has inherent delay (hours to a day). For real-time awareness:

| Data Source | What It Provides | Cost | API Access |
|---|---|---|---|
| **MarineTraffic** | AIS positions, port calls, vessel count per strait, transit times | Free tier: 100 credits/mo. Pro: $150+/mo | REST API, requires subscription |
| **VesselFinder** | AIS positions, vessel counts by region/chokepoint | Free: limited. Basic: $49/mo | REST API |
| **Kpler** | Oil & LNG cargo tracking, floating storage, real flows by chokepoint | Enterprise only (~$30K+/yr) | REST API, negotiated access |
| **Vortexa** | Real-time tanker tracking, crude-by-crude cargo flows | Enterprise (~$50K+/yr) | REST API |
| **UN Comtrade** | Monthly trade flow statistics by commodity & partner | Free | REST API (delayed 2-3 months) |
| **Suez Canal Authority** | Daily transit count & tonnage reports | Free (PDF reports) | No API — web scraping required |
| **Lloyd's List Intelligence** | War risk premiums, daily transit counts, vessel diversions | Subscription | Portal + limited API |
| **SpaceKnow** | Satellite imagery of port congestion, floating storage | Enterprise | REST API |

**Recommended affordable option:** MarineTraffic or VesselFinder basic tier ($49-150/mo) for:
- Hourly vessel counts transiting each chokepoint (via geofence zone)
- Transit time trends (longer transit = avoidance behavior)
- Tanker draft readings at key ports (proxy for export volumes)

**Integration approach:**
```python
# collectors/vessel_tracker.py
def get_chokepoint_traffic(chokepoint: str) -> dict:
    """Poll MarineTraffic API for vessel counts in chokepoint geofence."""
    zone = CHOKEPOINT_GEOFENCES[chokepoint]
    resp = requests.get(
        "https://services.marinetraffic.com/api/exportvessels/v:8",
        params={
            "MINLAT": zone["lat_min"], "MAXLAT": zone["lat_max"],
            "MINLON": zone["lon_min"], "MAXLON": zone["lon_max"],
            "SHIP_TYPE": 6,  # tankers only
            "apikey": MARINETRAFFIC_KEY,
        }
    )
    vessels = resp.json()
    return {
        "tanker_count": len(vessels),
        "avg_speed_knots": mean(v["SPEED"] for v in vessels) / 10,
        "timestamp": datetime.utcnow(),
    }
```

**Effort:** ~4 hours for basic integration. Requires API subscription.

---

### Phase 6 (Optional): Cape of Good Hope Diversion Metric

When Bab el-Mandeb is disrupted, tankers divert around Africa's Cape of Good Hope, adding:
- **~10-14 days** to Europe-bound shipments from the Gulf
- **~$1M+** extra fuel cost per VLCC round trip
- **~3-5 mbd** effective supply delay (oil still arrives, just later)

Track this as a derived metric:
```python
cape_diversion_active = bab_el_mandeb_status in ("partial_blockade", "full_blockade")
effective_delay_days = 12 if cape_diversion_active else 0
extra_freight_cost_per_barrel = 2.50 if cape_diversion_active else 0.0  # $/bbl
tankers_on_long_route = bab_el_mandeb.tanker_diversions  # from news or AIS
```

This feeds into the economic model — delayed supply acts like a mini shortage even though production isn't physically offline.

**Effort:** ~1 hour. Add fields to `ChokepointStatus` or a separate diversion table.

---

## Summary — What We Can Do Today vs What We Need

| Capability | Current State | What's Needed | Effort |
|---|---|---|---|
| **Hormuz status tracking** | ✅ Working (news-derived) | Migrate to generalized model | ~1h |
| **Bab el-Mandeb status tracking** | ❌ None | Phases 1-4 (schema + routing + keywords + UI) | ~5.5h |
| **Suez Canal tracking** | ❌ None | Comes free with Phases 1-4 | included |
| **Geographic event routing** | ❌ All events → Hormuz | Bounding box + keyword matching | ~2h |
| **Red Sea news collection** | ❌ No keywords | Add Houthi/Red Sea keywords to config | ~30min |
| **Multi-chokepoint UI** | ❌ Hormuz-only panel | Side-by-side or tabbed display | ~2h |
| **Real vessel tracking (AIS)** | ❌ None | MarineTraffic/VesselFinder API subscription | ~4h + $49-150/mo |
| **Cape diversion metrics** | ❌ None | Derived from Bab el-Mandeb status | ~1h |

### Recommended Priority

1. **Phases 1-4** (~5.5 hours total) — Generalize chokepoint model, add Bab el-Mandeb + Suez tracking via news events. No new API costs. Immediate value.
2. **Phase 5** (if budget allows) — MarineTraffic basic tier for real vessel counts. Transforms from "news-derived estimates" to "actual measured traffic."
3. **Phase 6** — Cape diversion metric. Quick win once Bab el-Mandeb tracking is live.

### Key Takeaway

**We can track both Hormuz and Bab el-Mandeb today using only our existing news pipeline + Claude classification.** The main work is generalizing the Hormuz-specific code to support multiple chokepoints and adding Red Sea keywords to the news collector. No new API subscriptions required for the core implementation — vessel tracking APIs are a "nice to have" enhancement.
