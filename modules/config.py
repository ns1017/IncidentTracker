"""
Centralized config loader for IncidentTracker.

Usage:
    from config import config
    debug = config["debug"]
"""

import json
from pathlib import Path

DEFAULT_CONFIG = {
    "debug": False,
    "db_path": "incidents.db",
    "map_tiles": "cartodbpositron",
    "poll_interval_seconds": 900,
    "feed_urls": ["https://www.abc27.com/local-news/york/feed/"],
    "ollama_model": "qwen2.5:1.5b",
    "ollama_num_ctx": 4096,
    "ollama_max_concurrent": 1,
    "ollama_model_temp": 0.1,
    # Pre-filter thresholds for llm.py's cross-reference step, used
    # before any LLM calls are made. location_threshold is a
    # difflib.SequenceMatcher ratio (0-1) - this starting value is a
    # guess, not tuned against real data yet; loosen/tighten once you
    # see how it behaves on your actual incidents/articles.
    "cross_reference_time_window_hours": 6,
    "cross_reference_location_threshold": 0.35,
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """
    Loads config.json and merges it over DEFAULT_CONFIG.

    """
    cfg = DEFAULT_CONFIG.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        cfg.update(loaded)
    except FileNotFoundError:
        print(f"[config] '{path}' not found, using defaults.")
    except json.JSONDecodeError as e:
        print(f"[config] '{path}' has invalid JSON ({e}), using defaults.")

    return cfg

config = load_config()
