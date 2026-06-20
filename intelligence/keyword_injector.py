"""
Keyword injector — uses Gemini to rewrite profile content with trending keywords.
Produces rewritten content that naturally incorporates high-demand keywords
without changing facts. Feeds the freshness manager and resume generator.
"""

from config.settings import generate_with_retry
import json
import re
from collections import Counter
import google.generativeai as genai
from config.settings import GEMINI_API_KEY, TARGET_ROLES, load_master_profile, GEMINI_MODEL
from database.models import get_trends_by_role, log_action


genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)


def _get_trending_keywords(top_n: int = 20) -> list[str]:
    """Get top trending skills across all roles from Supabase."""
    combined = Counter()
    for role in TARGET_ROLES:
        trends = get_trends_by_role(role, limit=15)
        for t in trends:
            combined[t["skill_name"]] += 1
    return [skill for skill, _ in combined.most_common(top_n)]


def rewrite_summary(current_summary: str, trending_keywords: list[str]) -> str:
    """Rewrite profile summary to incorporate trending keywords. Preserves facts."""
    prompt = f"""Rewrite this professional summary to naturally incorporate more of the trending 
keywords below. Keep the SAME facts, achievements, and tone. Do NOT invent experience.
Keep it under 5 sentences. Make it ATS-friendly.

CURRENT SUMMARY:
{current_summary}

TRENDING KEYWORDS TO INCORPORATE (use what naturally fits):
{', '.join(trending_keywords[:15])}

Return ONLY the rewritten summary text, no quotes or labels."""

    try:
        response = generate_with_retry(model, prompt)
        return response.text.strip().strip('"')
    except Exception as e:
        print(f"⚠️ Summary rewrite failed: {e}")
        return current_summary


def rewrite_project_bullets(project_name: str, current_bullets: list[str], 
                            tech_stack: list[str], trending_keywords: list[str]) -> list[str]:
    """Rewrite project bullet points with trending keywords."""
    if not current_bullets:
        return []
        
    bullets_text = "\n".join(f"• {b}" for b in current_bullets)

    prompt = f"""Rewrite these project bullet points for {project_name}.
Incorporate trending keywords naturally. Keep ALL metrics and numbers intact. 
Start each bullet with a strong action verb. Keep the same number of bullets.

TECH STACK: {', '.join(tech_stack)}

CURRENT BULLETS:
{bullets_text}

TRENDING KEYWORDS (use what's relevant):
{', '.join(trending_keywords[:15])}

Return ONLY the bullet points, one per line, starting with •"""

    try:
        response = generate_with_retry(model, prompt)
        lines = [
            line.strip().lstrip("•").strip()
            for line in response.text.strip().split("\n")
            if line.strip() and line.strip().startswith("•")
        ]
        return lines if lines else current_bullets
    except Exception as e:
        print(f"⚠️ Project bullet rewrite failed: {e}")
        return current_bullets


def rewrite_experience_bullets(company: str, role: str,
                                current_bullets: list[str],
                                trending_keywords: list[str]) -> list[str]:
    """Rewrite experience bullet points with trending keywords."""
    bullets_text = "\n".join(f"• {b}" for b in current_bullets)

    prompt = f"""Rewrite these resume bullet points for {role} at {company}.
Incorporate trending keywords naturally. Keep ALL metrics and numbers. Each bullet should 
start with a strong action verb. Keep same number of bullets.

CURRENT BULLETS:
{bullets_text}

TRENDING KEYWORDS (use what's relevant):
{', '.join(trending_keywords[:15])}

Return ONLY the bullet points, one per line, starting with •"""

    try:
        response = model.generate_content(prompt)
        lines = [
            line.strip().lstrip("•").strip()
            for line in response.text.strip().split("\n")
            if line.strip() and line.strip().startswith("•")
        ]
        return lines if lines else current_bullets
    except Exception as e:
        print(f"⚠️ Experience rewrite failed: {e}")
        return current_bullets


def generate_optimized_content() -> dict:
    """
    Main entry point. Loads master_profile, fetches trending keywords,
    rewrites all content sections, returns the full optimized content dict.
    Does NOT modify master_profile.yaml — returns new content for the
    freshness_manager/resume_generator to use.
    """
    profile = load_master_profile()
    keywords = _get_trending_keywords()

    if not keywords:
        print("⚠️ No trend data. Run job_scraper + trend_analyzer first.")
        return {}

    print(f"🔑 Top keywords: {', '.join(keywords[:10])}")
    result = {"keywords_used": keywords[:15]}

    # 1. Rewrite summary
    print("📝 Rewriting summary...")
    original_summary = profile["personal"].get("summary", "")
    result["summary"] = {
        "original": original_summary,
        "rewritten": rewrite_summary(original_summary, keywords),
    }

    # 2. Rewrite each project
    print("📝 Rewriting project descriptions...")
    result["projects"] = []
    for proj in profile.get("projects", []):
        rewritten_bullets = rewrite_project_bullets(
            proj["name"], proj.get("bullets", []),
            proj.get("tech", []), keywords
        )
        result["projects"].append({
            "name": proj["name"],
            "original_bullets": proj.get("bullets", []),
            "rewritten_bullets": rewritten_bullets,
        })

    # 3. Rewrite experience bullets
    print("📝 Rewriting experience bullets...")
    result["experience"] = []
    for exp in profile.get("experience", []):
        rewritten_bullets = rewrite_experience_bullets(
            exp["company"], exp["role"],
            exp.get("bullets", []), keywords
        )
        result["experience"].append({
            "company": exp["company"],
            "role": exp["role"],
            "original_bullets": exp.get("bullets", []),
            "rewritten_bullets": rewritten_bullets,
        })

    log_action(
        "keyword_injection",
        f"Generated optimized content using {len(keywords)} trending keywords",
        details=json.dumps(keywords[:10])
    )

    print("✅ Content optimization complete!")
    return result


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    content = generate_optimized_content()
    if content:
        print(f"\n{'='*60}")
        print("OPTIMIZED SUMMARY:")
        print(f"{'='*60}")
        print(content["summary"]["rewritten"])

        for p in content["projects"]:
            print(f"\n{'='*60}")
            print(f"PROJECT: {p['name']}")
            print(f"{'='*60}")
            print(p["rewritten"][:300] + "...")
