
import sys
import time
import traceback
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parent / "modules"
sys.path.insert(0, str(MODULES_DIR))

from modules.config import config
from modules.scrape import scrape_ycdes
from modules.database import get_conn, log_incident, get_all_incidents, close
from modules.map import map_incidents

MENU = """
York County Incident Tracker
-----------------------------
1. Poll ycdes.org and save incidents to the database
2. Map stored incidents
3. List saved incidents
4. Start polling loop
5. Exit
"""


def poll_and_save(conn):
    print("Polling ycdes.org...")
    incidents = scrape_ycdes()

    if not incidents:
        print("No active incidents found.")
        return

    for address, incident_type in incidents:
        log_incident(conn, incident_type, address)

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
    }

    try:
        while True:
            print(MENU)
            choice = input("Select an option: ").strip()

            if choice == "5":
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
