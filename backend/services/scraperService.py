"""
Lightweight HTML/RSS scraper using httpx + BeautifulSoup4.
Strictly NO headless browsers (Selenium/Playwright) – free-tier OOM safe.
"""
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict
import asyncio

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CareerBot/1.0; +https://github.com/career-bot)"
    )
}

REMOTIVE_RSS = "https://remotive.com/remote-jobs/feed/software-dev"
WEWORKREMOTELY_RSS = "https://weworkremotely.com/remote-jobs.rss"


async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def scrape_remotive_rss() -> List[Dict]:
    """Fetches Remotive RSS and returns raw job dicts."""
    html = await fetch_html(REMOTIVE_RSS)
    soup = BeautifulSoup(html, "xml")
    jobs = []
    for item in soup.find_all("item")[:30]:
        jobs.append(
            {
                "title": _text(item, "title"),
                "company": _text(item, "author"),
                "description": _clean(_text(item, "description")),
                "url": _text(item, "link"),
            }
        )
    return jobs


async def scrape_weworkremotely_rss() -> List[Dict]:
    html = await fetch_html(WEWORKREMOTELY_RSS)
    soup = BeautifulSoup(html, "xml")
    jobs = []
    for item in soup.find_all("item")[:30]:
        jobs.append(
            {
                "title": _text(item, "title"),
                "company": _text(item, "region") or "Remote",
                "description": _clean(_text(item, "description")),
                "url": _text(item, "link"),
            }
        )
    return jobs


async def scrape_all() -> List[Dict]:
    results = await asyncio.gather(
        scrape_remotive_rss(),
        scrape_weworkremotely_rss(),
        return_exceptions=True,
    )
    jobs = []
    for r in results:
        if isinstance(r, list):
            jobs.extend(r)
    return jobs


def _text(tag, name: str) -> str:
    el = tag.find(name)
    return el.get_text(strip=True) if el else ""


def _clean(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator=" ", strip=True)[:3000]   # cap context to 3k chars
