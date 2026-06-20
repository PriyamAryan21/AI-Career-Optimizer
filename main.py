"""
AI Career Optimizer — Main Entry Point
Usage:
    python main.py                    # Run full update cycle
    python main.py --login            # Manual Naukri login (save session)
    python main.py --scrape           # Scrape jobs only
    python main.py --trends           # Scrape + analyze trends
    python main.py --resume           # Generate resume PDF only
    python main.py --gaps             # Run gap analysis only
    python main.py --db-init          # Initialize database tables
"""

import sys
import asyncio
sys.stdout.reconfigure(encoding='utf-8')


def main():
    args = sys.argv[1:]

    if not args:
        # Default: run full update cycle
        from database.models import log_action
        from core.freshness_manager import run
        log_action("cli_trigger", "Executed full update cycle (--full)", status="success")
        run()

    elif "--login" in args:
        from database.models import log_action
        from core.auth import manual_login
        log_action("cli_trigger", "Executed manual login (--login)", status="success")
        asyncio.run(manual_login())

    elif "--validate" in args:
        from database.models import log_action
        from core.auth import validate_session
        result = asyncio.run(validate_session())
        log_action("cli_trigger", "Executed session validation (--validate)", details=f"Session is valid: {result}", status="success" if result else "failed")
        sys.exit(0 if result else 1)

    elif "--scrape" in args:
        from database.models import log_action
        from intelligence.job_feed import fetch_all_api_jobs
        print("Fetching job market data from APIs...")
        jobs = fetch_all_api_jobs()
        print(f"\nSuccessfully fetched {len(jobs)} jobs across all sources.")
        log_action("cli_trigger", "Executed raw scrape (--scrape)", details=f"Fetched {len(jobs)} jobs", status="success")

    elif "--trends" in args:
        from database.models import log_action
        from intelligence.job_feed import fetch_jobs_by_role_api
        from intelligence.trend_analyzer import analyze_trends
        scraped = fetch_jobs_by_role_api()
        trends = analyze_trends(scraped)
        for role, skills in trends.items():
            print(f"\n  {role}:")
            for s in skills[:10]:
                print(f"    {s['skill']}: {s['frequency']}/{s['total_postings']}")
        log_action("cli_trigger", "Executed trend analysis (--trends)", details=f"Analyzed {len(trends)} roles", status="success")

    elif "--resume" in args:
        from database.models import log_action
        from core.resume_generator import generate_resume_pdf
        path = generate_resume_pdf()
        print(f"Resume: {path}")
        log_action("cli_trigger", "Executed resume generation (--resume)", details=f"Generated {path}", status="success")

    elif "--gaps" in args:
        from database.models import log_action
        from intelligence.gap_analyzer import run_full_analysis
        result = run_full_analysis()
        if result:
            print(f"Match Score: {result['match_score']}%")
            log_action("cli_trigger", "Executed gap analysis (--gaps)", details=f"Score: {result['match_score']}%", status="success")
        else:
            log_action("cli_trigger", "Executed gap analysis (--gaps)", details="Failed to generate score", status="failed")

    elif "--push" in args:
        print("Testing Naukri upload (skipping scraper and AI)...")
        from database.models import log_action
        from core.auth import get_authenticated_context
        from playwright.async_api import async_playwright
        from core.headline_rotator import get_next_headline, update_headline_on_naukri
        from core.resume_generator import upload_resume_to_naukri
        from config.settings import OUTPUT_DIR, NAUKRI_PROFILE_URL

        async def push_test():
            async with async_playwright() as p:
                browser, context = await get_authenticated_context(p)
                try:
                    page = await context.new_page()
                    await page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded")
                    
                    new_headline = get_next_headline(use_ai=False)
                    await update_headline_on_naukri(page, new_headline)
                    
                    pdfs = list(OUTPUT_DIR.glob("*.pdf"))
                    if pdfs:
                        latest_pdf = max(pdfs, key=lambda x: x.stat().st_mtime)
                        await upload_resume_to_naukri(page, str(latest_pdf))
                        log_action("cli_trigger", "Executed Naukri push (--push)", details=f"Uploaded {latest_pdf.name}", status="success")
                    else:
                        print("No PDFs found in output/resumes/")
                        log_action("cli_trigger", "Executed Naukri push (--push)", details="No PDFs found", status="failed")
                except Exception as e:
                    log_action("cli_trigger", "Executed Naukri push (--push)", details=f"Error: {e}", status="failed")
                finally:
                    await browser.close()
        asyncio.run(push_test())

    elif "--db-init" in args:
        from database.models import log_action
        from database.db_init import initialize_database
        initialize_database()
        log_action("cli_trigger", "Executed database init (--db-init)", status="success")

    elif "--jobs" in args:
        from database.models import log_action
        from intelligence.job_feed import get_hot_job_feed
        jobs = get_hot_job_feed(use_ai_scoring=True)
        for i, job in enumerate(jobs[:10], 1):
            print(f"\n  #{i} [{job['match_score']}% match] {job['title']}")
            print(f"     {job['company']} | {job['location']} | {job['source']}")
            print(f"     {job['apply_url'][:80]}")
        log_action("cli_trigger", "Executed job scoring (--jobs)", details=f"Scored {len(jobs)} jobs", status="success")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
