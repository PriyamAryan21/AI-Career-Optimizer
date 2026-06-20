import asyncio
import sys
from playwright.async_api import async_playwright
from core.auth import load_session
from config.settings import NAUKRI_PROFILE_URL

async def test_summary_click():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        loaded = await load_session(context)
        page = await context.new_page()

        print("Navigating to profile...")
        await page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        
        # Click the edit button
        edit_btn = page.locator("h1:has-text('Profile Summary') span.new-pencil, div:has-text('Resume Headline') span[class*='edit']").first
        try:
            await edit_btn.click(timeout=5000)
            print("Clicked edit button! Waiting for modal...")
            await page.wait_for_timeout(2000)
            
            html_analysis = await page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('textarea, input[type="text"]').forEach(t => {
                    let parent = t.parentElement;
                    let contextText = '';
                    if (parent) contextText = parent.textContent.substring(0, 50).trim();
                    if (parent && parent.parentElement) contextText += ' | ' + parent.parentElement.textContent.substring(0, 50).trim();
                    
                    results.push({
                        tag: t.tagName,
                        id: t.id,
                        class: t.className,
                        name: t.name,
                        context: contextText
                    });
                });
                return results;
            }""")
            
            print("\n--- Inputs Found ---")
            for i in html_analysis:
                print(f"{i['tag']} name='{i['name']}' id='{i['id']}' class='{i['class']}' context='{i['context']}'")
        except Exception as e:
            print(f"Error clicking: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_summary_click())
