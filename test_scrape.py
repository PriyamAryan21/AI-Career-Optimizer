"""Test with stealth-mode Playwright and network idle wait."""
import asyncio
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.async_api import async_playwright


async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Use VISIBLE browser to bypass detection
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        
        # Remove webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
        """)

        page = await context.new_page()

        url = "https://www.naukri.com/react-developer-jobs?k=react+developer"
        print(f"Navigating to: {url}")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except:
            print("networkidle timeout, continuing anyway...")
        
        # Extra wait for JS rendering
        await page.wait_for_timeout(5000)
        
        content = await page.content()
        print(f"Page HTML length: {len(content)}")

        # Get all classes
        classes = await page.evaluate("""() => {
            const allElements = document.querySelectorAll('*');
            const classSet = new Set();
            allElements.forEach(el => {
                el.classList.forEach(c => classSet.add(c));
            });
            return Array.from(classSet).sort();
        }""")
        print(f"Total unique classes: {len(classes)}")
        
        # Filter for relevant classes
        relevant = [c for c in classes if any(kw in c.lower() for kw in ['job', 'tuple', 'srp', 'card', 'listing', 'title', 'comp', 'skill', 'tag'])]
        print(f"Relevant classes: {json.dumps(relevant[:40], indent=2)}")

        # Count elements with job-like text
        titles = await page.evaluate("""() => {
            const all = document.querySelectorAll('a');
            const results = [];
            all.forEach(a => {
                const text = a.textContent?.trim();
                const href = a.href;
                if (text && text.length > 10 && text.length < 120 && 
                    (href.includes('job-listings') || href.includes('/job/'))) {
                    results.push({text, href: href.substring(0, 100), tag: a.tagName, className: a.className?.substring(0, 60)});
                }
            });
            return results.slice(0, 15);
        }""")
        print(f"\nJob-like links: {len(titles)}")
        for t in titles[:10]:
            print(f"  [{t.get('className','')}] {t['text'][:60]}")
            print(f"    -> {t['href']}")

        # screenshot for debugging
        await page.screenshot(path="naukri_debug.png")
        print("\nScreenshot saved as naukri_debug.png")
        
        await browser.close()

asyncio.run(test())
