# York County Incident Tracker

My senior capstone project for my Cybersecurity program, exploring how well local news coverage reflects emergency incidents and what that gap might mean for public perception of EMS, law enforcement, and media reporting.

## Project Goal

Emergency dispatch data (CAD feeds) is often public, but only a small fraction of incidents ever make it into local news. This project aims to:

1. Scrape and log real incident data from public dispatch sources.
2. Geocode and map those incidents.
3. Eventually cross-reference incidents against local news/RSS coverage to measure how much (or how little) overlap exists.
4. Combine incidents into some sort of database. At the very least, publish the dataset!
5. Possibly impliment language model analysis of real-time incidents.
6. Use that comparison to discuss bias, gaps, and framing in how emergencies are reported to the public.

This is an active work-in-progress build, not a finished tool.

## Current Status

Polls every active incident from [ycdes.org WebCAD](https://www.ycdes.org/webcad/Default.aspx), stores them in a local SQLite database with duplicate detection, and renders everything currently on record as an interactive map (`incident_map.html`). In parallel, it pulls configured local news RSS feeds, stores articles separately, and can run stored articles through a local Ollama model to pull out structured incident-type/location/time signals — the raw material for the incident-vs-coverage comparison that's still ahead.

| File | Purpose | Status |
|---|---|---|
| `main.py` | Entry point, numbered menu to poll & save, map stored incidents, list what's saved, run a continuous polling loop, fetch/store news, or run LLM analysis on stored articles | Working |
| `scrape.py` | Scrapes the ycdes.org incident table (type, intersection, location) for every currently active incident | Working |
| `news.py` | Fetches configured RSS/Atom feeds and parses each entry into a `(title, link, published, summary, article_id)` tuple | Working |
| `llm.py` | Async structured extraction from stored articles via a local Ollama model — pulls out incident type, location mentioned, and time reference | Working |
| `database.py` | SQLite storage for incidents (fingerprinted by type + address, deduped) and news articles (deduped by feed guid, later enriched with the LLM's extracted fields) | Working |
| `map.py` | Cleans scraped addresses, geocodes via ArcGIS, and plots one or many incidents on a Folium map | Working |
| `config.py` | Centralized config loader with sane defaults (debug, DB path, map tiles, poll interval, feed list, Ollama settings) | Working |
| `config.json` | Optional runtime overrides but every key has a default, so this isn't required | Working |
| `analysis.py` | Where the actual incident-vs-article comparison/matching logic will live | moved to llm.py |
| `incident_map.html` | Generated output, a Folium/Leaflet map with a marker per stored incident | Example output |

The pipeline now handles every active incident and every configured news feed, and persists both across runs instead of overwriting a single snapshot. `main.py` can also poll continuously and unattended (see [Setup](#setup)).

## How It Works

**Incident pipeline:**

<img width="667" height="899" alt="menu+polling" src="https://github.com/user-attachments/assets/72e3f7cd-bf31-417c-ae68-fd2a96ca5222" />

1. `scrape.py` sends a GET request to the ycdes.org WebCAD page and parses every row of the incident table with BeautifulSoup, returning each active incident's type, nearest intersection, and location text.

<img width="711" height="320" alt="menu+storedincidents" src="https://github.com/user-attachments/assets/ab9b34d6-a657-4c80-ab2b-cbe3963da928" />

2. `database.py` stores each incident in a local SQLite database (`incidents.db`). Incidents are fingerprinted by type + address, so the same still-active dispatch showing up on repeated polls bumps its `last_seen`/`times_seen` instead of creating a duplicate row.

<img width="490" height="703" alt="menu+mapping" src="https://github.com/user-attachments/assets/9bc2668e-e54e-46f0-83d6-db1d8cd59d6b" />

3. `map.py` cleans each stored address into a geocodable string, reverse-geocodes it with `geopy`'s ArcGIS geocoder, and plots every incident currently in the database onto one Folium map.

<img width="905" height="942" alt="map" src="https://github.com/user-attachments/assets/e6073081-5e80-4841-98e9-3891423cc434" />

**News pipeline:**

4. `news.py` fetches every feed URL in `config.json`'s `feed_urls` and parses each entry with `feedparser`, returning the article's title, link, published date, summary, and a stable id.

<img width="444" height="280" alt="pull_rss" src="https://github.com/user-attachments/assets/07f064ff-0dca-4c25-9e7a-d6d58486ccfc" />

5. `database.py` stores each article, deduped by that id, with no analysis yet attached.

<img width="779" height="909" alt="rss_analysis" src="https://github.com/user-attachments/assets/0488ead6-939f-495a-8a79-badbabb0a9f5" />

6. `llm.py` pulls every stored article that hasn't been analyzed yet and, for each one, asynchronously asks a local Ollama model to extract a structured `{incident_type, location_mentioned, time_reference}` record from the headline and summary. Results get written back onto that article's row. Initially tested 50 rss article snapshots with qwen2.5:0.5b, took ~5 minutes on i5-7300u+igpu and 8gb ram (kde plasma/arch linux). 7 previews were analyzed in about 30 seconds with the recommended qwen2.5:1.5b on the same setup. 

## Setup

```bash
pip install httpx beautifulsoup4 folium geopy feedparser ollama
```

The LLM analysis step also needs [Ollama](https://ollama.com) installed and a model pulled locally (this project currently defaults to `qwen2.5:1.5b`):

```bash
ollama pull qwen2.5:1.5b
```

`config.json` in the project root is optional — everything below has a default in `config.py`, so you only need to set the keys you want to override:

```json
{
  "debug": false,
  "db_path": "incidents.db",
  "map_tiles": "cartodbpositron",
  "poll_interval_seconds": 240,
  "feed_urls": ["https://www.abc27.com/local-news/york/feed/"],
  "ollama_model": "qwen2.5:1.5b",
  "ollama_num_ctx": 4096,
  "ollama_max_concurrent": 1
  "ollama_model_temp": 0.1,
  "cross_reference_time_window_hours": 6,
  "cross_reference_location_threshold": 0.35
}
```

| Key | Default | Purpose |
|---|---|---|
| `debug` | `false` | Verbose logging, including full tracebacks on poll failures |
| `db_path` | `"incidents.db"` | SQLite file location, resolved relative to the project root |
| `map_tiles` | `"cartodbpositron"` | Folium basemap tile provider |
| `poll_interval_seconds` | `240` | Delay between polls in the continuous loop — matches ycdes.org's own auto-refresh cadence |
| `feed_urls` | ABC27's York feed | List of RSS/Atom feed URLs to pull for news-coverage comparison |
| `ollama_model` | `"qwen2.5:1.5b"` | Local Ollama model used for article extraction |
| `ollama_num_ctx` | `4096` | Context window passed to Ollama per extraction call |
| `ollama_max_concurrent` | `1` | How many articles to send to Ollama at once — local inference on modest hardware is realistically serial regardless, so raise this only once you've confirmed your machine can handle it |
more descriptions coming as vars solidify in the plan!


Then run:

```bash
python main.py
```

```
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
```

Option 4 leaves the process running in the foreground, polling on the interval set by `poll_interval_seconds`. A failed poll is logged and skipped rather than killing the loop, with a louder warning if failures start stacking up. Ctrl+C stops the loop and drops you back to the menu without exiting the program.

Options 5 and 6 are deliberately separate: 5 only fetches and stores raw articles (safe to run often, cheap, no LLM involved), 6 only processes whatever's stored and hasn't been analyzed yet. Re-running 6 after nothing new has been fetched just reports there's nothing to do.

## Roadmap

- [x] Build out `main.py` as the actual pipeline entry point
- [x] Move from single-incident to continuous/batch incident mapping, with periodic snapshots
- [x] Persist incident history (SQLite-backed, with dedup, instead of overwriting a single HTML file per run)
- [x] Harden the polling loop against transient failures so it can run unattended for extended periods
- [x] Add a news/RSS ingestion module, with persisted article storage
- [x] Local LLM structured extraction from articles (incident type / location / time signals)
- [ ] Persistent logging to file for long-running/headless polling sessions (right now output only goes to the terminal)
- [ ] Basic analysis comparing incident counts to news mentions over time (implemented, but untested)
- [ ] Evaluate scraping [717alerts.com](https://717alerts.com) as a secondary incident source.
- [ ] Evaluate scraping [crimewatch.net](https://crimewatch.net) department pages.

## To Do

- Stronger LLM Prompt/ output formatting
- Make menu option 3 more dynamic to view all db contents - also have test data implementation options
- Add more RSS feeds
- Add visual progression/loading bar for intensive task (llm analysis)
- database merging (for my older sessions, so previous data isn't irrelevant/unusable).

## Ethical & Legal Notes

This project only scrapes data that is already published for public access (public safety CAD dispatch pages, public news sites). As this expands:

- Requests are rate-limited and identify with a standard browser User-Agent; no attempt is made to bypass authentication, paywalls, or bot protections.
- Article analysis runs against a locally-hosted Ollama model — article text isn't sent to a third-party API for processing.
- No personally identifying information beyond what's already public on the dispatch page (e.g., names of victims) is intentionally collected or published.

## Disclaimer

This is a student research project. Incident data is pulled from public safety dispatch systems and may be incomplete, delayed, or occasionally inaccurate, it should not be used for real-time emergency awareness or decision-making.
