try:
    import folium
    import json
    from geopy.geocoders import ArcGIS
    from geopy.exc import GeocoderTimedOut
    from scrape import scrape_ycdes
except ImportError as e:
    raise ImportError(
        "Libraries are missing. Please install them using 'pip install folium geopy json'."
    ) from e

try:
    with open('config.json', 'r', encoding='utf-8') as conf:
        config = json.load(conf)
except FileNotFoundError:
    print('JSON config not found')
    pass

# config vars
debug = config["debug"]

def clean_coordinates(ycdes_table):
    """
    args: modules>scrape.py>scrape_ycdes() output
    
    returns: formatted address for geopy to reverse geocode
    """
    lines = [line.strip() for line in ycdes_table.strip().split("\n") if line.strip()]
    intersection = lines[0].split(",")[0]
    intersection = intersection.replace(" / ", " & ").replace("/", " & ")

    remaining = lines[1:]  # e.g. "YORK CITY"

    cleaned_address = ", ".join([intersection] + remaining) + ", York, PA"
    return cleaned_address

def convert_ycdes_to_coordinates(cleaned_address):
    """
    Converts the ycdes incidents location into coordinates

    args: formatted address

    returns: reverse geocoded coordinates as list of tuples
    """
    geolocate = ArcGIS()
    try:
        location = geolocate.geocode(cleaned_address, timeout=10)
    
        if location:
            print("Location Found.")
            print(f"Full Address:   {location.address}")
            print(f"Latitude:   {location.latitude}")
            print(f"Longitude:  {location.longitude}")
            lat = round(location.latitude, 6)
            lon = round(location.longitude, 6)
            loc = (lat, lon)
            return loc
        else:
            print("Location not found...")
            return None

    except GeocoderTimedOut:
        print("The request timed out...")
        return None

def map_location(loc, incident_type):
    """
    args: lat, lon tuple provided from loc

    returns: folium map object with marker at the incident location

    notes: for prototype incidents will be mapped individually, plan to append to one continous map
    with occasional backups.

    """
    incident_map = folium.Map(location=loc, zoom_start=12)
    folium.Marker(
        location = loc,
        popup=f'{incident_type}',
        tooltip='Click for info',
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(incident_map)

    incident_map.save('incident_map.html')

raw_address, incident_type = scrape_ycdes()
cleaned = clean_coordinates(raw_address)
loc = convert_ycdes_to_coordinates(cleaned)

if loc is None:
    print(f"Skipping map: could not geocode '{cleaned}'")
else:
    map_location(loc, incident_type)