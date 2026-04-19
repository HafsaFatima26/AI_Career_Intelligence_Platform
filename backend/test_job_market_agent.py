"""
Standalone test for Job Market Agent — Sitting 3
Usage:
  cd backend
  python test_job_market_agent.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from agents.jobMarketAgent import run_job_market_agent

async def main():
    # Process first 20 jobs to test quickly (full run: limit=50 or more)
    saved = await run_job_market_agent(limit=20)
    print(f"\n🎯  Test complete: {saved} skills in Supabase")

if __name__ == "__main__":
    asyncio.run(main())
