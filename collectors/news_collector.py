"""
News Collection Pipeline — RSS feeds, GDELT API, article extraction, dedup, fallbacks.

Orchestrates: fetch all sources → deduplicate → store → classify via geopolitical agent.
"""

import hashlib
import re
import time
from datetime import datetime, timedelta, date
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from loguru import logger
from thefuzz import fuzz

from config import (
    RSS_FEEDS, GDELT_DOC_API, GDELT_QUERY, GDELT_RATE_LIMIT_SECONDS,
    NEWS_KEYWORDS, HEADLINE_SIMILARITY_THRESHOLD,
    NEWSAPI_KEY, BING_NEWS_KEY,
)
from db.database import get_session, GeopoliticalEvent


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities from a string."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator=" ", strip=True)


# ─── RSS Feed Fetcher ────────────────────────────────────────────────────────

def fetch_rss_feeds() -> list[dict]:
    """Fetch articles from all configured RSS feeds, filter by keywords."""
    articles = []
    keyword_pattern = re.compile(
        "|".join(re.escape(kw) for kw in NEWS_KEYWORDS),
        re.IGNORECASE,
    )

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                combined = f"{title} {summary}"

                if not keyword_pattern.search(combined):
                    continue

                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6])
                else:
                    pub_date = datetime.utcnow()

                articles.append({
                    "headline": _strip_html(title),
                    "summary": _strip_html(summary)[:500] if summary else "",
                    "source_url": entry.get("link", ""),
                    "source": name,
                    "timestamp": pub_date,
                })

            logger.debug(f"RSS {name}: fetched {len(feed.entries)} entries")
        except Exception as e:
            logger.warning(f"RSS {name} fetch failed: {e}")

    logger.info(f"RSS total: {len(articles)} keyword-matched articles")
    return articles


# ─── GDELT API Fetcher ───────────────────────────────────────────────────────

