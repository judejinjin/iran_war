"""
Data Quality Report — Oil Super Spike Analyzer

Audits all database tables for completeness, freshness, and anomalies.
Produces a console report covering:
  1. Options chains  — strikes per expiry, missing fields, OI coverage
  2. Futures curves   — symbol coverage, date gaps, price anomalies
  3. News / Geopolitical — event counts, date coverage, severity distribution
  4. Military          — event & deployment counts, escalation scores
  5. Infrastructure    — facility counts, disruption events, chokepoint status
  6. Vol surface       — ATM vol coverage per expiry
  7. Backfill status   — last run, errors

Run:  python data_quality_report.py
"""

import sqlite3
import sys
import io
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

# Force UTF-8 on Windows so → and other chars don't blow up in cp1252 redirects
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DB_PATH = Path(__file__).resolve().parent / "db" / "oil_data.db"

SEPARATOR = "=" * 80
SUB_SEP = "-" * 60


def connect():
    if not DB_PATH.exists():
        print(f"ERROR: database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
#  1. OPTIONS CHAINS
# ─────────────────────────────────────────────────────────────────────────────

def report_options(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  1. OPTIONS CHAINS")
    print(SEPARATOR)

    # Total rows
    total = cur.execute("SELECT COUNT(*) FROM options_chains").fetchone()[0]
    print(f"\nTotal options_chains rows: {total:,}")
    if total == 0:
        print("  *** NO OPTIONS DATA ***")
        return

    # Date range
    row = cur.execute(
        "SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM options_chains"
    ).fetchone()
    print(f"Date range: {row[0]} → {row[1]}  ({row[2]} distinct dates)")

    # Per-underlying summary
    print(f"\n{SUB_SEP}")
    print("  Per-underlying totals")
    print(SUB_SEP)
    for r in cur.execute("""
        SELECT underlying,
               COUNT(*) as rows,
               COUNT(DISTINCT date) as dates,
               COUNT(DISTINCT expiry_date) as expiries,
               COUNT(DISTINCT strike) as strikes
        FROM options_chains
        GROUP BY underlying
        ORDER BY underlying
    """):
        print(f"  {r['underlying']:8s}  rows={r['rows']:>7,}  dates={r['dates']}  "
              f"expiries={r['expiries']}  distinct_strikes={r['strikes']}")

    # Per date × underlying × expiry: strike counts (the main quality metric)
    print(f"\n{SUB_SEP}")
    print("  Strikes per expiry (latest 5 dates, per underlying)")
    print(SUB_SEP)

    dates = [r[0] for r in cur.execute(
        "SELECT DISTINCT date FROM options_chains ORDER BY date DESC LIMIT 5"
    )]

    for dt in sorted(dates):
        print(f"\n  Date: {dt}")
        rows = cur.execute("""
            SELECT underlying, expiry_date, option_type,
                   COUNT(*) as cnt,
                   MIN(strike) as min_k,
                   MAX(strike) as max_k
            FROM options_chains
            WHERE date = ?
            GROUP BY underlying, expiry_date, option_type
            ORDER BY underlying, expiry_date, option_type
        """, (dt,)).fetchall()
        if not rows:
            print("    (no data)")
            continue

        # Group by underlying + expiry
        grouped = defaultdict(dict)
        for r in rows:
            key = (r['underlying'], r['expiry_date'])
            otype = r['option_type'][:1]  # CALL→C, PUT→P
            grouped[key][otype] = {
                'cnt': r['cnt'], 'min_k': r['min_k'], 'max_k': r['max_k']
            }

        prev_underlying = None
        for (und, exp), types in sorted(grouped.items()):
            if und != prev_underlying:
                print(f"    {und}:")
                prev_underlying = und
            c_info = types.get('C', {})
            p_info = types.get('P', {})
            c_cnt = c_info.get('cnt', 0)
            p_cnt = p_info.get('cnt', 0)
            c_range = f"[{c_info['min_k']:.1f}-{c_info['max_k']:.1f}]" if c_cnt else "[]"
            p_range = f"[{p_info['min_k']:.1f}-{p_info['max_k']:.1f}]" if p_cnt else "[]"
            mismatch = " *** C/P MISMATCH ***" if c_cnt != p_cnt and c_cnt > 0 and p_cnt > 0 else ""
            print(f"      exp={exp}  C={c_cnt:>3} {c_range:>20}  P={p_cnt:>3} {p_range:>20}{mismatch}")

    # Field completeness
    print(f"\n{SUB_SEP}")
    print("  Field completeness (% non-null, non-zero)")
    print(SUB_SEP)
    fields = ['bid', 'ask', 'last_price', 'implied_vol', 'delta', 'gamma',
              'vega', 'theta', 'volume', 'open_interest']
    for f in fields:
        row = cur.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN {f} IS NOT NULL AND {f} != 0 THEN 1 ELSE 0 END) as filled
            FROM options_chains
        """).fetchone()
        pct = 100.0 * row['filled'] / row['total'] if row['total'] > 0 else 0
        flag = " *** LOW ***" if pct < 10 else ""
        print(f"  {f:20s}  {row['filled']:>7,} / {row['total']:>7,}  ({pct:5.1f}%){flag}")

    # OI distribution
    oi_rows = cur.execute(
        "SELECT COUNT(*) FROM options_chains WHERE open_interest IS NOT NULL AND open_interest > 0"
    ).fetchone()[0]
    print(f"\n  OI > 0 rows: {oi_rows:,} / {total:,}  "
          f"({100.0 * oi_rows / total:.1f}%)")

    # Date-over-date strike count change (detect big drops)
    print(f"\n{SUB_SEP}")
    print("  Date-over-date strike count changes (flag drops > 30%)")
    print(SUB_SEP)
    dod = cur.execute("""
        WITH daily AS (
            SELECT date, underlying, expiry_date,
                   COUNT(*) as strikes
            FROM options_chains
            GROUP BY date, underlying, expiry_date
        ),
        shifted AS (
            SELECT a.date, a.underlying, a.expiry_date,
                   a.strikes as today,
                   b.strikes as prev,
                   CAST(a.strikes - b.strikes AS REAL) / b.strikes * 100 as pct_change
            FROM daily a
            JOIN daily b ON a.underlying = b.underlying
                        AND a.expiry_date = b.expiry_date
                        AND a.date = date(b.date, '+1 day')
            WHERE b.strikes > 5
        )
        SELECT * FROM shifted
        WHERE pct_change < -30
        ORDER BY date DESC, underlying, expiry_date
        LIMIT 20
    """).fetchall()
    if dod:
        for r in dod:
            print(f"  {r['date']} {r['underlying']:6s} exp={r['expiry_date']}  "
                  f"{r['prev']}→{r['today']} ({r['pct_change']:+.0f}%)")
    else:
        print("  No major drops detected.")


# ─────────────────────────────────────────────────────────────────────────────
#  2. FUTURES CURVES
# ─────────────────────────────────────────────────────────────────────────────

def report_futures(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  2. FUTURES CURVES")
    print(SEPARATOR)

    total = cur.execute("SELECT COUNT(*) FROM futures_curves").fetchone()[0]
    print(f"\nTotal futures_curves rows: {total:,}")
    if total == 0:
        print("  *** NO FUTURES DATA ***")
        return

    row = cur.execute(
        "SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM futures_curves"
    ).fetchone()
    print(f"Date range: {row[0]} → {row[1]}  ({row[2]} distinct dates)")

    # Per-symbol summary
    print(f"\n{SUB_SEP}")
    print("  Per-symbol summary")
    print(SUB_SEP)
    for r in cur.execute("""
        SELECT symbol,
               COUNT(*) as rows,
               COUNT(DISTINCT date) as dates,
               COUNT(DISTINCT contract_month) as months,
               MIN(settlement_price) as min_px,
               MAX(settlement_price) as max_px,
               AVG(settlement_price) as avg_px,
               SUM(CASE WHEN settlement_price IS NULL OR settlement_price = 0 THEN 1 ELSE 0 END) as null_px,
               SUM(CASE WHEN volume IS NOT NULL AND volume > 0 THEN 1 ELSE 0 END) as vol_rows,
               SUM(CASE WHEN open_interest IS NOT NULL AND open_interest > 0 THEN 1 ELSE 0 END) as oi_rows
        FROM futures_curves
        GROUP BY symbol
        ORDER BY symbol
    """):
        print(f"  {r['symbol']:8s}  rows={r['rows']:>7,}  dates={r['dates']}  "
              f"months={r['months']}  px=[{r['min_px']:.2f}-{r['max_px']:.2f}] avg={r['avg_px']:.2f}")
        null_pct = 100.0 * r['null_px'] / r['rows'] if r['rows'] else 0
        vol_pct = 100.0 * r['vol_rows'] / r['rows'] if r['rows'] else 0
        oi_pct = 100.0 * r['oi_rows'] / r['rows'] if r['rows'] else 0
        print(f"           null_price={r['null_px']:,} ({null_pct:.1f}%)  "
              f"has_volume={r['vol_rows']:,} ({vol_pct:.1f}%)  "
              f"has_OI={r['oi_rows']:,} ({oi_pct:.1f}%)")

    # Latest 5 dates contract count
    print(f"\n{SUB_SEP}")
    print("  Recent dates — contracts per symbol")
    print(SUB_SEP)
    for r in cur.execute("""
        SELECT date, symbol, COUNT(*) as contracts,
               MIN(contract_month) as front, MAX(contract_month) as back
        FROM futures_curves
        WHERE date >= (SELECT date(MAX(date), '-7 days') FROM futures_curves)
        GROUP BY date, symbol
        ORDER BY date DESC, symbol
    """):
        print(f"  {r['date']}  {r['symbol']:6s}  {r['contracts']:>3} contracts  "
              f"[{r['front']} → {r['back']}]")

    # Date gaps (missing business days)
    print(f"\n{SUB_SEP}")
    print("  Date gaps (>1 calendar day, last 30 days, CL only)")
    print(SUB_SEP)
    dates = [r[0] for r in cur.execute("""
        SELECT DISTINCT date FROM futures_curves
        WHERE symbol IN ('CL','WTI')
        ORDER BY date DESC LIMIT 60
    """)]
    gaps_found = False
    for i in range(len(dates) - 1):
        d1 = date.fromisoformat(dates[i])
        d2 = date.fromisoformat(dates[i + 1])
        gap = (d1 - d2).days
        if gap > 3:  # skip weekends
            print(f"  Gap: {dates[i+1]} → {dates[i]}  ({gap} days)")
            gaps_found = True
    if not gaps_found:
        print("  No significant gaps found.")

    # Spreads
    spreads_total = cur.execute("SELECT COUNT(*) FROM spreads").fetchone()[0]
    print(f"\n  Spreads table: {spreads_total:,} rows")


# ─────────────────────────────────────────────────────────────────────────────
#  3. NEWS / GEOPOLITICAL EVENTS
# ─────────────────────────────────────────────────────────────────────────────

def report_news(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  3. NEWS & GEOPOLITICAL EVENTS")
    print(SEPARATOR)

    total = cur.execute("SELECT COUNT(*) FROM geopolitical_events").fetchone()[0]
    print(f"\nTotal geopolitical_events rows: {total:,}")
    if total == 0:
        print("  *** NO NEWS DATA ***")
        return

    row = cur.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM geopolitical_events"
    ).fetchone()
    print(f"Timestamp range: {row[0]} → {row[1]}")

    # By category
    print(f"\n{SUB_SEP}")
    print("  Events by category")
    print(SUB_SEP)
    for r in cur.execute("""
        SELECT category, COUNT(*) as cnt,
               AVG(severity) as avg_sev,
               SUM(CASE WHEN supply_impact_mbd IS NOT NULL AND supply_impact_mbd != 0 THEN 1 ELSE 0 END) as has_impact
        FROM geopolitical_events
        GROUP BY category
        ORDER BY cnt DESC
    """):
        avg_sev = f"{r['avg_sev']:.1f}" if r['avg_sev'] else "N/A"
        print(f"  {r['category']:30s}  {r['cnt']:>5,}  avg_severity={avg_sev}  "
              f"has_supply_impact={r['has_impact']}")

    # Events per day (last 14 days)
    print(f"\n{SUB_SEP}")
    print("  Events per day (last 14 days)")
    print(SUB_SEP)
    for r in cur.execute("""
        SELECT DATE(timestamp) as dt, COUNT(*) as cnt
        FROM geopolitical_events
        WHERE timestamp >= date('now', '-14 days')
        GROUP BY dt
        ORDER BY dt DESC
    """):
        bar = "#" * min(r['cnt'], 50)
        print(f"  {r['dt']}  {r['cnt']:>4} {bar}")

    # Severity distribution
    print(f"\n{SUB_SEP}")
    print("  Severity distribution")
    print(SUB_SEP)
    for r in cur.execute("""
        SELECT severity, COUNT(*) as cnt
        FROM geopolitical_events
        WHERE severity IS NOT NULL
        GROUP BY severity
        ORDER BY severity
    """):
        bar = "#" * min(r['cnt'], 50)
        print(f"  sev={r['severity']:>2d}  {r['cnt']:>5,}  {bar}")
    null_sev = cur.execute(
        "SELECT COUNT(*) FROM geopolitical_events WHERE severity IS NULL"
    ).fetchone()[0]
    if null_sev:
        print(f"  NULL   {null_sev:>5,}")

    # Field completeness
    print(f"\n{SUB_SEP}")
    print("  Field completeness")
    print(SUB_SEP)
    for f in ['summary', 'source_url', 'severity', 'supply_impact_mbd',
              'latitude', 'longitude', 'location_name']:
        row = cur.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN {f} IS NOT NULL AND {f} != '' THEN 1 ELSE 0 END) as filled
            FROM geopolitical_events
        """).fetchone()
        pct = 100.0 * row['filled'] / row['total'] if row['total'] > 0 else 0
        print(f"  {f:25s}  {row['filled']:>5,} / {row['total']:>5,}  ({pct:5.1f}%)")

    # Daily summaries
    ds_total = cur.execute("SELECT COUNT(*) FROM daily_summaries").fetchone()[0]
    print(f"\n  Daily summaries: {ds_total:,} rows")
    if ds_total:
        row = cur.execute(
            "SELECT MIN(date), MAX(date) FROM daily_summaries"
        ).fetchone()
        print(f"  Date range: {row[0]} → {row[1]}")


