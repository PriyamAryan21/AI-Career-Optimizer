"""
Skill gap analyzer — compares your profile skills vs market demand.
Generates suggestions (add/remove/update) and saves them to the
suggestions_queue for approval via dashboard or email.
"""

from config.settings import generate_with_retry
import json
import re
import google.generativeai as genai
from config.settings import GEMINI_API_KEY, TARGET_ROLES, load_master_profile, GEMINI_MODEL
from database.models import (
    get_trends_by_role, add_suggestion, log_action, get_pending_suggestions
)


genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)


def _get_your_skills() -> dict:
    """Load your skills from master_profile.yaml, categorized."""
    profile = load_master_profile()
    skills = profile.get("skills", {})
    return {
        "proven": skills.get("proven", []),
        "learning": skills.get("learning", []),
        "suggested": skills.get("suggested", []),
    }


def _get_market_demand() -> dict[str, list[dict]]:
    """Fetch latest trend data from Supabase for all target roles."""
    demand = {}
    for role in TARGET_ROLES:
        trends = get_trends_by_role(role, limit=20)
        if trends:
            demand[role] = trends
    return demand


def analyze_gaps() -> dict:
    """
    Main entry point. Compares your skills vs market demand and generates:
    - missing_skills: high-demand skills you don't have
    - strong_skills: your skills that are in high demand (leverage these)
    - declining_skills: your skills with low/no market demand
    - suggestions: AI-generated actionable items

    Returns the full analysis dict.
    """
    your_skills = _get_your_skills()
    market = _get_market_demand()

    if not market:
        print("⚠️ No trend data found. Run job_scraper + trend_analyzer first.")
        return {}

    all_your_skills = set(
        s.lower() for s in your_skills["proven"] + your_skills["learning"] + your_skills["suggested"]
    )

    # Collect all market skills with their demand percentages
    market_skills = {}
    for role, trends in market.items():
        for t in trends:
            skill = t["skill_name"]
            demand = float(t["avg_demand"])
            if skill.lower() in market_skills:
                market_skills[skill.lower()] = max(market_skills[skill.lower()], demand)
            else:
                market_skills[skill.lower()] = demand

    # Calculate gaps
    missing = []
    strong = []
    for skill, demand in sorted(market_skills.items(), key=lambda x: x[1], reverse=True):
        if skill not in all_your_skills:
            missing.append({"skill": skill, "demand_pct": demand})
        else:
            strong.append({"skill": skill, "demand_pct": demand})

    # Skills you have that aren't showing up in market data at all
    declining = [
        s for s in your_skills["proven"]
        if s.lower() not in market_skills
    ]

    analysis = {
        "your_skills": your_skills,
        "missing_high_demand": missing[:15],  # Top 15 gaps
        "strong_matches": strong,
        "potentially_declining": declining,
        "market_coverage": f"{len(strong)}/{len(market_skills)} market skills covered",
        "match_score": round((len(strong) / max(len(market_skills), 1)) * 100, 1),
    }

    print(f"📊 Gap Analysis Complete:")
    print(f"   Match Score: {analysis['match_score']}%")
    print(f"   Strong: {len(strong)} | Missing: {len(missing)} | Declining: {len(declining)}")

    return analysis


def generate_ai_suggestions(analysis: dict) -> list[dict]:
    """
    Send gap analysis to Gemini for intelligent, actionable suggestions.
    Saves each suggestion to the suggestions_queue (pending approval).
    """
    if not analysis:
        return []

    prompt = f"""You are a career optimization AI. Based on the following skill gap analysis, 
generate specific, actionable suggestions.

MY CURRENT SKILLS:
- Proven: {', '.join(analysis['your_skills']['proven'])}
- Learning: {', '.join(analysis['your_skills']['learning'])}

HIGH-DEMAND SKILLS I'M MISSING (top gaps):
{json.dumps(analysis['missing_high_demand'][:10], indent=2)}

MY SKILLS WITH STRONG MARKET DEMAND:
{json.dumps(analysis['strong_matches'][:10], indent=2)}

POTENTIALLY DECLINING SKILLS (low market mentions):
{', '.join(analysis['potentially_declining'][:10])}

MATCH SCORE: {analysis['match_score']}%

INSTRUCTIONS:
Generate 5-8 suggestions. Each suggestion must be one of these types:
- "add_skill": A specific, granular ATS-friendly hard skill noun to add (e.g., "Stripe API", "PCI-DSS", "Docker", "PostgreSQL"). DO NOT suggest broad, abstract concepts or soft skills like "Fintech Domain Knowledge" or "Leadership". Only suggest concrete tools, frameworks, protocols, or specific hard technical domains.
- "remove_skill": A skill to consider removing or de-emphasizing  
- "update_content": A change to how I present existing skills/experience, or suggesting to add a broad domain expertise (like Fintech) into the profile summary.

For each, explain WHY in 1-2 sentences.

RESPOND ONLY with valid JSON:
[
  {{
    "type": "add_skill",
    "target_skill": "AWS",
    "suggestion": "Add AWS/Cloud skills to profile",
    "reasoning": "AWS appears in 65% of Full Stack listings. Adding it would significantly boost match rate."
  }}
]
"""

    try:
        response = generate_with_retry(model, prompt)
        text = response.text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        suggestions = json.loads(text)

        # Save each to the suggestions queue (awaiting approval)
        saved = []
        for s in suggestions:
            stype = s.get("type", "other")
            # Map to our DB enum values
            if stype not in ("add_skill", "remove_skill", "update_content"):
                stype = "other"
                
            target = s.get("target_skill", "")
            encoded_text = f"{target}:::{s['suggestion']}" if target else s['suggestion']

            add_suggestion(
                suggestion_type=stype,
                suggestion_text=encoded_text,
                ai_reasoning=s.get("reasoning", "")
            )
            saved.append(s)

        print(f"✅ {len(saved)} suggestions saved to approval queue")
        log_action(
            "gap_analysis",
            f"Generated {len(saved)} skill suggestions",
            details=json.dumps(saved)
        )
        return saved

    except Exception as e:
        print(f"❌ AI suggestion generation failed: {e}")
        return []


def run_full_analysis() -> dict:
    """Convenience function: run gap analysis + generate suggestions in one call."""
    analysis = analyze_gaps()
    suggestions = generate_ai_suggestions(analysis)
    analysis["suggestions"] = suggestions
    return analysis


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_full_analysis()

    if result:
        print(f"\n{'='*60}")
        print(f"📊 SKILL GAP REPORT")
        print(f"{'='*60}")
        print(f"\nMatch Score: {result['match_score']}%")

        print(f"\n🟢 Strong Skills (in-demand):")
        for s in result["strong_matches"][:10]:
            print(f"   ✅ {s['skill']} ({s['demand_pct']}% demand)")

        print(f"\n🔴 Missing High-Demand Skills:")
        for s in result["missing_high_demand"][:10]:
            print(f"   ❌ {s['skill']} ({s['demand_pct']}% demand)")

        print(f"\n🟡 Potentially Declining:")
        for s in result.get("potentially_declining", [])[:5]:
            print(f"   ⚠️ {s}")

        print(f"\n💡 AI Suggestions (saved to approval queue):")
        for s in result.get("suggestions", []):
            print(f"   [{s['type']}] {s['suggestion']}")
            print(f"      → {s['reasoning']}")
