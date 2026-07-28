from bs4 import BeautifulSoup
from scrape import send_get

def main():
    output = send_get("https://www.ycdes.org/webcad/Default.aspx", timeout=10)
    parsed = BeautifulSoup(output, 'html.parser')
    incident_table = parsed.find('table', class_='incidentList')

    rows = incident_table.find_all('tr')

    data_row = rows[1].find_all('td')

    incident_type = data_row[3].get_text(strip=True)  # Index 3 is "Incident Type"
    street = data_row[4].get_text(strip=True)         # Index 4 is "Street"
    intersection = data_row[6].get_text(strip=True)   # Index 6 is "Nearest Intersection"
    location = data_row[7].get_text(strip=True)       # Index 7 is "Location"

    full_address = f"{intersection} {location}"

    print(f"Incident Type: {incident_type}")
    print(f"Combined Address: {full_address}")# Print the parsed HTML in a readable format
    exit
main()