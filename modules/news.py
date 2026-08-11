"""
RSS/news feed ingestion for IncidentTracker.

"""

try:
    import feedparser
except ImportError as e:
    raise ImportError(
        "Libraries are missing. Please install them using 'pip install feedparser'."
    ) from e

from config import config
from scrape import send_get

debug = config["debug"]


def get_articles(feed_url):
    """
    Fetches and parses one RSS/Atom feed.

    Returns:
        list[tuple[str, str, str, str, str]]: (title, link, published,
        summary, article_id) for every entry in the feed. article_id
        falls back to the article's link if the feed has no guid.
    """
    raw = send_get(feed_url)
    parsed = feedparser.parse(raw)

    articles = []
    for entry in parsed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        published = entry.get("published", "")
        summary = entry.get("summary", "")
        article_id = entry.get("id") or link

        if debug:
            print(f"Article: {title}")

        articles.append((title, link, published, summary, article_id))

    return articles


def get_all_articles(feed_urls=None):
    """
    Fetches every configured feed and combines the results. A single
    bad feed is skipped (with a printed warning) rather than taking
    down the whole batch - same philosophy as poll_loop in main.py.
    """
    feed_urls = feed_urls if feed_urls is not None else config["feed_urls"]

    all_articles = []
    for url in feed_urls:
        try:
            all_articles.extend(get_articles(url))
        except RuntimeError as e:
            print(f"Skipping feed '{url}': {e}")

    return all_articles


if __name__ == "__main__":
    for title, link, published, summary, article_id in get_all_articles():
        print("---")
        print("title:", title)
        print("link:", link)
        print("published:", published)
        print("id:", article_id)
