"""
LLM-based structured extraction for scraped news articles, using a
local Ollama model.

Usage:
    import asyncio
    from llm import analyze_articles

    results = asyncio.run(analyze_articles(articles))  # articles from news.py
"""

import asyncio
import difflib
import json
import subprocess
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from ollama import chat, AsyncClient

from config import config

debug = config["debug"]

OLLAMA_HOST = "http://localhost:11434"
MODEL = config.get("ollama_model", "qwen2.5:1.5b")
NUM_CTX = config.get("ollama_num_ctx", 4096)
MAX_CONCURRENT_REQUESTS = config.get("ollama_max_concurrent", 1)

EXTRACTION_SYSTEM_PROMPT = (
    "You extract structured data from a news article's headline and "
    "summary. Respond with ONLY a JSON object, no other text, matching "
    'this shape: {"incident_type": string or null, '
    '"location_mentioned": string or null, "time_reference": string or '
    "null}. If a field isn't clearly present in the text, use null. "
    "Do not guess or invent details not present in the text."
)


def start_ollama():
    subprocess.Popen(
        ["ollama", "serve"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def check_ollama_running():
    """
    Returns True if Ollama is reachable.
    """  
    try:
        response = httpx.get(OLLAMA_HOST, timeout=5)
        if response.status_code == 200:
            if debug:
                print(response, "Ollama running.")
            return True
    except httpx.RequestError:
        pass

    print("Ollama not running.")
    answer = input("Attempt to start it? y/n: ").strip().lower()
    if answer != "y":
        print("Please start Ollama manually.")
        return False
    else:
        start_ollama()
        time.sleep(3)
        return True


async def analyze_article(article, semaphore, client, model=MODEL):
    """
    args: article - (title, link, published, summary, article_id)
                     tuple, e.g. one entry from news.get_articles()

    returns: dict with the article's identifying fields plus the
             model's extracted incident_type / location_mentioned /
             time_reference (each may be None). Includes an 'error'
             key instead if the call or JSON parsing failed, rather
             than raising and taking the whole batch down.
    """
    title, link, published, summary, article_id = article
    base = {
        "article_id": article_id,
        "title": title,
        "link": link,
        "published": published,
    }

    async with semaphore:
        try:
            response = await client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Headline: {title}\nSummary: {summary}"},
                ],
                format="json",
                options={"temperature": 0.1, "num_ctx": NUM_CTX},
            )
            extracted = json.loads(response.message.content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, AttributeError) as e:
            if debug:
                print(f"Extraction failed for '{title}': {type(e).__name__}: {e}")
            return {
                **base,
                "incident_type": None,
                "location_mentioned": None,
                "time_reference": None,
                "error": f"{type(e).__name__}: {e}",
            }

    return {**base, **extracted}


async def analyze_articles(articles, model=MODEL):
    """
    args: articles - list of (title, link, published, summary,
                      article_id) tuples, e.g. from
                      news.get_all_articles()

    returns: list of dicts, one per article, same order as input
             (see analyze_article()). Empty list if Ollama isn't
             reachable.
    """
    if not check_ollama_running():
        return []

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    client = AsyncClient(host=OLLAMA_HOST)

    tasks = [analyze_article(a, semaphore, client, model=model) for a in articles]
    return await asyncio.gather(*tasks)


def analyze_text(text, verify_ollama=True):
    """
    Synchronous convenience wrapper for a single ad-hoc string - kept
    separate from the async batch pipeline above, which is what
    news.py's output should actually go through.

    (Renamed the old 'check_ollama_running=True' parameter to
    'verify_ollama' - it shared a name with the check_ollama_running()
    function above, which shadowed it inside this function's scope.)
    """
    if verify_ollama and not check_ollama_running():
        return None

    response = chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        format="json",
        options={"temperature": 0.1, "num_ctx": NUM_CTX},
    )
    try:
        return json.loads(response.message.content)
    except json.JSONDecodeError:
        return None


