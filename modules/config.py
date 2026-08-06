"""
Config loader 

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
}

# modules/config.py -> project root is one directory up
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """
    Loads config.json and merges it over DEFAULT_CONFIG.

    Never raises. If the file is missing or contains invalid JSON,
    this prints a warning and falls back to defaults so the rest of
    the pipeline doesn't crash on startup over a config problem.
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
