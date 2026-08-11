"""
LLM-based structured extraction for scraped news articles, using a
local Ollama model.

Usage:
    import asyncio
    from llm import analyze_articles

    results = asyncio.run(analyze_articles(articles))  # articles from news.py
"""

import asyncio
import json
import subprocess
import time

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