# ─────────────────────────────────────────────────────────────────────────────
#  4. MILITARY INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

def report_military(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  4. MILITARY INTELLIGENCE")
    print(SEPARATOR)

    # Events
    total = cur.execute("SELECT COUNT(*) FROM military_events").fetchone()[0]
    print(f"\nTotal military_events: {total:,}")
    if total:
        row = cur.execute(
            "SELECT MIN(date), MAX(date) FROM military_events"
        ).fetchone()
        print(f"Date range: {row[0]} → {row[1]}")
        for r in cur.execute("""
            SELECT side, event_type, COUNT(*) as cnt
            FROM military_events
            GROUP BY side, event_type
            ORDER BY side, cnt DESC
        """):
            print(f"  {r['side']:12s}  {r['event_type']:20s}  {r['cnt']:>5,}")

    # Deployments
    dep = cur.execute("SELECT COUNT(*) FROM military_deployments").fetchone()[0]
    print(f"\nMilitary deployments: {dep:,}")
    if dep:
        for r in cur.execute("""
            SELECT side, deployment_status, COUNT(*) as cnt
            FROM military_deployments
            GROUP BY side, deployment_status
            ORDER BY side, cnt DESC
        """):
            print(f"  {r['side']:12s}  {r['deployment_status']:15s}  {r['cnt']:>5,}")

    # Daily summary
    ds = cur.execute("SELECT COUNT(*) FROM military_daily_summary").fetchone()[0]
    print(f"\nMilitary daily summaries: {ds:,}")
    if ds:
        row = cur.execute(
            "SELECT MIN(date), MAX(date) FROM military_daily_summary"
        ).fetchone()
        print(f"Date range: {row[0]} → {row[1]}")
        print(f"\n  Latest escalation scores:")
        for r in cur.execute("""
            SELECT date, side, escalation_score
            FROM military_daily_summary
            ORDER BY date DESC
            LIMIT 10
        """):
            esc = r['escalation_score'] if r['escalation_score'] else "N/A"
            print(f"    {r['date']}  {r['side']:12s}  escalation={esc}")


# ─────────────────────────────────────────────────────────────────────────────
#  5. INFRASTRUCTURE & PRODUCTION
# ─────────────────────────────────────────────────────────────────────────────

def report_infrastructure(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  5. INFRASTRUCTURE & PRODUCTION")
    print(SEPARATOR)

    # Facilities
    fac = cur.execute("SELECT COUNT(*) FROM facility").fetchone()[0]
    print(f"\nFacilities: {fac:,}")
    if fac:
        for r in cur.execute("""
            SELECT facility_type, country, COUNT(*) as cnt,
                   SUM(capacity_oil_mbd) as total_oil_cap
            FROM facility
            GROUP BY facility_type, country
            ORDER BY total_oil_cap DESC
        """):
            cap = f"{r['total_oil_cap']:.2f}" if r['total_oil_cap'] else "0"
            print(f"  {r['country']:12s}  {r['facility_type']:20s}  "
                  f"{r['cnt']:>3} facilities  {cap} mbd capacity")

    # Facility status
    fs = cur.execute("SELECT COUNT(*) FROM facility_status").fetchone()[0]
    print(f"\nFacility status records: {fs:,}")
    if fs:
        row = cur.execute(
            "SELECT MIN(date), MAX(date) FROM facility_status"
        ).fetchone()
        print(f"Date range: {row[0]} → {row[1]}")

    # Disruption events
    dis = cur.execute("SELECT COUNT(*) FROM disruption_event").fetchone()[0]
    print(f"\nDisruption events: {dis:,}")
    if dis:
        for r in cur.execute("""
            SELECT event_type, COUNT(*) as cnt,
                   SUM(oil_impact_mbd) as total_oil_impact
            FROM disruption_event
            GROUP BY event_type
            ORDER BY cnt DESC
        """):
            impact = f"{r['total_oil_impact']:.2f}" if r['total_oil_impact'] else "0"
            print(f"  {r['event_type']:20s}  {r['cnt']:>4,}  oil_impact={impact} mbd")

    # Country production
    cp = cur.execute("SELECT COUNT(*) FROM country_production").fetchone()[0]
    print(f"\nCountry production records: {cp:,}")
    if cp:
        row = cur.execute(
            "SELECT MIN(date), MAX(date), COUNT(DISTINCT country) FROM country_production"
        ).fetchone()
        print(f"Date range: {row[0]} → {row[1]}  ({row[2]} countries)")

    # Chokepoints
    for table in ['hormuz_status', 'chokepoint_status']:
        cnt = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"\n{table}: {cnt:,} rows")
        if cnt:
            row = cur.execute(f"SELECT MIN(date), MAX(date) FROM {table}").fetchone()
            print(f"  Date range: {row[0]} → {row[1]}")

    # Region supply summary
    try:
        rss = cur.execute("SELECT COUNT(*) FROM region_supply_summary").fetchone()[0]
        print(f"\nRegion supply summary: {rss:,} rows")
        if rss:
            row = cur.execute(
                "SELECT MIN(date), MAX(date) FROM region_supply_summary"
            ).fetchone()
            print(f"  Date range: {row[0]} → {row[1]}")
    except sqlite3.OperationalError:
        print("\nRegion supply summary: table not found")


# ─────────────────────────────────────────────────────────────────────────────
#  6. VOL SURFACE
# ─────────────────────────────────────────────────────────────────────────────

def report_vol_surface(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  6. VOL SURFACE")
    print(SEPARATOR)

    total = cur.execute("SELECT COUNT(*) FROM vol_surface").fetchone()[0]
    print(f"\nTotal vol_surface rows: {total:,}")
    if total == 0:
        return

    row = cur.execute(
        "SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM vol_surface"
    ).fetchone()
    print(f"Date range: {row[0]} → {row[1]}  ({row[2]} dates)")

    for r in cur.execute("""
        SELECT underlying, COUNT(*) as rows,
               COUNT(DISTINCT expiry_date) as expiries,
               AVG(atm_vol) as avg_atm,
               SUM(CASE WHEN atm_vol IS NULL THEN 1 ELSE 0 END) as null_atm,
               SUM(CASE WHEN skew_25d IS NULL THEN 1 ELSE 0 END) as null_skew
        FROM vol_surface
        GROUP BY underlying
    """):
        print(f"  {r['underlying']:8s}  rows={r['rows']}  expiries={r['expiries']}  "
              f"avg_ATM={r['avg_atm']:.1f}%  null_ATM={r['null_atm']}  null_skew={r['null_skew']}")


# ─────────────────────────────────────────────────────────────────────────────
#  7. SCENARIOS & AGENT ANALYSES
# ─────────────────────────────────────────────────────────────────────────────

def report_scenarios(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  7. SCENARIOS & AGENT ANALYSES")
    print(SEPARATOR)

    sp = cur.execute("SELECT COUNT(*) FROM scenario_probabilities").fetchone()[0]
    print(f"\nScenario probabilities: {sp:,}")
    if sp:
        row = cur.execute(
            "SELECT MIN(date), MAX(date) FROM scenario_probabilities"
        ).fetchone()
        print(f"Date range: {row[0]} → {row[1]}")
        for r in cur.execute("""
            SELECT scenario_name, COUNT(*) as cnt, AVG(probability) as avg_prob
            FROM scenario_probabilities
            GROUP BY scenario_name
            ORDER BY avg_prob DESC
        """):
            print(f"  {r['scenario_name']:30s}  {r['cnt']:>3} entries  "
                  f"avg_prob={r['avg_prob']:.1%}")

    aa = cur.execute("SELECT COUNT(*) FROM agent_analyses").fetchone()[0]
    print(f"\nAgent analyses: {aa:,}")
    if aa:
        for r in cur.execute("""
            SELECT analysis_type, COUNT(*) as cnt,
                   AVG(confidence) as avg_conf
            FROM agent_analyses
            GROUP BY analysis_type
            ORDER BY cnt DESC
        """):
            conf = f"{r['avg_conf']:.1%}" if r['avg_conf'] else "N/A"
            print(f"  {r['analysis_type']:25s}  {r['cnt']:>4}  avg_confidence={conf}")


# ─────────────────────────────────────────────────────────────────────────────
#  8. BACKFILL STATUS
# ─────────────────────────────────────────────────────────────────────────────

def report_backfill(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  8. BACKFILL STATUS")
    print(SEPARATOR)

    rows = cur.execute("""
        SELECT source, status, last_backfilled_date, total_records,
               error_message, started_at, completed_at
        FROM backfill_status
        ORDER BY source
    """).fetchall()

    if not rows:
        print("\n  No backfill_status records.")
        return

    print()
    for r in rows:
        err = f"  ERROR: {r['error_message'][:80]}" if r['error_message'] else ""
        print(f"  {r['source']:18s}  status={r['status']:10s}  "
              f"last={r['last_backfilled_date'] or 'N/A':12s}  "
              f"records={r['total_records'] or 0:>7,}{err}")
        if r['started_at']:
            print(f"{'':20s}  started={r['started_at']}  completed={r['completed_at'] or 'N/A'}")


# ─────────────────────────────────────────────────────────────────────────────
#  9. OVERALL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def report_overall(conn):
    cur = conn.cursor()
    print(f"\n{SEPARATOR}")
    print("  OVERALL DATA QUALITY SUMMARY")
    print(SEPARATOR)

    tables = [
        ("geopolitical_events", "News/Geopolitical"),
        ("daily_summaries", "Daily Summaries"),
        ("military_events", "Military Events"),
        ("military_deployments", "Military Deployments"),
        ("military_daily_summary", "Military Daily Summary"),
        ("futures_curves", "Futures Curves"),
        ("spreads", "Spreads"),
        ("options_chains", "Options Chains"),
        ("vol_surface", "Vol Surface"),
        ("scenario_probabilities", "Scenarios"),
        ("agent_analyses", "Agent Analyses"),
        ("positions", "Positions"),
        ("facility", "Facilities"),
        ("facility_status", "Facility Status"),
        ("disruption_event", "Disruption Events"),
        ("country_production", "Country Production"),
        ("hormuz_status", "Hormuz Status"),
        ("chokepoint_status", "Chokepoint Status"),
        ("backfill_status", "Backfill Status"),
    ]

    print(f"\n  {'Table':<30s}  {'Rows':>10s}  Status")
    print(f"  {'-'*30}  {'-'*10}  {'-'*20}")

    for table, label in tables:
        try:
            cnt = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            cnt = -1
        if cnt < 0:
            status = "TABLE MISSING"
        elif cnt == 0:
            status = "*** EMPTY ***"
        elif cnt < 10:
            status = "LOW"
        else:
            status = "OK"
        cnt_str = f"{cnt:>10,}" if cnt >= 0 else "N/A"
        print(f"  {label:<30s}  {cnt_str}  {status}")

    # DB file size
    db_size = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"\n  Database file size: {db_size:.1f} MB")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#' * 80}")
    print(f"  OIL SUPER SPIKE ANALYZER — DATA QUALITY REPORT")
    print(f"  Generated: {date.today().isoformat()}")
    print(f"  Database:  {DB_PATH}")
    print(f"{'#' * 80}")

    conn = connect()
    try:
        report_overall(conn)
        report_options(conn)
        report_futures(conn)
        report_news(conn)
        report_military(conn)
        report_infrastructure(conn)
        report_vol_surface(conn)
        report_scenarios(conn)
        report_backfill(conn)
    finally:
        conn.close()

    print(f"\n{'#' * 80}")
    print(f"  END OF REPORT")
    print(f"{'#' * 80}\n")


if __name__ == "__main__":
    main()
