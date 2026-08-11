import asyncio
import sys
import time
import traceback
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parent / "modules"
sys.path.insert(0, str(MODULES_DIR))

from config import config
from scrape import scrape_ycdes
from database import (
    get_conn,
    log_incident,
    get_all_incidents,
    log_article,
    get_unanalyzed_articles,
    save_article_analysis,
    get_analyzed_articles,
    save_match,
    get_checked_pairs,
    close,
)
from map import map_incidents
from news import get_all_articles
from llm import analyze_articles, cross_reference

MENU = """
York County Incident Tracker
-----------------------------
1. Poll ycdes.org and save incidents to the database
2. Map stored incidents
3. List saved incidents
4. Start polling loop
5. Fetch RSS feeds and save articles to the database
6. Analyze stored articles with Ollama
7. Cross-reference incidents against analyzed articles
8. Exit
"""


def poll_and_save(conn):
    print("Polling ycdes.org...")
    incidents = scrape_ycdes()

    if not incidents:
        print("No active incidents found.")
        return

    for address, incident_type, dispatch_time in incidents:
        log_incident(conn, incident_type, address, dispatch_time)

    print(f"Logged {len(incidents)} incident(s) to the database.")


def map_stored(conn):
    rows = get_all_incidents(conn)

    if not rows:
        print("No incidents in the database yet - run option 1 first.")
        return

    result = map_incidents(rows)
    if result is not None:
        print("Saved map to incident_map.html")


def list_saved(conn):
    rows = get_all_incidents(conn)

    if not rows:
        print("No incidents saved yet.")
        return

    for row in rows:
        address_oneline = row["address"].replace("\n", " ")
        print(
            f"[{row['times_seen']}x] {row['incident_type']} - {address_oneline} "
            f"(last seen {row['last_seen']})"
        )


def fetch_and_save_news(conn):
    print("Fetching news feeds...")
    articles = get_all_articles()

    if not articles:
        print("No articles found.")
        return

    new_count = 0
    for title, link, published, summary, article_id in articles:
        if log_article(conn, title, link, published, summary, article_id):
            new_count += 1

    print(f"Fetched {len(articles)} article(s), {new_count} new.")


def analyze_stored_news(conn):
    rows = get_unanalyzed_articles(conn)

    if not rows:
        print("Nothing to analyze - run option 5 first, or everything's already analyzed.")
        return

    print(f"Analyzing {len(rows)} article(s) with Ollama...\n")

    # llm.analyze_articles() expects (title, link, published, summary,
    # article_id) tuples - build them from the stored rows instead of
    # re-fetching from the live feed.
    tuples = [
        (r["title"], r["link"], r["published"], r["summary"], r["article_id"])
        for r in rows
    ]
    results = asyncio.run(analyze_articles(tuples))

    for r in results:
        print("---")
        print(r["title"])
        if r.get("error"):
            print(f"  extraction failed: {r['error']}")
            continue

        print(f"  incident_type: {r['incident_type']}")
        print(f"  location_mentioned: {r['location_mentioned']}")
        print(f"  time_reference: {r['time_reference']}")
        save_article_analysis(
            conn,
            r["article_id"],
            r["incident_type"],
            r["location_mentioned"],
            r["time_reference"],
        )

    print("\nSaved analysis results to the database.")


def run_cross_reference(conn):
    incidents = get_all_incidents(conn)
    articles = get_analyzed_articles(conn)

    if not incidents or not articles:
        print("Need at least one incident and one analyzed article - run options 1, 5, and 6 first.")
        return

    already_checked = get_checked_pairs(conn)
    print(f"Pre-filtering {len(incidents)} incident(s) x {len(articles)} analyzed article(s)...")
    results = asyncio.run(cross_reference(incidents, articles, already_checked=already_checked))

    if not results:
        print("No new candidate pairs passed the time/location pre-filter.")
        return

    print(f"Checked {len(results)} candidate pair(s) with Ollama:\n")
    match_count = 0
    for r in results:
        if r["match"]:
            match_count += 1
        print("---")
        print(f"Incident: {r['incident_type']} @ {r['address_oneline']}")
        print(f"Article:  {r['title']}")
        print(f"  match: {r['match']} (confidence: {r['confidence']})")
        print(f"  reasoning: {r['reasoning']}")
        save_match(
            conn,
            r["incident_fingerprint"],
            r["article_id"],
            r["match"],
            r["confidence"],
            r["reasoning"],
        )

    print(f"\n{match_count}/{len(results)} candidate pair(s) confirmed as matches. Saved to database.")


CONSECUTIVE_FAILURE_WARNING_THRESHOLD = 5


def poll_loop(conn):
    interval = config.get("poll_interval_seconds", 240)
    print(
        f"Starting polling loop (every {interval}s). "
        f"Press Ctrl+C to stop and return to the menu.\n"
    )

    poll_count = 0
    consecutive_failures = 0

    try:
        while True:
            poll_count += 1
            print(f"--- Poll #{poll_count} [{time.strftime('%H:%M:%S')}] ---")

            try:
                poll_and_save(conn)
                consecutive_failures = 0
            except Exception as e:
                consecutive_failures += 1
                print(f"Poll failed ({type(e).__name__}): {e}")
                if config.get("debug"):
                    traceback.print_exc()
                if consecutive_failures >= CONSECUTIVE_FAILURE_WARNING_THRESHOLD:
                    print(
                        f"WARNING: {consecutive_failures} consecutive failures - "
                        f"check your network connection or whether ycdes.org is reachable."
                    )
                print("Will retry next cycle.")

            print(f"Sleeping {interval}s until next poll...\n")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped polling loop. Returning to menu.")


def main():
    conn = get_conn()
    actions = {
        "1": lambda: poll_and_save(conn),
        "2": lambda: map_stored(conn),
        "3": lambda: list_saved(conn),
        "4": lambda: poll_loop(conn),
        "5": lambda: fetch_and_save_news(conn),
        "6": lambda: analyze_stored_news(conn),
        "7": lambda: run_cross_reference(conn),
    }

    try:
        while True:
            print(MENU)
            choice = input("Select an option: ").strip()

            if choice == "8":
                print("Exiting.")
                break

            action = actions.get(choice)
            if action:
                action()
            else:
                print("Invalid option, try again.")
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
    finally:
        close(conn)


if __name__ == "__main__":
    main()
