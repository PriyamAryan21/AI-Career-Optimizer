"""
Headline rotator — cycles through profile headlines on Naukri.
Picks from the headline_pool in master_profile.yaml, or generates
a fresh one using Gemini + trending keywords. Pushes the update
to Naukri via Playwright.
"""

import random
import json
import re
import time
import google.generativeai as genai
from config.settings import GEMINI_API_KEY, load_master_profile, save_master_profile, GEMINI_MODEL
from database.models import log_action, get_trends_by_role
from config.settings import TARGET_ROLES
from collections import Counter


genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)


def generate_with_retry(model, prompt, max_retries=4, initial_delay=15, backoff_factor=2):
    """Robust wrapper for Gemini API with exponential backoff."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            if "404" in str(e).lower() or "api_key" in str(e).lower():
                raise e
            if attempt == max_retries - 1:
                raise e
            print(f"   Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
            delay *= backoff_factor
    return None


def _get_trending_keywords(top_n: int = 10) -> list[str]:
    """Get top trending skills from Supabase."""
    combined = Counter()
    for role in TARGET_ROLES:
        trends = get_trends_by_role(role, limit=10)
        for t in trends:
            combined[t["skill_name"]] += 1
    return [skill for skill, _ in combined.most_common(top_n)]


def get_next_headline(use_ai: bool = True) -> str:
    """
    Main entry point — decides whether to use AI or pool-based rotation.
    Every 3rd cycle, generate an AI headline. Otherwise, pick from pool.
    """
    if use_ai and random.random() < 0.33:
        print("   Generating AI-optimized Profile Summary...")
        return generate_ai_headline()
    else:
        print("   Picking base summary...")
        return pick_headline()


def pick_headline() -> str:
    """Fallback: returns the base summary directly from master_profile.yaml"""
    profile = load_master_profile()
    return profile.get("personal", {}).get("summary", "Computer Science student with strong foundation in full-stack development.")


def generate_ai_headline() -> str:
    """
    Generate a fresh, keyword-optimized Profile Summary using Gemini + trending data.
    Takes the base summary and elegantly weaves in trending skills to boost ranking.
    """
    profile = load_master_profile()
    base_summary = profile.get("personal", {}).get("summary", "")
    keywords = _get_trending_keywords()

    prompt = f"""You are an expert tech recruiter optimizing a candidate's Naukri Profile Summary.
    
Take this base summary:
"{base_summary}"

And naturally weave in these currently TRENDING keywords (use only the ones that make sense): 
{', '.join(keywords[:12])}

RULES:
- Must feel completely natural, professional, and confident.
- Do NOT make it a bulleted list or a pipeline of skills. Write a cohesive 3-5 sentence paragraph.
- Max length: 500 characters.
- Do not hallucinate experiences that aren't implied by the base summary.
- STRICTLY NO MARKDOWN. Return plain text only. Do NOT use **bold** or *italics*.

Return ONLY the optimized paragraph text in plain string format, nothing else."""

    try:
        response = generate_with_retry(model, prompt)
        optimized_summary = response.text.strip().strip('"').strip("'")
        
        # Strip any markdown formatting (asterisks) just in case
        optimized_summary = optimized_summary.replace("**", "").replace("*", "")
        
        if len(optimized_summary) > 50:
            print(f"   Generated AI Profile Summary: {optimized_summary[:60]}...")
            return optimized_summary
        else:
            return pick_headline()

    except Exception as e:
        print(f"   AI summary generation failed: {e}")
        return pick_headline()


async def update_headline_on_naukri(page, headline: str) -> bool:
    """
    Push the headline update to Naukri profile page.
    Assumes page is already navigated to the profile and authenticated.
    """
    try:
        # Click the edit/pencil icon specifically for the Profile Summary / Resume Headline section
        edit_btn = page.locator(
            "h1:has-text('Profile Summary') span.new-pencil, "
            "h1:has-text('Profile Summary') span.edit, "
            "div:has-text('Profile summary') a:has-text('Add'), "
            "div.resumeHeadline .edit, "
            "div.resumeHeadline span[class*='edit'], "
            "div:has-text('Resume Headline') span[class*='edit'], "
            "div:has-text('Resume Headline') i[class*='edit']"
        ).first
        # Increased timeout to 30000ms to allow Cloudflare/bot challenges to clear
        await edit_btn.click(timeout=30000)
        await page.wait_for_timeout(1000)

        # Find the headline/resume title input field
        headline_input = page.locator(
            "textarea[name='summary'], textarea[id='summary'], "
            "textarea, "
            "input[name='resumeTitle'], input[placeholder*='headline'], "
            "input[placeholder*='Resume'], input[id*='resumeHeadline'], "
            "input[class*='resumeTitle']"
        ).locator("visible=true").first
        await headline_input.click()
        await headline_input.fill("")
        await headline_input.fill(headline)
        await page.wait_for_timeout(500)

        # Click save
        save_btn = page.locator("button:has-text('Save'), button[type='submit']").first
        await save_btn.click(timeout=5000)
        await page.wait_for_timeout(2000)

        print(f"   Headline updated: {headline}")
        log_action(
            "headline_rotation",
            f"Updated headline on Naukri",
            diff_after=headline,
            status="success"
        )
        return True

    except Exception as e:
        print(f"   Failed to update headline: {e}")
        try:
            await page.screenshot(path="naukri_error.png")
            with open("naukri_error.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            print("   📸 Saved naukri_error.png and naukri_error.html for debugging.")
        except Exception as snap_e:
            print(f"   Could not capture error screenshot: {snap_e}")
            
        log_action("headline_rotation", f"Failed: {e}", status="failed")
        return False

# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("Pool-based headline:")
    print(f"  {pick_headline()}")

    print("\nAI-generated headline:")
    print(f"  {generate_ai_headline()}")
