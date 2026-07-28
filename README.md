# York County Incident Tracker

My senior capstone project for my Cybersecurity program, exploring how well **local news coverage reflects actual emergency incidents** and what that gap might mean for public perception of EMS, law enforcement, and media reporting.

<img width="2557" height="1395" alt="1" src="https://github.com/user-attachments/assets/67530af1-e84c-45b6-bf1b-ef3b35d2bb38" />

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

✅ **Working prototype** — pulls a single incident from [ycdes.org WebCAD](https://www.ycdes.org/webcad/Default.aspx), geocodes it, and renders it on an interactive map (`incident_map.html`).

| File | Purpose | Status |
|---|---|---|
| `scrape.py` | Scrapes the ycdes.org incident table (type, intersection, location) | Working |
| `map.py` | Cleans the scraped address, geocodes it via ArcGIS, and drops a marker on a Folium map | Working |
| `main.py` | Intended entry point to orchestrate the scrape → geocode → map pipeline | Not yet implemented |
| `config.json` | Basic runtime config (currently just a `debug` flag) | Working |
| `incident_map.html` | Sample output — a Folium/Leaflet map with a single incident marker | Example output |

Right now the pipeline handles **one incident at a time** (the most recent row in the CAD table). The plan is to move to continuous/batch mapping of all active incidents.

## How It Works

1. `scrape.py` sends a GET request to the ycdes.org WebCAD page and parses the incident table with BeautifulSoup, pulling incident type, nearest intersection, and location text.
2. `map.py` cleans that raw text into a geocodable address string, reverse-geocodes it with `geopy`'s ArcGIS geocoder, and plots the result on a Folium map with a marker and popup.
3. The map is saved locally as `incident_map.html`.

## Setup

```bash
pip install httpx beautifulsoup4 folium geopy
```

Create a `config.json` in the project root:

```json
{
  "debug": true
}
```

Then run:

```bash
python map.py
```

(A proper `main.py` orchestrator is planned — for now, running `map.py` directly triggers the full scrape → geocode → map flow.)

## Roadmap

- [ ] Build out `main.py` as the actual pipeline entry point
- [ ] Move from single-incident to continuous/batch incident mapping, with periodic snapshots
- [ ] Add a news/RSS ingestion module to compare incident volume vs. actual coverage
- [ ] Evaluate scraping [717alerts.com](https://717alerts.com) as a secondary incident source (heavier JS rendering — will likely require Playwright/Selenium rather than static requests)
- [ ] Evaluate scraping [crimewatch.net](https://crimewatch.net) department pages (e.g. Lower Windsor Twp PD) — "Load More" pagination will likely also require Selenium
- [ ] Persist incident history (currently overwrites a single HTML file per run)
- [ ] Basic analysis/dashboard comparing incident counts to news mentions over time

## Ethical & Legal Notes

This project only scrapes data that is already published for public access (public safety CAD dispatch pages, public news sites). As this expands:

- Requests are rate-limited and identify with a standard browser User-Agent; no attempt is made to bypass authentication, paywalls, or bot protections.
- No personally identifying information beyond what's already public on the dispatch page (e.g., names of victims) is intentionally collected or published.

## Disclaimer

This is a student research project. Incident data is pulled from public safety dispatch systems and may be incomplete, delayed, or occasionally inaccurate, it should not be used for real-time emergency awareness or decision-making.
