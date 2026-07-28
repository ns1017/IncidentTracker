try:
    import httpx
    import json
    from bs4 import BeautifulSoup
except ImportError as e:
    raise ImportError(
        "Libraries are missing. Please install them using 'pip install httpx beautifulsoup4 json'."
    ) from e

try:
    with open('config.json', 'r', encoding='utf-8') as conf:
        config = json.load(conf)
except FileNotFoundError:
    print('JSON config not found')
    pass

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
            response.raise_for_status()  # Raise an exception for HTTP errors
        return response.text
    except httpx.RequestError as e:
        raise RuntimeError(f'An error occurred while requesting {url}: {e}') from e

def scrape_ycdes():
        """ Scrapes ycdes.org for local incidents, road closures, and fire hydrant.
            Though, the incidents table is our priority.
    
        Returns:
            str: The text content of the of aforementioned tables.
        """
        output = send_get("https://www.ycdes.org/webcad/Default.aspx", timeout=10)
        parsed = BeautifulSoup(output, 'html.parser')
        incident_table = parsed.find('table', class_='incidentList')
        
        rows = incident_table.find_all('tr')
        
        data_row = rows[1].find_all('td')
        
        incident_type = data_row[3].get_text(strip=True)  # Index 3 is "Incident Type"
        #street = data_row[4].get_text(strip=True)         # Index 4 is "Street", not used
        intersection = data_row[6].get_text(strip=True)   # Index 6 is "Nearest Intersection"
        location = data_row[7].get_text(strip=True)       # Index 7 is "Location"
        
        full_address = f"{intersection}\n{location}"
        if debug:
            print(f"Incident Type: {incident_type}")
            print(f"Combined Address: {full_address}")
        ycdes_table = full_address

        return ycdes_table, incident_type