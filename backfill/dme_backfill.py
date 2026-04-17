"""
DME Oman Crude Oil Settlement Scraper.

Fetches daily end-of-day settlement prices for DME Oman Crude (OQD) from the
CME Group public settlement page (30-min delayed).

  Product: DME Oman Crude Oil Futures (OQD on CME Globex)
  CME product ID: config.DME_CME_PRODUCT_ID (default 460)
  Settlement page: https://www.cmegroup.com/CmeWS/mvc/Settlements/futures/
                   settlements/{product_id}/ALL.html

Note: DME (Dubai Mercantile Exchange) rebranded to Gulf Mercantile Exchange in
2025. Their contracts remain accessible via CME Group infrastructure.  If CME
changes the product code or page structure, update DME_CME_PRODUCT_ID in
config.py and the _parse_settle_price column-order heuristic below.
"""

import re
from datetime import date
from loguru import logger

import requests
from bs4 import BeautifulSoup

from config import DME_CME_PRODUCT_ID, DME_REQUEST_TIMEOUT
from db.database import FuturesCurve

_CME_SETTLE_URL = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/futures/settlements"
    f"/{DME_CME_PRODUCT_ID}/ALL.html"
)

_MONTH_MAP = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.cmegroup.com/",
}


def _parse_contract_month(label: str) -> str | None:
    """Convert CME label like 'MAY 26' or 'MAY2026' to 'YYYY-MM'."""
    label = label.strip().upper()
    m = re.match(r"([A-Z]{3})\s*(\d{2,4})$", label)
    if m:
        mon, yr = m.group(1), m.group(2)
        if mon not in _MONTH_MAP:
            return None
        year = f"20{yr}" if len(yr) == 2 else yr
        return f"{year}-{_MONTH_MAP[mon]}"
    return None


def _extract_settle_price(cells: list) -> float | None:
    """
    CME settlement tables have columns roughly:
      Month | Open | High | Low | Last | Change | Settle | Est.Vol | PriorSettle
    We try column index 6 (Settle) first, then fall back to 4 (Last) and others.
    """
    for idx in [6, 5, 4, 7, 3]:
        if idx >= len(cells):
            continue
        txt = cells[idx].get_text(strip=True).replace(",", "").replace("\u2013", "").replace("-", "")
        if not txt or txt in ("", "0", "UNCH"):
            continue
        try:
            val = float(txt)
            if 5.0 < val < 1000.0:   # sanity range for crude oil $/bbl
                return val
        except ValueError:
            continue
    return None


def run_backfill(start_from: date, session) -> int:
    """
    Scrape today's DME Oman Crude settlement prices from the CME Group page.
    Inserts/updates FuturesCurve rows with symbol='OQD' for each contract month
    returned that falls on or after start_from.

    Returns count of rows inserted/updated.
    """
    today = date.today()
    start_ym = start_from.strftime("%Y-%m")

    logger.info(f"DME backfill: fetching Oman settlements from CME (product {DME_CME_PRODUCT_ID})")

    try:
        resp = requests.get(
            _CME_SETTLE_URL,
            headers=_HEADERS,
            timeout=DME_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"DME backfill: HTTP {e.response.status_code} from CME. "
            f"Check DME_CME_PRODUCT_ID ({DME_CME_PRODUCT_ID}) in config.py. "
            f"URL: {_CME_SETTLE_URL}"
        )
        return 0
    except requests.exceptions.RequestException as e:
        logger.warning(f"DME backfill: network error fetching CME page: {e}")
        return 0

    soup = BeautifulSoup(resp.text, "lxml")

    # CME settlement pages wrap data in a <table> — find the one with price rows
    table = None
    for t in soup.find_all("table"):
        first_data = t.find("td")
        if first_data and re.search(r"[A-Z]{3}\s*\d{2}", first_data.get_text(strip=True).upper()):
            table = t
            break

    if table is None:
        table = soup.find("table")

    if table is None:
        logger.warning(
            "DME backfill: no settlement table found in CME page. "
            "The page structure may have changed."
        )
        return 0

    count = 0
    rows = table.find_all("tr")
    for tr in rows[1:]:          # skip header row
        cells = tr.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        contract_month = _parse_contract_month(cells[0].get_text(strip=True))
        if not contract_month:
            continue

        if contract_month < start_ym:
            continue

        settle_price = _extract_settle_price(cells)
        if settle_price is None:
            continue

        existing = session.query(FuturesCurve).filter_by(
            date=today, symbol="OQD", contract_month=contract_month,
        ).first()

        if existing:
            existing.settlement_price = settle_price
        else:
            session.add(FuturesCurve(
                date=today,
                symbol="OQD",
                contract_month=contract_month,
                settlement_price=settle_price,
                volume=None,
                open_interest=None,
            ))
        count += 1

    if count:
        session.commit()
        logger.info(f"DME backfill: stored {count} Oman (OQD) settlement prices for {today}")
    else:
        logger.warning(
            "DME backfill: parsed 0 valid prices. "
            "Page may be empty (weekend/holiday) or table format changed."
        )

    return count


