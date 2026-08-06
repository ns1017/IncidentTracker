try:

    import sys
    from pathlib import Path
except ImportError:
    print("Error: Python 3.6 or higher is required to run this program. @main.py")
    exit()

MODULES_DIR = Path(__file__).resolve().parent / "modules"
sys.path.insert(0, str(MODULES_DIR))

from modules.scrape import scrape_ycdes
from modules.database import get_conn, log_incident, get_all_incidents, close
from modules.map import map_incidents

MENU = """
York County Incident Tracker
-----------------------------
1. Poll ycdes.org and save incidents to the database
2. Map stored incidents
3. List saved incidents
4. Exit
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


def main():
    conn = get_conn()
    actions = {
        "1": lambda: poll_and_save(conn),
        "2": lambda: map_stored(conn),
        "3": lambda: list_saved(conn),
    }

    try:
        while True:
            print(MENU)
            choice = input("Select an option: ").strip()

            if choice == "4":
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
