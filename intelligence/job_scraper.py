"""
Job scraper — fetches job listings from Naukri using Playwright.
Naukri is a React SPA, so we need a real browser to render job cards.
Uses visible browser + anti-detection to avoid bot blocking.
"""

import re
import time
import random
import asyncio
import json
import sys
from datetime import datetime
from playwright.async_api import async_playwright
from database.models import log_action
from config.settings import TARGET_ROLES


def _build_search_url(role: str, page: int = 1) -> str:
    """Build Naukri search URL for a given role."""
    slug = role.lower().replace(" ", "-")
    query = role.replace(" ", "+")
    if page == 1:
        return f"https://www.naukri.com/{slug}-jobs?k={query}"
    return f"https://www.naukri.com/{slug}-jobs-{page}?k={query}"


async def _extract_jobs_from_page(page) -> list[dict]:
    """Extract job data from a loaded Naukri search results page."""
    await page.wait_for_timeout(3000)  # Let React render

    jobs = await page.evaluate("""() => {
        const cards = document.querySelectorAll('.srp-jobtuple-wrapper, .cust-job-tuple');
        const results = [];
        
        cards.forEach(card => {
            try {
                const titleEl = card.querySelector('a.title');
                const compEl = card.querySelector('a.comp-name');
                const expEl = card.querySelector('.ni-job-tuple-icon-srp-experience + span, .exp');
                const salEl = card.querySelector('.ni-job-tuple-icon-srp-rupee + span, .sal');
                const locEl = card.querySelector('.ni-job-tuple-icon-srp-location + span, .loc');
                const descEl = card.querySelector('.job-desc');
                const dateEl = card.querySelector('.job-post-day');
                
                // Skills
                const skillEls = card.querySelectorAll('.keyskill');
                const skills = [];
                skillEls.forEach(s => {
                    const text = s.textContent?.trim();
                    if (text) skills.push(text);
                });
                
                // Also try individual skill tags inside keyskill container
                if (skills.length === 0) {
                    const tagEls = card.querySelectorAll('.tag, .chip');
                    tagEls.forEach(t => {
                        const text = t.textContent?.trim();
                        if (text) skills.push(text);
                    });
                }
                
                results.push({
                    title: titleEl?.textContent?.trim() || 'Unknown',
                    link: titleEl?.href || '',
                    company: compEl?.textContent?.trim() || 'Unknown',
                    experience: expEl?.textContent?.trim() || '',
                    salary: salEl?.textContent?.trim() || 'Not Disclosed',
                    location: locEl?.textContent?.trim() || '',
                    description_snippet: (descEl?.textContent?.trim() || '').substring(0, 500),
                    skills: skills,
                    posted: dateEl?.textContent?.trim() || '',
                });
            } catch(e) {}
        });
        
        return results;
    }""")

    # Add timestamp
    now = datetime.now().isoformat()
    for j in jobs:
        j["scraped_at"] = now

    return jobs


async def scrape_role_async(role: str, context, pages: int = 2) -> list[dict]:
    """Scrape job listings for a single role across multiple pages."""
    all_jobs = []
    print(f"  Scraping: {role}...")

    page = await context.new_page()

    for pg in range(1, pages + 1):
        url = _build_search_url(role, pg)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            jobs = await _extract_jobs_from_page(page)
            all_jobs.extend(jobs)
            print(f"   Page {pg}: {len(jobs)} jobs found")
            await page.wait_for_timeout(random.randint(2000, 4000))
        except Exception as e:
            print(f"   Page {pg} failed: {e}")
            continue

    await page.close()
    return all_jobs


async def scrape_all_roles_async(pages_per_role: int = 2) -> dict[str, list[dict]]:
    """Scrape job listings for ALL target roles using Playwright."""
    if not TARGET_ROLES:
        print("No TARGET_ROLES defined in .env")
        return {}

    results = {}
    total = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        for role in TARGET_ROLES:
            jobs = await scrape_role_async(role, context, pages=pages_per_role)
            results[role] = jobs
            total += len(jobs)
            await asyncio.sleep(random.uniform(2, 5))

        await browser.close()

    print(f"\n  Scraping complete: {total} total jobs across {len(TARGET_ROLES)} roles")
    log_action(
        "scrape_jobs",
        f"Scraped {total} jobs across {len(TARGET_ROLES)} roles",
        details=str({role: len(jobs) for role, jobs in results.items()})
    )
    return results


def scrape_all_roles(pages_per_role: int = 2) -> dict[str, list[dict]]:
    """Sync wrapper for scrape_all_roles_async."""
    return asyncio.run(scrape_all_roles_async(pages_per_role))


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    data = scrape_all_roles()
    for role, jobs in data.items():
        print(f"\n{'='*60}")
        print(f"  {role}: {len(jobs)} jobs")
        print(f"{'='*60}")
        for j in jobs[:3]:
            print(f"  {j['title']} @ {j['company']}")
            print(f"     Skills: {', '.join(j['skills'][:5])}")
            print(f"     Link: {j['link'][:80]}")
            print()
