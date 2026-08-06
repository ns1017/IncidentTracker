try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError as e:
    raise ImportError(
        "Libraries are missing. Please install them using 'pip install httpx beautifulsoup4' @scrape.py."
    ) from e

from config import config

# config vars
debug = config["debug"]

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",}

def send_get(url = str, timeout = int):
    """
    Sends a GET request to the specified URL and returns the response content.

    Args:
        url (str): The URL to send the GET request to.
        timeout (int): The timeout for the request in seconds.

    Returns:
        str: The response content as text.
    """
    try:
        with httpx.Client(headers=headers) as client: 
            response = client.get(url, timeout=timeout)
            response.raise_for_status()
        return response.text
    except httpx.RequestError as e:
        raise RuntimeError(f'An error occurred while requesting {url}: {e}') from e

def scrape_ycdes():
    """ Scrapes ycdes.org for currently active incidents.

    Returns:
        list[tuple[str, str]]: an (address, incident_type) pair for
        every active incident row, or an empty list.
    """
    output = send_get("https://www.ycdes.org/webcad/Default.aspx", timeout=10)
    parsed = BeautifulSoup(output, 'html.parser')
    incident_table = parsed.find('table', class_='incidentList')

    if incident_table is None:
        return []

    data_rows = incident_table.find_all('tr')[1:]

    incidents = []
    for row in data_rows:
        cells = row.find_all('td')
        if len(cells) < 8:
            continue

        incident_type = cells[3].get_text(strip=True)  # Index 3 is "Incident Type"
        #street = cells[4].get_text(strip=True)         # Index 4 is "Street"
        intersection = cells[6].get_text(strip=True)   # Index 6 is "Nearest Intersection"
        location = cells[7].get_text(strip=True)       # Index 7 is "Location"

        full_address = f"{intersection}\n{location}"
        if debug:
            print(f"Incident Type: {incident_type}")
            print(f"Combined Address: {full_address}")

        incidents.append((full_address, incident_type))

    return incidents
