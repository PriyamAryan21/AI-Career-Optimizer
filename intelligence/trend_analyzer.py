"""
Trend analyzer — uses Gemini to extract skill trends from scraped job data.
Takes raw job listings, identifies which skills appear most frequently,
and saves trend data to Supabase for gap analysis and dashboard.
"""


import json
import re
from datetime import datetime
from collections import Counter
import time
import google.generativeai as genai
from config.settings import GEMINI_API_KEY, TARGET_ROLES, generate_with_retry, GEMINI_MODEL
from database.models import save_trend_data, log_action


# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)


def _extract_skills_via_ai(jobs: list[dict], role: str) -> list[dict]:
    """
    Send job data to Gemini and ask it to extract + rank the most demanded skills.
    Returns list of dicts: [{skill, frequency, total_postings}]
    """
    # Build a condensed summary of jobs (to fit token limits)
    job_summaries = []
    for j in jobs[:20]:  # Cap at 20 jobs to stay within token limits
        summary = f"Title: {j['title']}, Skills: {', '.join(j['skills'])}"
        if j.get("description_snippet"):
            summary += f", Desc: {j['description_snippet'][:200]}"
        job_summaries.append(summary)

    jobs_text = "\n".join(job_summaries)
    total = len(jobs)

    prompt = f"""Analyze these {total} job listings for the role "{role}" and extract the most in-demand technical skills.

JOB LISTINGS:
{jobs_text}

INSTRUCTIONS:
1. Identify ALL technical skills, tools, frameworks, and technologies mentioned.
2. Count how many listings mention each skill (approximate frequency).
3. Combine synonyms (e.g., "React.js" and "ReactJS" = "React.js").
4. Return the top 25 skills sorted by frequency.

RESPOND ONLY with valid JSON — no markdown, no explanation:
[
  {{"skill": "React.js", "frequency": 15}},
  {{"skill": "Node.js", "frequency": 12}}
]
"""

    try:
        response = generate_with_retry(model, prompt)
        text = response.text.strip()

        # Clean markdown code fences if present
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        skills = json.loads(text)

        # Add total_postings count to each
        for s in skills:
            s["total_postings"] = total

        return skills

    except (json.JSONDecodeError, Exception) as e:
        print(f"   ⚠️ Gemini parsing failed for {role}: {e}")
        return _fallback_frequency_count(jobs)


def _fallback_frequency_count(jobs: list[dict]) -> list[dict]:
    """
    Fallback if Gemini fails — simple frequency count from the skills tags.
    No AI, just counting what Naukri already tagged.
    """
    counter = Counter()
    for j in jobs:
        for skill in j.get("skills", []):
            counter[skill.strip()] += 1

    total = len(jobs)
    return [
        {"skill": skill, "frequency": count, "total_postings": total}
        for skill, count in counter.most_common(25)
    ]


def analyze_trends(scraped_data: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """
    Main entry point. Takes output from scrape_all_roles() and:
    1. Sends each role's jobs to Gemini for skill extraction
    2. Saves trend data to Supabase
    3. Returns the full trend analysis

    Args:
        scraped_data: {role_name: [list of job dicts]} from job_scraper

    Returns:
        {role_name: [list of {skill, frequency, total_postings, demand_pct}]}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    all_trends = {}

    for role, jobs in scraped_data.items():
        if not jobs:
            print(f"⏭️ Skipping {role} — no jobs scraped")
            continue

        print(f"🧠 Analyzing trends for: {role} ({len(jobs)} listings)...")
        skills = _extract_skills_via_ai(jobs, role)

        # Save each skill to Supabase
        for s in skills:
            save_trend_data(
                skill_name=s["skill"],
                role=role,
                frequency=s["frequency"],
                total_postings=s["total_postings"],
                scraped_date=today
            )

        all_trends[role] = skills
        print(f"   ✅ {len(skills)} skills identified and saved")

        print("   ⏳ Waiting 15 seconds to respect Gemini API rate limits...")
        time.sleep(15)
    log_action(
        "analyze_trends",
        f"Analyzed trends for {len(all_trends)} roles",
        details=json.dumps({r: len(s) for r, s in all_trends.items()})
    )

    return all_trends


def get_top_skills_across_roles(trends: dict[str, list[dict]], top_n: int = 15) -> list[dict]:
    """
    Aggregate skills across ALL roles to find universally in-demand skills.
    Useful for headline rotation and resume keywords.
    """
    combined = Counter()
    for role, skills in trends.items():
        for s in skills:
            combined[s["skill"]] += s["frequency"]

    return [
        {"skill": skill, "total_mentions": count}
        for skill, count in combined.most_common(top_n)
    ]


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    from intelligence.job_scraper import scrape_all_roles

    print("Step 1: Scraping jobs...")
    scraped = scrape_all_roles(pages_per_role=1)  # 1 page for quick test

    print("\nStep 2: Analyzing trends with Gemini...")
    trends = analyze_trends(scraped)

    print("\n" + "=" * 60)
    print("📊 TOP SKILLS BY ROLE:")
    print("=" * 60)
    for role, skills in trends.items():
        print(f"\n🎯 {role}:")
        for s in skills[:10]:
            pct = round((s["frequency"] / s["total_postings"]) * 100, 1)
            print(f"   {s['skill']:.<30} {s['frequency']}/{s['total_postings']} ({pct}%)")

    print("\n🌐 TOP SKILLS OVERALL:")
    for s in get_top_skills_across_roles(trends):
        print(f"   {s['skill']:.<30} {s['total_mentions']} mentions")
