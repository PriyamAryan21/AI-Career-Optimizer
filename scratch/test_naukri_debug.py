import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright
from config.settings import NAUKRI_PROFILE_URL
from core.auth import get_authenticated_context

async def test_naukri():
    print("Testing Naukri navigation locally...")
    try:
        async with async_playwright() as p:
            browser, context = await get_authenticated_context(p)
            page = await context.new_page()
            
            print(f"Navigating to {NAUKRI_PROFILE_URL}...")
            await page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            
            print(f"Current URL: {page.url}")
            
            # Take a screenshot to see what's on the screen
            screenshot_path = "naukri_debug_local.png"
            await page.screenshot(path=screenshot_path)
            print(f"Saved screenshot to {screenshot_path}")
            
            # Check for bot detection
            if "login" in page.url.lower():
                print("⚠️ REDIRECTED TO LOGIN. Cookies are expired or invalid.")
            else:
                title = await page.title()
                print(f"Page Title: {title}")
                if "challenge" in title.lower() or "verify" in title.lower() or "cloudflare" in title.lower():
                    print("⚠️ BLOCKED BY CLOUDFLARE/BOT DETECTION.")
                else:
                    print("✅ Page loaded successfully. Checking for DOM elements...")
                    
                    # Try to find elements
                    headline_locator = page.locator("h1:has-text('Profile Summary') span.new-pencil, div.resumeHeadline .edit").first
                    count = await headline_locator.count()
                    if count > 0:
                        print("✅ Found Headline edit button!")
                    else:
                        print("❌ Could NOT find Headline edit button. UI might have changed.")
                        
            await browser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_naukri())