### cross reference section ###
#
# Compares stored incidents against stored (already-analyzed) articles
# to judge whether an article is reporting on a specific incident.
#
# Two stages, on purpose - checking every incident against every
# article with an LLM call would be slow and wasteful:
#   1. Cheap programmatic pre-filter (this process, no LLM): narrows
#      down to pairs that are plausibly the same event, based on a
#      time window and fuzzy location matching.
#   2. LLM confirms/denies each surviving pair with a tightened
#      prompt, since "same rough type + overlapping time window" isn't
#      enough on its own to call it a real match.

TIME_WINDOW_HOURS = config.get("cross_reference_time_window_hours", 6)
LOCATION_THRESHOLD = config.get("cross_reference_location_threshold", 0.35)

CROSS_REFERENCE_SYSTEM_PROMPT = (
    "You determine whether a news article is reporting on a specific "
    "emergency dispatch incident. You will be given the incident's "
    "type, location, and time, plus an article's headline, summary, "
    "and previously-extracted location/time signals. Respond with "
    'ONLY a JSON object, no other text, matching this shape: '
    '{"match": true or false, "confidence": "high" or "medium" or '
    '"low", "reasoning": a one-sentence explanation}. Only answer '
    "true if the article plausibly describes the same real-world "
    "event as the incident - the same type of emergency, in the same "
    "or a clearly overlapping location, around the same time. Do not "
    "call it a match just because both mention similar keywords in "
    "general; the location and incident type must actually line up. "
    "If you are unsure, answer false with low confidence rather than "
    "guessing true."
)


