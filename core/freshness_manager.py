"""
Freshness manager — the main orchestrator.
Runs the full profile update cycle:
1. Validate Naukri session
2. Scrape job listings & analyze trends
3. Generate AI-optimized content (keyword injection)
4. Rotate headline on Naukri
5. Generate & upload fresh resume
6. Send completion email
"""

import asyncio
import random
import sys
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

from config.settings import (
    NAUKRI_PROFILE_URL, UPDATE_FREQUENCY_DAYS, JITTER_HOURS
)
from core.auth import ensure_authenticated, get_authenticated_context
from core.headline_rotator import get_next_headline, update_headline_on_naukri
from core.resume_generator import generate_resume_pdf, upload_resume_to_naukri
from intelligence.job_scraper import scrape_all_roles_async
from intelligence.trend_analyzer import analyze_trends
from intelligence.keyword_injector import generate_optimized_content
from intelligence.gap_analyzer import run_full_analysis
from database.models import log_action
from notifications.email_notifier import (
    notify_cycle_complete, notify_error, notify_pending_suggestions
)


async def run_update_cycle():
    """
    Execute one full profile update cycle.
    This is the main function called by the scheduler / GitHub Actions.
    """
    print("=" * 60)
    print(f"  AI Career Optimizer — Update Cycle")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 60)

    actions_taken = []

    # ── Step 1: Validate Session ──────────────────────
    print("\n[1/6] Validating Naukri session...")
    is_auth = await ensure_authenticated()
    if not is_auth:
        print("Session expired. Email notification sent. Aborting cycle.")
        log_action("update_cycle", "Aborted — session expired", status="failed")
        return False

    actions_taken.append("Session validated successfully")
    print("   Session is active!")

    # ── Step 2: Fetch Jobs & Analyze Trends ──────────
    print("\n[2/6] Fetching job market data from APIs...")
    try:
        from intelligence.job_feed import fetch_jobs_by_role_api
        
        # Use our free APIs instead of Playwright scraping to bypass Naukri IP blocks
        scraped_data = fetch_jobs_by_role_api()
        total_jobs = sum(len(jobs) for jobs in scraped_data.values())
        
        actions_taken.append(f"Fetched {total_jobs} jobs via APIs")

        if total_jobs > 0:
            print("\n[2b/6] Analyzing trends with Gemini...")
            trends = analyze_trends(scraped_data)
            actions_taken.append(f"Identified skills from {total_jobs} jobs")
        else:
            print("   No jobs fetched, skipping trend analysis")
            trends = {}

    except Exception as e:
        print(f"   Fetching/analysis failed: {e}")
        notify_error(str(e), "Job API Fetch & Trend Analysis")
        actions_taken.append(f"Job fetch failed: {str(e)[:100]}")
        trends = {}

    # ── Step 3: Generate Optimized Content ────────────
    print("\n[3/6] Generating AI-optimized content...")
    optimized_content = None
    try:
        optimized_content = generate_optimized_content()
        if optimized_content:
            actions_taken.append("AI content optimization complete")
        else:
            actions_taken.append("Content optimization skipped (no trend data)")
    except Exception as e:
        print(f"   Content optimization failed: {e}")
        actions_taken.append("Content optimization failed (using raw profile)")

    # ── Step 4: Generate Resume PDF ───────────────────
    print("\n[4/6] Generating resume PDF...")
    pdf_path = None
    try:
        loop = asyncio.get_running_loop()
        pdf_path = await loop.run_in_executor(None, generate_resume_pdf, optimized_content)
        actions_taken.append(f"Resume generated: {pdf_path.split('/')[-1] if '/' in pdf_path else pdf_path.split(chr(92))[-1]}")
    except Exception as e:
        print(f"   Resume generation failed: {e}")
        notify_error(str(e), "Resume Generation")
        actions_taken.append(f"Resume generation failed: {str(e)[:100]}")

    # ── Step 5: Push Updates to Naukri ────────────────
    print("\n[5/6] Pushing updates to Naukri...")
    try:
        async with async_playwright() as p:
            browser, context = await get_authenticated_context(p)
            page = await context.new_page()

            # Navigate to profile
            await page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)

            # 5a. Rotate headline
            print("   Updating headline...")
            new_headline = get_next_headline(use_ai=True)
            headline_ok = await update_headline_on_naukri(page, new_headline)
            if headline_ok:
                actions_taken.append(f"Headline rotated: {new_headline[:50]}")
            else:
                actions_taken.append("Headline rotation failed")

            # 5b. Upload resume
            if pdf_path:
                print("   Uploading resume...")
                resume_ok = await upload_resume_to_naukri(page, pdf_path)
                if resume_ok:
                    actions_taken.append("Resume uploaded to Naukri")
                else:
                    actions_taken.append("Resume upload failed")

            # ── Step 6: Scrape Profile Analytics ──────────────
            print("\n[6/7] Scraping profile performance analytics...")
            from core.analytics_scraper import scrape_and_save_analytics
            analytics_ok = await scrape_and_save_analytics(page)
            if analytics_ok:
                actions_taken.append("Scraped and saved profile analytics")
            else:
                actions_taken.append("Analytics scraping failed")

            await browser.close()

    except Exception as e:
        print(f"   Naukri update/analytics failed: {e}")
        notify_error(str(e), "Naukri Profile Update")
        actions_taken.append(f"Naukri push failed: {str(e)[:100]}")

    # ── Step 7: Gap Analysis & Notifications ──────────
    print("\n[7/7] Running gap analysis & sending notifications...")
    try:
        gap_result = run_full_analysis()
        if gap_result and gap_result.get("suggestions"):
            actions_taken.append(
                f"Gap analysis: {gap_result['match_score']}% match, "
                f"{len(gap_result['suggestions'])} new suggestions"
            )
            # Notify about pending suggestions
            from database.models import get_pending_suggestions
            pending = get_pending_suggestions()
            if pending:
                notify_pending_suggestions(pending)
    except Exception as e:
        print(f"   Gap analysis failed: {e}")
        actions_taken.append(f"Gap analysis failed: {str(e)[:50]}")

    # ── Done: Send Summary Email ──────────────────────
    jitter = random.randint(0, JITTER_HOURS)
    next_run = (datetime.now() + timedelta(days=UPDATE_FREQUENCY_DAYS, hours=jitter))
    next_run_str = next_run.strftime("%Y-%m-%d ~%H:%M IST")

    notify_cycle_complete(actions_taken, next_run_str)

    log_action(
        "update_cycle",
        f"Cycle complete: {len(actions_taken)} actions",
        details="\n".join(actions_taken),
        status="success"
    )

    print(f"\n{'='*60}")
    print(f"  Cycle Complete!")
    print(f"  Actions: {len(actions_taken)}")
    print(f"  Next run: {next_run_str}")
    print(f"{'='*60}")
    for a in actions_taken:
        print(f"   - {a}")

    return True


def run():
    """Sync entry point for the update cycle."""
    asyncio.run(run_update_cycle())


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    run()
