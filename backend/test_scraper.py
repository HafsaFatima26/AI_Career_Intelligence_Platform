"""
Quick standalone test for the scraper — run this directly to verify
before wiring into the full API.

Usage:
  cd backend
  python test_scraper.py
"""
import asyncio
from services.scraperService import scrape_all_jobs, save_jobs_to_json

async def main():
    jobs = await scrape_all_jobs()

    print("\n── Sample Jobs ─────────────────────────────")
    for job in jobs[:5]:
        print(f"  [{job['source']}] {job['title']} @ {job['company']}")
        print(f"  URL: {job['source_url']}")
        print(f"  Desc preview: {job['description'][:120]}...")
        print()

    save_jobs_to_json(jobs, "scraped_jobs.json")
    print(f"\n✅  Done. {len(jobs)} jobs saved to scraped_jobs.json")

if __name__ == "__main__":
    asyncio.run(main())
