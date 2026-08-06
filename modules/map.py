try:
    import folium
    from geopy.geocoders import ArcGIS
    from geopy.exc import GeocoderTimedOut
except ImportError as e:
    raise ImportError(
        "Libraries are missing. Please install them using 'pip install folium geopy'."
    ) from e

from config import config

# config vars
debug = config["debug"]


def clean_coordinates(ycdes_table):
    """
    args: modules>scrape.py>scrape_ycdes() output for ONE incident
          (an "intersection\\nlocation" string)

    returns: formatted address for geopy to reverse geocode
    """
    lines = [line.strip() for line in ycdes_table.strip().split("\n") if line.strip()]
    intersection = lines[0].split(",")[0]
    intersection = intersection.replace(" / ", " & ").replace("/", " & ")

    remaining = lines[1:]  

    cleaned_address = ", ".join([intersection] + remaining) + ", York, PA"
    return cleaned_address


def convert_ycdes_to_coordinates(cleaned_address):
    """
    Converts the ycdes incident's location into coordinates

    args: formatted address

    returns: (lat, lon) tuple, or None if it couldn't be geocoded
    """
    geolocate = ArcGIS()
    try:
        location = geolocate.geocode(cleaned_address, timeout=10)

        if location:
            if debug:
                print("Location Found.")
                print(f"Full Address:   {location.address}")
                print(f"Latitude:   {location.latitude}")
                print(f"Longitude:  {location.longitude}")
            lat = round(location.latitude, 6)
            lon = round(location.longitude, 6)
            return (lat, lon)
        else:
            print("Location not found...")
            return None

    except GeocoderTimedOut:
        print("The request timed out...")
        return None


def build_map(located_incidents, output_path="incident_map.html"):
    """
    args: located_incidents - list of (lat, lon, incident_type) tuples
          output_path - where to save the resulting HTML map

    returns: folium map object, saved to output_path with one marker
             per incident. Centered on the average position of all
             incidents so a batch of incidents across the county
             fits on screen together.
    """
    if not located_incidents:
        raise ValueError("No located incidents to map.")

    avg_lat = sum(lat for lat, _, _ in located_incidents) / len(located_incidents)
    avg_lon = sum(lon for _, lon, _ in located_incidents) / len(located_incidents)

    incident_map = folium.Map(
        location=(avg_lat, avg_lon),
        zoom_start=12,
        tiles=config.get("map_tiles", "cartodbpositron"),
    )

    for lat, lon, incident_type in located_incidents:
        folium.Marker(
            location=(lat, lon),
            popup=f"{incident_type}",
            tooltip="Click for info",
            icon=folium.Icon(color="red", icon="info-sign"),
        ).add_to(incident_map)

    incident_map.save(output_path)
    return incident_map


def map_incidents(incidents, output_path="incident_map.html"):
    """
    Geocodes and plots a batch of incidents on a single map.

    args: incidents - iterable of either:
            - (address, incident_type) tuples, e.g. scrape_ycdes() output
            - sqlite3.Row objects with 'address' / 'incident_type' keys,
              e.g. database.get_all_incidents() output
          output_path - where to save the resulting HTML map

    returns: folium map object, or None if nothing could be geocoded
    """
    located = []

    for item in incidents:
        if hasattr(item, "keys"):  # sqlite3.Row (or any mapping-like row)
            address, incident_type = item["address"], item["incident_type"]
        else:
            address, incident_type = item

        cleaned = clean_coordinates(address)
        loc = convert_ycdes_to_coordinates(cleaned)

        if loc is None:
            print(f"Skipping incident: could not geocode '{cleaned}'")
            continue

        located.append((loc[0], loc[1], incident_type))

    if not located:
        print("Nothing could be geocoded - no map generated.")
        return None

    if debug:
        print(f"Mapping {len(located)} of {len(incidents)} incident(s).")

    return build_map(located, output_path)


if __name__ == "__main__":

    from scrape import scrape_ycdes

    raw_incidents = scrape_ycdes()
    if not raw_incidents:
        print("No active incidents found.")
    else:
        map_incidents(raw_incidents)