def _parse_incident_datetime(incident):
    """
    Prefers the incident's actual dispatch_time (as reported by
    ycdes.org) over first_seen (when our own poller happened to see
    it) - first_seen can lag behind the real event if the poller was
    ever down. Falls back to first_seen if dispatch_time is missing
    (e.g. an older row from before this column existed) or unparseable.
    """
    dispatch_time = incident["dispatch_time"] if "dispatch_time" in incident.keys() else None
    if dispatch_time:
        try:
            return datetime.strptime(dispatch_time, "%m/%d/%Y %I:%M %p")
        except ValueError:
            pass

    try:
        return datetime.strptime(incident["first_seen"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _parse_article_datetime(article):
    """
    Parses the article's raw RSS 'published' string. This assumes
    standard RFC 2822 formatting (what RSS 2.0's <pubDate> uses, and
    what ABC27's feed produces) - a future Atom-based feed with ISO
    8601 dates would fail to parse here and just get excluded from
    time-filtered matching rather than guessed at. Worth revisiting
    with feedparser's own published_parsed if that becomes an issue.
    """
    published = article["published"] if "published" in article.keys() else None
    if not published:
        return None
    try:
        dt = parsedate_to_datetime(published)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)  # compare naive datetimes throughout
        return dt
    except (TypeError, ValueError):
        return None


def _location_similarity(a, b):
    """
    Fuzzy similarity between two location strings via stdlib difflib
    (Ratcliff/Obershelp), returning a 0-1 ratio. Deliberately not
    pulling in a dedicated fuzzy-matching library for this - difflib
    is good enough for short strings like street/intersection names.
    Swap in rapidfuzz here if this proves too weak against real data.
    """
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_candidate_pairs(
    incidents,
    articles,
    time_window_hours=TIME_WINDOW_HOURS,
    location_threshold=LOCATION_THRESHOLD,
    already_checked=None,
):
    """
    args: incidents - list of incident rows, e.g. from
                       database.get_all_incidents()
          articles - list of ANALYZED article rows, e.g. from
                      database.get_analyzed_articles() - unanalyzed
                      articles have no location_mentioned to compare
                      against and are useless here
          already_checked - set of (incident_fingerprint, article_id)
                             pairs to skip, e.g. from
                             database.get_checked_pairs()

    The actual pre-filter: keeps a pair only if published falls within
    time_window_hours of the incident's time AND the incident's
    address fuzzy-matches the article's extracted location (or, if
    that's null, the article's title+summary text) above
    location_threshold. If either side's time fails to parse, the pair
    isn't excluded on time grounds - it falls through to the location
    check alone rather than being silently dropped.

    Returns: list of (incident_row, article_row) tuples - no LLM calls
             made yet.
    """
    already_checked = already_checked or set()
    window = timedelta(hours=time_window_hours)

    candidates = []
    for incident in incidents:
        incident_dt = _parse_incident_datetime(incident)
        incident_location = incident["address"].replace("\n", " ")

        for article in articles:
            pair_key = (incident["fingerprint"], article["article_id"])
            if pair_key in already_checked:
                continue

            article_dt = _parse_article_datetime(article)
            if incident_dt and article_dt and abs(article_dt - incident_dt) > window:
                continue

            location_text = article["location_mentioned"] or f"{article['title']} {article['summary']}"
            if _location_similarity(incident_location, location_text) < location_threshold:
                continue

            candidates.append((incident, article))

    return candidates


async def check_match(incident, article, semaphore, client, model=MODEL):
    """
    args: incident - one incident row
          article - one analyzed article row

    Asks Ollama whether this specific pair is plausibly the same
    real-world event, using CROSS_REFERENCE_SYSTEM_PROMPT.

    returns: dict identifying the pair plus 'match' (bool),
             'confidence', and 'reasoning'. On a call/parse failure,
             defaults to match=False / confidence='low' rather than
             raising and taking the whole batch down.
    """
    address_oneline = incident["address"].replace("\n", " ")
    incident_summary = (
        f"Type: {incident['incident_type']}\n"
        f"Location: {address_oneline}\n"
        f"Time: {incident['dispatch_time'] or incident['first_seen']}"
    )
    article_summary = (
        f"Headline: {article['title']}\n"
        f"Summary: {article['summary']}\n"
        f"Extracted location: {article['location_mentioned']}\n"
        f"Extracted time reference: {article['time_reference']}"
    )

    base = {
        "incident_fingerprint": incident["fingerprint"],
        "incident_type": incident["incident_type"],
        "address_oneline": address_oneline,
        "article_id": article["article_id"],
        "title": article["title"],
    }

    async with semaphore:
        try:
            response = await client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": CROSS_REFERENCE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"INCIDENT:\n{incident_summary}\n\nARTICLE:\n{article_summary}",
                    },
                ],
                format="json",
                options={"temperature": 0.1, "num_ctx": NUM_CTX},
            )
            result = json.loads(response.message.content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, AttributeError) as e:
            if debug:
                print(f"Cross-reference check failed: {type(e).__name__}: {e}")
            return {**base, "match": False, "confidence": "low", "reasoning": f"check failed: {e}"}

    return {
        **base,
        "match": bool(result.get("match", False)),
        "confidence": result.get("confidence", "low"),
        "reasoning": result.get("reasoning", ""),
    }


async def cross_reference(incidents, articles, model=MODEL, already_checked=None):
    """
    args: incidents - list of incident rows, e.g. from
                       database.get_all_incidents()
          articles - list of ANALYZED article rows, e.g. from
                      database.get_analyzed_articles()
          already_checked - set of (incident_fingerprint, article_id)
                             pairs to skip, e.g. from
                             database.get_checked_pairs()

    Pre-filters incidents x articles (see find_candidate_pairs()),
    then asks Ollama to confirm/deny each surviving pair concurrently.

    returns: list of dicts, one per candidate pair actually checked
             (see check_match()). Empty list if nothing survived the
             pre-filter, or if Ollama isn't reachable.
    """
    candidates = find_candidate_pairs(incidents, articles, already_checked=already_checked)

    if not candidates:
        return []

    if not check_ollama_running():
        return []

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    client = AsyncClient(host=OLLAMA_HOST)

    tasks = [check_match(incident, article, semaphore, client, model=model) for incident, article in candidates]
    return await asyncio.gather(*tasks)


if __name__ == "__main__":
    from news import get_all_articles

    articles = get_all_articles()
    if not articles:
        print("No articles found.")
    else:
        results = asyncio.run(analyze_articles(articles))
        for r in results:
            print("---")
            print(r)
