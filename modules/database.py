"""
Duplicate incidents are collapsed via a fingerprint hash
of incident_type + address rather than inserted as new rows -
first_seen stays fixed, last_seen bumps forward each time it's
scraped again.

Usage:
    from database import get_conn, log_incident, close

    conn = get_conn()
    log_incident(conn, incident_type, address)
    close(conn)
"""
try:

    import hashlib
    import sqlite3
except ImportError as e:
    raise ImportError(
        "Python v3.6+ required for sqlite3 and hashlib. Please upgrade your Python installation."
    )

from config import config, PROJECT_ROOT

DB_PATH = str(PROJECT_ROOT / config["db_path"])

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    fingerprint    TEXT PRIMARY KEY,
    incident_type  TEXT NOT NULL,
    address        TEXT NOT NULL,
    times_seen     INTEGER NOT NULL DEFAULT 1,
    first_seen     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Opens (and if needed, creates) the incidents database and makes
    sure the incidents table exists.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def fingerprint(incident_type: str, address: str) -> str:
    """
    Builds a stable id for an incident from its type + address so
    the same active dispatch scraped on repeated polls maps to the
    same row instead of creating duplicates.
    """
    raw = f"{incident_type.strip().lower()}|{address.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def log_incident(conn: sqlite3.Connection, incident_type: str, address: str) -> str:
    """
    Inserts a new incident with duplicate redundancy.

    Returns the fingerprint for the logged incident.
    """
    fp = fingerprint(incident_type, address)
    conn.execute(
        """
        INSERT INTO incidents (fingerprint, incident_type, address)
        VALUES (?, ?, ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
            times_seen = times_seen + 1,
            last_seen = CURRENT_TIMESTAMP
        """,
        (fp, incident_type, address),
    )
    conn.commit()
    return fp


def get_all_incidents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Returns every logged incident, most recently seen first.
    """
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM incidents ORDER BY last_seen DESC")
    return cur.fetchall()


def close(conn: sqlite3.Connection) -> None:
    conn.close()


if __name__ == "__main__":
    test_conn = get_conn()
    log_incident(test_conn, "Vehicle Accident", "N George St & W King St, York, PA")
    log_incident(test_conn, "Vehicle Accident", "N George St & W King St, York, PA") #duplicate check
    log_incident(test_conn, "Fire Alarm", "123 Main St, York, PA")

    for row in get_all_incidents(test_conn):
        print(dict(row))

    close(test_conn)
