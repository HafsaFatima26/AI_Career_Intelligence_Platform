"""
Scraping Service — Sitting 2
Targets: Remotive RSS + WeWorkRemotely RSS + HackerNews Who's Hiring
Uses httpx + BeautifulSoup4 ONLY. Zero headless browsers.
Stores raw jobs into Supabase `jobs` table.
"""
import httpx
import asyncio
import json
import re
from bs4 import BeautifulSoup
from typing import List, Dict
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CareerIntelBot/1.0)"
}

# ── RSS Feed URLs ─────────────────────────────────────────────────────────────
REMOTIVE_FEEDS = [
    "https://remotive.com/remote-jobs/feed/software-dev",
    "https://remotive.com/remote-jobs/feed/data",
    "https://remotive.com/remote-jobs/feed/devops-sysadmin",
]
# WITH THIS:
WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/remote-jobs.rss",
]

# Target roles for filtering relevant jobs
TARGET_KEYWORDS = [
    "python", "fastapi", "django", "machine learning", "ml", "ai",
    "data engineer", "data scientist", "backend", "llm", "nlp",
    "deep learning", "langchain", "vector", "embedding", "api",
    "tensorflow", "pytorch", "sql", "postgresql", "aws", "gcp",
    "docker", "kubernetes", "software engineer", "fullstack"
]


# ── Core HTTP fetcher ─────────────────────────────────────────────────────────
async def fetch_url(url: str) -> str:
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20.0, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        print(f"⚠️  Fetch failed for {url}: {e}")
        return ""


# ── Remotive RSS scraper ──────────────────────────────────────────────────────
async def scrape_remotive() -> List[Dict]:
    jobs = []
    for feed_url in REMOTIVE_FEEDS:
        html = await fetch_url(feed_url)
        if not html:
            continue
        soup = BeautifulSoup(html, "xml")
        for item in soup.find_all("item"):
            title = _text(item, "title")
            description = _clean_html(_text(item, "description"))
            job = {
                "title": title,
                "company": _text(item, "author") or "Unknown",
                "description": description,
                "source_url": _text(item, "link"),
                "source": "remotive",
                "scraped_at": datetime.utcnow().isoformat(),
            }
            if _is_relevant(title + " " + description):
                jobs.append(job)
    print(f"✅  Remotive: scraped {len(jobs)} relevant jobs")
    return jobs


# ── WeWorkRemotely RSS scraper ────────────────────────────────────────────────
async def scrape_weworkremotely() -> List[Dict]:
    jobs = []
    for feed_url in WWR_FEEDS:
        html = await fetch_url(feed_url)
        if not html:
            continue
        soup = BeautifulSoup(html, "xml")
        for item in soup.find_all("item"):
            title = _text(item, "title")
            # WWR title format: "Company: Role Title" — split it
            company, role = _parse_wwr_title(title)
            description = _clean_html(_text(item, "description"))
            job = {
                "title": role,
                "company": company,
                "description": description,
                "source_url": _text(item, "link"),
                "source": "weworkremotely",
                "scraped_at": datetime.utcnow().isoformat(),
            }
            if _is_relevant(role + " " + description):
                jobs.append(job)
    print(f"✅  WeWorkRemotely: scraped {len(jobs)} relevant jobs")
    return jobs


# ── HackerNews Jobs scraper ───────────────────────────────────────────────────
async def scrape_hn_jobs() -> List[Dict]:
    """
    Scrapes HN Who's Hiring thread via Algolia API.
    Completely free, no auth, no scraping restrictions.
    """
    url = "https://hn.algolia.com/api/v1/search_by_date?query=hiring+python+machine+learning&tags=job&hitsPerPage=50"
    html = await fetch_url(url)
    if not html:
        return []
    try:
        data = json.loads(html)
        jobs = []
        for hit in data.get("hits", []):
            text = hit.get("story_text") or hit.get("comment_text") or ""
            title_raw = hit.get("title") or text[:80]
            clean_text = _clean_html(text)
            if not clean_text or len(clean_text) < 50:
                continue
            job = {
                "title": title_raw[:200],
                "company": _extract_company_from_hn(clean_text),
                "description": clean_text[:3000],
                "source_url": f"https://news.ycombinator.com/item?id={hit.get('objectID','')}",
                "source": "hackernews",
                "scraped_at": datetime.utcnow().isoformat(),
            }
            if _is_relevant(clean_text):
                jobs.append(job)
        print(f"✅  HackerNews: scraped {len(jobs)} relevant jobs")
        return jobs
    except Exception as e:
        print(f"⚠️  HN parse error: {e}")
        return []


# ── Main scrape orchestrator ──────────────────────────────────────────────────
async def scrape_all_jobs() -> List[Dict]:
    """
    Runs all scrapers concurrently and returns deduplicated job list.
    Target: 50-100 jobs per run.
    """
    print("🚀  Starting scrape across all sources...")
    results = await asyncio.gather(
        scrape_remotive(),
        scrape_weworkremotely(),
        scrape_hn_jobs(),
        return_exceptions=True,
    )

    all_jobs = []
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
        else:
            print(f"⚠️  Scraper error: {r}")

    # Deduplicate by URL
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("source_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)

    print(f"\n📊  Total unique jobs scraped: {len(unique_jobs)}")
    return unique_jobs


# ── Save to Supabase ──────────────────────────────────────────────────────────
async def save_jobs_to_db(jobs: List[Dict]) -> int:
    """Upserts jobs into Supabase jobs table. Returns count saved."""
    from services.dbService import get_client
    client = get_client()
    saved = 0
    # Batch upsert in chunks of 20 — updates existing rows on source_url conflict
    for chunk in _chunk(jobs, 20):
        rows = [
            {
                "title": j["title"][:500],
                "company": j["company"][:200],
                "description": j["description"][:5000],
                "source_url": j["source_url"][:1000],
            }
            for j in chunk
        ]
        try:
            client.table("jobs").upsert(rows, on_conflict="source_url").execute()
            saved += len(rows)
        except Exception as e:
            print(f"⚠️  DB upsert error: {e}")
    print(f"💾  Saved {saved} jobs to Supabase")
    return saved


# ── Save to local JSON (backup / testing) ────────────────────────────────────
def save_jobs_to_json(jobs: List[Dict], path: str = "scraped_jobs.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"💾  Saved {len(jobs)} jobs to {path}")


# ── Helper functions ──────────────────────────────────────────────────────────
def _text(tag, name: str) -> str:
    el = tag.find(name)
    return el.get_text(strip=True) if el else ""


def _clean_html(raw: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:3000]


def _is_relevant(text: str) -> bool:
    """Returns True if job text contains at least one target keyword."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in TARGET_KEYWORDS)


def _parse_wwr_title(title: str):
    """WeWorkRemotely titles are 'Company: Role' — split them."""
    if ":" in title:
        parts = title.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    return "Unknown", title.strip()


def _extract_company_from_hn(text: str) -> str:
    """Try to extract company name from HN job post first line."""
    first_line = text.split(".")[0][:100]
    return first_line if len(first_line) > 3 else "Unknown"


def _chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i: i + n]
