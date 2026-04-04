"""Quick test of RSS feed collection."""
from collectors.news_collector import fetch_rss_feeds

arts = fetch_rss_feeds()
print(f"RSS articles: {len(arts)}")
for a in arts[:8]:
    print(f"  [{a['source']}] {a['headline'][:90]}")