def fetch_gdelt_articles(
    query: str = GDELT_QUERY,
    max_records: int = 75,
    timespan: str = "2h",
) -> list[dict]:
    """Query GDELT DOC 2.0 API for recent articles matching keywords."""
    articles = []
    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": str(max_records),
        "timespan": timespan,
        "format": "json",
        "sort": "DateDesc",
    }

    try:
        resp = requests.get(GDELT_DOC_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for art in data.get("articles", []):
            pub_date = datetime.strptime(
                art.get("seendate", "")[:14], "%Y%m%d%H%M%S"
            ) if art.get("seendate") else datetime.utcnow()

            articles.append({
                "headline": art.get("title", ""),
                "summary": "",
                "source_url": art.get("url", ""),
                "source": f"gdelt_{art.get('domain', 'unknown')}",
                "timestamp": pub_date,
                "tone": art.get("tone", 0),
            })

        logger.info(f"GDELT: fetched {len(articles)} articles")
    except Exception as e:
        logger.warning(f"GDELT fetch failed: {e}")

    return articles


def fetch_gdelt_for_date(target_date: date, max_records: int = 250, max_retries: int = 3) -> list[dict]:
    """Fetch GDELT articles for a specific historical date (for backfill).
    Retries with exponential backoff on 429 / empty responses.
    Returns None if all retries exhausted, [] if no articles for this day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    start_str = start.strftime("%Y%m%d%H%M%S")
    end_str = end.strftime("%Y%m%d%H%M%S")

    params = {
        "query": GDELT_QUERY,
        "mode": "ArtList",
        "maxrecords": str(max_records),
        "startdatetime": start_str,
        "enddatetime": end_str,
        "format": "json",
        "sort": "DateDesc",
    }

    articles = []
    for attempt in range(max_retries):
        try:
            resp = requests.get(GDELT_DOC_API, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 5 * (2 ** attempt)  # 5, 10, 20s
                logger.info(f"GDELT 429 for {target_date}, retry {attempt+1}/{max_retries} in {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()

            for art in data.get("articles", []):
                pub_date = datetime.strptime(
                    art.get("seendate", "")[:14], "%Y%m%d%H%M%S"
                ) if art.get("seendate") else datetime.combine(target_date, datetime.min.time())

                articles.append({
                    "headline": art.get("title", ""),
                    "summary": "",
                    "source_url": art.get("url", ""),
                    "source": f"gdelt_{art.get('domain', 'unknown')}",
                    "timestamp": pub_date,
                })

            logger.debug(f"GDELT backfill {target_date}: {len(articles)} articles")
            return articles  # success — exit retry loop
        except requests.exceptions.HTTPError:
            raise  # already handled 429 above; re-raise others
        except (requests.exceptions.RequestException, ValueError) as e:
            wait = 5 * (2 ** attempt)
            logger.info(f"GDELT error for {target_date} ({e}), retry {attempt+1}/{max_retries} in {wait}s")
            time.sleep(wait)

    logger.warning(f"GDELT backfill {target_date} failed after {max_retries} retries")
    return None  # None = fetch failed; [] = no articles for this day


# ─── Article Body Extractor ──────────────────────────────────────────────────

def extract_article_body(url: str, timeout: int = 15) -> str:
    """Fetch article URL and extract main body text via BeautifulSoup."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try article tag first, then main, then body
        article = soup.find("article") or soup.find("main") or soup.find("body")
        if article:
            paragraphs = article.find_all("p")
            text = " ".join(p.get_text(strip=True) for p in paragraphs)
            return text[:3000]

        return soup.get_text(separator=" ", strip=True)[:3000]
    except Exception as e:
        logger.debug(f"Body extraction failed for {url[:80]}: {e}")
        return ""


# ─── Deduplication Engine ────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    """Normalized URL hash for exact dedup."""
    normalized = re.sub(r"[?#].*$", "", url.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()


def deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by URL hash and fuzzy headline matching."""
    seen_urls = set()
    seen_headlines = []
    unique = []

    for art in articles:
        # URL dedup
        url_h = _url_hash(art.get("source_url", ""))
        if url_h in seen_urls:
            continue
        seen_urls.add(url_h)

        # Fuzzy headline dedup
        headline = art.get("headline", "")
        is_dup = False
        for existing in seen_headlines:
            ratio = fuzz.token_sort_ratio(headline, existing) / 100.0
            if ratio >= HEADLINE_SIMILARITY_THRESHOLD:
                is_dup = True
                break

        if not is_dup:
            seen_headlines.append(headline)
            unique.append(art)

    removed = len(articles) - len(unique)
    if removed > 0:
        logger.info(f"Dedup: removed {removed} duplicates, {len(unique)} unique remain")
    return unique


# ─── Fallback Fetchers ───────────────────────────────────────────────────────

def fetch_newsapi(query: str = "Iran war oil", page_size: int = 20) -> list[dict]:
    """Fallback: NewsAPI.org (requires NEWSAPI_KEY)."""
    if not NEWSAPI_KEY:
        return []

    articles = []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "pageSize": str(page_size),
                "sortBy": "publishedAt",
                "language": "en",
                "apiKey": NEWSAPI_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        for art in data.get("articles", []):
            pub_date = datetime.fromisoformat(
                art["publishedAt"].replace("Z", "+00:00")
            ).replace(tzinfo=None) if art.get("publishedAt") else datetime.utcnow()

            articles.append({
                "headline": _strip_html(art.get("title", "")),
                "summary": _strip_html(art.get("description", ""))[:500],
                "source_url": art.get("url", ""),
                "source": f"newsapi_{art.get('source', {}).get('name', 'unknown')}",
                "timestamp": pub_date,
            })

        logger.info(f"NewsAPI fallback: {len(articles)} articles")
    except Exception as e:
        logger.warning(f"NewsAPI fallback failed: {e}")

    return articles


def fetch_bing_news(query: str = "Iran war oil", count: int = 20) -> list[dict]:
    """Fallback: Bing News Search API (requires BING_NEWS_KEY)."""
    if not BING_NEWS_KEY:
        return []

    articles = []
    try:
        resp = requests.get(
            "https://api.bing.microsoft.com/v7.0/news/search",
            params={"q": query, "count": str(count), "mkt": "en-US", "freshness": "Day"},
            headers={"Ocp-Apim-Subscription-Key": BING_NEWS_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        for art in data.get("value", []):
            pub_date = datetime.fromisoformat(
                art["datePublished"].replace("Z", "+00:00")
            ).replace(tzinfo=None) if art.get("datePublished") else datetime.utcnow()

            articles.append({
                "headline": _strip_html(art.get("name", "")),
                "summary": _strip_html(art.get("description", ""))[:500],
                "source_url": art.get("url", ""),
                "source": f"bing_{art.get('provider', [{}])[0].get('name', 'unknown')}",
                "timestamp": pub_date,
            })

        logger.info(f"Bing News fallback: {len(articles)} articles")
    except Exception as e:
        logger.warning(f"Bing News fallback failed: {e}")

    return articles


# ─── DB Dedup Check ──────────────────────────────────────────────────────────

def filter_already_stored(articles: list[dict], session) -> list[dict]:
    """Remove articles whose URL is already in geopolitical_events."""
    existing_urls = set()
    rows = session.query(GeopoliticalEvent.source_url).filter(
        GeopoliticalEvent.source_url.isnot(None)
    ).all()
    for (url,) in rows:
        if url:
            existing_urls.add(_url_hash(url))

    new_articles = [
        a for a in articles
        if _url_hash(a.get("source_url", "")) not in existing_urls
    ]
    skipped = len(articles) - len(new_articles)
    if skipped > 0:
        logger.debug(f"DB dedup: skipped {skipped} already-stored articles")
    return new_articles


# ─── Full Pipeline Orchestration ─────────────────────────────────────────────

def run_news_pipeline(classify: bool = True) -> int:
    """
    Complete news collection pipeline:
    1. Fetch from RSS + GDELT
    2. Deduplicate (URL + fuzzy headline)
    3. Fallback to NewsAPI/Bing if < 5 articles
    4. Filter already-stored URLs
    5. Extract article bodies for top articles
    6. Store raw events in geopolitical_events (category='unclassified')
    7. Optionally classify via geopolitical agent

    Returns: number of new articles stored.
    """
    # Step 1: Fetch from all primary sources
    rss_articles = fetch_rss_feeds()
    time.sleep(GDELT_RATE_LIMIT_SECONDS)
    gdelt_articles = fetch_gdelt_articles()

    all_articles = rss_articles + gdelt_articles

    # Step 2: Deduplicate
    unique_articles = deduplicate_articles(all_articles)

    # Step 3: Fallback if low volume
    if len(unique_articles) < 5:
        logger.info("Low article count — triggering fallbacks")
        fallback = fetch_newsapi() + fetch_bing_news()
        unique_articles = deduplicate_articles(unique_articles + fallback)

    if not unique_articles:
        logger.info("No new articles found")
        return 0

    # Step 4: Filter already-stored
    session = get_session()
    try:
        new_articles = filter_already_stored(unique_articles, session)

        if not new_articles:
            logger.info("All articles already in DB")
            return 0

        # Step 5: Extract bodies for top articles (limit to 20 to avoid rate limits)
        for art in new_articles[:20]:
            if art.get("source_url") and not art.get("summary"):
                body = extract_article_body(art["source_url"])
                if body:
                    art["summary"] = body[:500]

        # Step 6: Store raw events
        stored_count = 0
        event_ids = []
        for art in new_articles:
            event = GeopoliticalEvent(
                timestamp=art.get("timestamp", datetime.utcnow()),
                category="unclassified",
                headline=art.get("headline", ""),
                summary=art.get("summary", ""),
                source_url=art.get("source_url", ""),
            )
            session.add(event)
            session.flush()
            event_ids.append(event.id)
            stored_count += 1

        session.commit()
        logger.info(f"Stored {stored_count} new articles in geopolitical_events")

        # Step 7: Classify via geopolitical agent
        if classify and event_ids:
            try:
                from agents.geopolitical_agent import classify_events
                classify_events(event_ids)
            except Exception as e:
                logger.error(f"Classification failed (events stored unclassified): {e}")

        return stored_count

    except Exception as e:
        session.rollback()
        logger.error(f"News pipeline failed: {e}")
        raise
    finally:
        session.close()
