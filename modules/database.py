"""
Incident storage for IncidentTracker.

Uses SQLite (stdlib, no extra dependency) to persist scraped
incidents. Duplicate incidents (the same active dispatch reappearing
on repeated polls of ycdes.org) are collapsed via a fingerprint hash
of incident_type + address rather than inserted as new rows -
first_seen stays fixed, last_seen bumps forward each time it's
scraped again.

Usage:
    from database import get_conn, log_incident, close

    conn = get_conn()
    log_incident(conn, incident_type, address)
    close(conn)
"""

import hashlib
import sqlite3

from config import config, PROJECT_ROOT

# Resolve relative to the project root (not the current working
# directory) so it lands in the same place whether you run this from
# modules/ or from the project root, same as config.py does for
# config.json.
DB_PATH = str(PROJECT_ROOT / config["db_path"])

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    fingerprint    TEXT PRIMARY KEY,
    incident_type  TEXT NOT NULL,
    address        TEXT NOT NULL,
    dispatch_time  TEXT,
    times_seen     INTEGER NOT NULL DEFAULT 1,
    first_seen     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# incident_type/location_mentioned/time_reference start NULL and get
# filled in later by save_article_analysis() - analyzed_at being NULL
# is what marks a row as still needing the LLM extraction step.
ARTICLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    article_id          TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    link                 TEXT NOT NULL,
    published            TEXT,
    summary              TEXT,
    fetched_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    incident_type        TEXT,
    location_mentioned   TEXT,
    time_reference        TEXT,
    analyzed_at          TEXT
);
"""

# One row per incident/article pair that's been run through the LLM
# cross-reference check (not every pair - only ones that survived the
# programmatic time/location pre-filter in llm.py).
MATCHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    incident_fingerprint  TEXT NOT NULL,
    article_id            TEXT NOT NULL,
    match                 INTEGER NOT NULL,
    confidence            TEXT,
    reasoning             TEXT,
    checked_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (incident_fingerprint, article_id)
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """
    Lightweight migration for columns added after a table already
    existed in the wild. SQLite has no "ADD COLUMN IF NOT EXISTS", so
    this just tries the ALTER and ignores the error if it's already
    there. Existing rows get dispatch_time = NULL (there's no way to
    recover a dispatch time we never captured for old rows) - that's
    fine, the cross-reference step falls back to first_seen for those.
    """
    try:
        conn.execute("ALTER TABLE incidents ADD COLUMN dispatch_time TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Opens (and if needed, creates) the database and makes sure the
    incidents, articles, and matches tables all exist.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.execute(ARTICLES_SCHEMA)
    conn.execute(MATCHES_SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def fingerprint(incident_type: str, address: str) -> str:
    """
    Builds a stable id for an incident from its type + address so
    the same active dispatch scraped on repeated polls maps to the
    same row instead of creating duplicates.

    ycdes.org doesn't expose a dispatch/case number in the table, so
    this is the best stand-in available. If a real case number turns
    up later, swap it in here instead.
    """
    raw = f"{incident_type.strip().lower()}|{address.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def log_incident(
    conn: sqlite3.Connection,
    incident_type: str,
    address: str,
    dispatch_time: str | None = None,
) -> str:
    """
    Inserts a new incident, or if it's already been seen (same
    fingerprint), bumps last_seen and times_seen instead of
    duplicating the row. dispatch_time is only set on first insert -
    like first_seen, it shouldn't change on a repeat sighting.

    Returns the fingerprint for the logged incident.
    """
    fp = fingerprint(incident_type, address)
    conn.execute(
        """
        INSERT INTO incidents (fingerprint, incident_type, address, dispatch_time)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
            times_seen = times_seen + 1,
            last_seen = CURRENT_TIMESTAMP
        """,
        (fp, incident_type, address, dispatch_time),
    )
    conn.commit()
    return fp


def get_all_incidents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Returns every logged incident, most recently seen first."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM incidents ORDER BY last_seen DESC")
    return cur.fetchall()


def log_article(
    conn: sqlite3.Connection,
    title: str,
    link: str,
    published: str,
    summary: str,
    article_id: str,
) -> bool:
    """
    Stores one article, ignoring it if already on record (same
    article_id). Unlike incidents, article content doesn't change
    after publish, so - unlike log_incident() - there's nothing to
    update on a repeat; a duplicate is just skipped.

    Returns True if this was a new row, False if it was already saved.
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO articles (article_id, title, link, published, summary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (article_id, title, link, published, summary),
    )
    conn.commit()
    return cur.rowcount > 0


def get_unanalyzed_articles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Returns every stored article that hasn't been run through LLM extraction yet."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT * FROM articles WHERE analyzed_at IS NULL ORDER BY fetched_at"
    )
    return cur.fetchall()


def save_article_analysis(
    conn: sqlite3.Connection,
    article_id: str,
    incident_type: str | None,
    location_mentioned: str | None,
    time_reference: str | None,
) -> None:
    """Records the LLM's extracted fields for one previously-stored article."""
    conn.execute(
        """
        UPDATE articles
        SET incident_type = ?, location_mentioned = ?, time_reference = ?,
            analyzed_at = CURRENT_TIMESTAMP
        WHERE article_id = ?
        """,
        (incident_type, location_mentioned, time_reference, article_id),
    )
    conn.commit()


def get_all_articles_db(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Returns every stored article, most recently fetched first."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM articles ORDER BY fetched_at DESC")
    return cur.fetchall()


def get_analyzed_articles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Returns every article that's already been through LLM extraction -
    only these are useful for cross-referencing, since incident_type/
    location_mentioned/time_reference are what the pre-filter and the
    match check both rely on.
    """
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT * FROM articles WHERE analyzed_at IS NOT NULL ORDER BY fetched_at DESC"
    )
    return cur.fetchall()


def save_match(
    conn: sqlite3.Connection,
    incident_fingerprint: str,
    article_id: str,
    match: bool,
    confidence: str | None,
    reasoning: str | None,
) -> None:
    """Records (or updates) the LLM's confirm/deny judgment for one incident/article pair."""
    conn.execute(
        """
        INSERT INTO matches (incident_fingerprint, article_id, match, confidence, reasoning)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(incident_fingerprint, article_id) DO UPDATE SET
            match = excluded.match,
            confidence = excluded.confidence,
            reasoning = excluded.reasoning,
            checked_at = CURRENT_TIMESTAMP
        """,
        (incident_fingerprint, article_id, int(match), confidence, reasoning),
    )
    conn.commit()


def get_checked_pairs(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """
    Returns every (incident_fingerprint, article_id) pair already run
    through the LLM match check, so cross_reference() can skip
    re-checking (and re-spending an LLM call on) the same pair twice.
    """
    cur = conn.execute("SELECT incident_fingerprint, article_id FROM matches")
    return {(row[0], row[1]) for row in cur.fetchall()}


def close(conn: sqlite3.Connection) -> None:
    conn.close()


if __name__ == "__main__":
    test_conn = get_conn()
    log_incident(test_conn, "Vehicle Accident", "N George St & W King St, York, PA")
    log_incident(test_conn, "Vehicle Accident", "N George St & W King St, York, PA")

    for row in get_all_incidents(test_conn):
        print(dict(row))

    close(test_conn)
