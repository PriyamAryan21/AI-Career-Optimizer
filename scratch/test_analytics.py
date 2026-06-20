import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from core.auth import get_authenticated_context
from core.analytics_scraper import scrape_and_save_analytics

async def test_production_scraper():
    print("Launching browser to test production analytics scraper...")
    async with async_playwright() as p:
        try:
            browser, context = await get_authenticated_context(p)
            page = await context.new_page()
            
            # Run the actual production scraper
            success = await scrape_and_save_analytics(page)
            
            if success:
                print("\n✅ Successfully scraped and saved metrics to database!")
                
                # Verify what was saved in the database
                from database.models import _get_connection
                conn = _get_connection()
                cur = conn.cursor()
                cur.execute("SELECT * FROM profile_metrics ORDER BY id DESC LIMIT 1")
                row = cur.fetchone()
                print("\n--- Latest Database Row ---")
                print(row)
                cur.close()
                conn.close()
            else:
                print("\n❌ Scraper returned False.")
                
            await browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_production_scraper())
