from bs4 import BeautifulSoup
from scrape import send_get

def main():
    output = send_get("https://www.ycdes.org/webcad/Default.aspx", timeout=10)
    parsed = BeautifulSoup(output, 'html.parser')
    print(parsed.prettify())
    exit
main()