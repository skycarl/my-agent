import re
import requests
from bs4 import BeautifulSoup

URL = "https://www.seattlemonorail.com/"

# Accept either a hyphen (-) or an en-dash (–) after the weekday
DAY_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+[-–\-]\s+\d{1,2}/\d{1,2}",
    re.IGNORECASE,
)


def fetch_hours_rows(url: str = URL, timeout: int = 10) -> list[str]:
    """
    Return *all* rows that start with a weekday/date pattern.
    Scans every <li> tag — no brittle header rules — and keeps
    insertion order while de-duplicating.
    """
    html = requests.get(
        url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout
    ).text
    soup = BeautifulSoup(html, "html.parser")

    seen, rows = set(), []
    for li in soup.find_all("li"):
        text = " ".join(li.get_text(" ", strip=True).split())
        if DAY_RE.match(text) and text not in seen:
            rows.append(text)
            seen.add(text)

    return rows


if __name__ == "__main__":
    for line in fetch_hours_rows():
        print(line)
