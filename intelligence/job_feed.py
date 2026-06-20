"""
Hot Job Feed — aggregates job listings from multiple free sources.
Sources:
    1. Remotive API (no key needed, remote dev jobs)
    2. Adzuna API (free key, India-focused)
    3. JSearch / RapidAPI (free key, aggregates LinkedIn/Indeed/Glassdoor)
    4. Naukri (cached from existing scraper runs)

Normalizes all results into a unified format with match scoring via Gemini.
"""

import json
import re
import time
import requests
from datetime import datetime, timedelta
from collections import Counter

from config.settings import (
    load_master_profile, TARGET_ROLES, GEMINI_API_KEY, GEMINI_MODEL
)

# Optional API keys (loaded from env)
import os
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


# ── Unified Job Format ────────────────────────────────
def _normalize_job(
    title: str, company: str, location: str, url: str,
    source: str, skills: list = None, salary: str = "",
    posted: str = "", description: str = ""
) -> dict:
    """Normalize a job into a standard format across all sources."""
    return {
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip() if location else "Not specified",
        "apply_url": url.strip(),
        "source": source,
        "skills": skills or [],
        "salary": salary,
        "posted": posted,
        "description": description[:500] if description else "",
        "match_score": 0,  # Will be filled by Gemini scoring
    }

def _get_exp_keyword() -> str:
    """Fetch the experience keyword dynamically from YAML to use in API searches."""
    profile = load_master_profile()
    return profile.get("personal", {}).get("experience_keyword", "").strip()


# ── Profile-aware search terms ────────────────────────
def _get_search_queries() -> list[str]:
    """Build search queries from TARGET_ROLES and top profile skills."""
    profile = load_master_profile()
    top_skills = profile.get("skills", {}).get("proven", [])[:6]
    
    queries = []
    # Use target roles directly
    for role in TARGET_ROLES[:3]:
        queries.append(role)
    # Add skill-based queries
    skill_combos = [
        "React developer", "Node.js engineer", ".NET Core developer",
        "Full Stack developer", "Python developer", "TypeScript React"
    ]
    for combo in skill_combos:
        if any(s.lower() in combo.lower() for s in top_skills):
            queries.append(combo)
    
    return list(dict.fromkeys(queries))[:5]  # Deduplicated, max 5


# ── Source 1: Remotive (FREE, no API key) ─────────────
def fetch_remotive_jobs(limit: int = 25) -> list[dict]:
    """
    Fetch remote dev jobs from Remotive using profile-aware search.
    Uses the search= param to query by target roles and skills.
    Free API, no key needed. Max 4 calls/day recommended.
    """
    print("   📡 Fetching from Remotive (profile-filtered)...")
    jobs = []
    try:
        search_queries = _get_search_queries()
        exp_keyword = _get_exp_keyword()
        for query in search_queries[:3]:  # Max 3 queries to stay within limits
            search_term = search_term = f"{query} {exp_keyword}".strip().replace(" ", "%20")
            url = (
                f"https://remotive.com/api/remote-jobs"
                f"?category=software-dev&search={search_term}&limit={limit}"
            )
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for job in data.get("jobs", []):
                    tags = job.get("tags", [])
                    jobs.append(_normalize_job(
                        title=job.get("title", ""),
                        company=job.get("company_name", ""),
                        location=job.get("candidate_required_location", "Worldwide"),
                        url=job.get("url", ""),
                        source="Remotive",
                        skills=tags,
                        salary=job.get("salary", ""),
                        posted=job.get("publication_date", "")[:10],
                        description=_clean_html(job.get("description", ""))
                    ))
            time.sleep(1)  # Be polite
        print(f"   ✅ Remotive: {len(jobs)} jobs")
    except Exception as e:
        print(f"   ⚠️ Remotive failed: {e}")
    return jobs


# ── Source 2: Adzuna (FREE tier, needs key) ───────────
def fetch_adzuna_jobs(limit: int = 20) -> list[dict]:
    """
    Fetch jobs from Adzuna API (India focus).
    Free tier: 250 calls/day. Register at https://developer.adzuna.com/
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("   ⏭️ Adzuna: Skipped (no API key configured)")
        return []

    print("   📡 Fetching from Adzuna (India)...")
    jobs = []
    try:
        exp_keyword = _get_exp_keyword()
        for role in TARGET_ROLES[:3]:  # Limit to 3 roles to conserve quota
            query = f"{role} {exp_keyword}".strip().replace(" ", "%20")
            url = (
                f"https://api.adzuna.com/v1/api/jobs/in/search/1"
                f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
                f"&results_per_page={limit}&what={query}"
                f"&content-type=application/json"
            )
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for result in data.get("results", []):
                    salary_min = result.get("salary_min", "")
                    salary_max = result.get("salary_max", "")
                    salary = ""
                    if salary_min and salary_max:
                        salary = f"₹{int(salary_min):,} - ₹{int(salary_max):,}"
                    elif salary_min:
                        salary = f"₹{int(salary_min):,}+"

                    jobs.append(_normalize_job(
                        title=result.get("title", ""),
                        company=result.get("company", {}).get("display_name", ""),
                        location=result.get("location", {}).get("display_name", "India"),
                        url=result.get("redirect_url", ""),
                        source="Adzuna",
                        skills=[],  # Adzuna doesn't return structured skills
                        salary=salary,
                        posted=result.get("created", "")[:10],
                        description=_clean_html(result.get("description", ""))
                    ))
            time.sleep(1)
        print(f"   ✅ Adzuna: {len(jobs)} jobs")
    except Exception as e:
        print(f"   ⚠️ Adzuna failed: {e}")
    return jobs


# ── Source 3: JSearch / RapidAPI (FREE 200/mo) ────────
def fetch_jsearch_jobs(limit: int = 10) -> list[dict]:
    """
    Fetch jobs from JSearch (aggregates LinkedIn, Indeed, Glassdoor).
    Free tier: 200 requests/month. Register at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    """
    if not RAPIDAPI_KEY:
        print("   ⏭️ JSearch: Skipped (no RapidAPI key configured)")
        return []

    print("   📡 Fetching from JSearch (LinkedIn/Indeed/Glassdoor)...")
    jobs = []
    try:
        exp_keyword = _get_exp_keyword()
        for role in TARGET_ROLES[:2]:  # Only 2 roles to conserve monthly quota
            url = "https://jsearch.p.rapidapi.com/search"
            params = {
                "query": f"{role} {exp_keyword} in India",
                "page": "1",
                "num_pages": "1",
                "date_posted": "week",
            }
            headers = {
                "X-RapidAPI-Key": RAPIDAPI_KEY,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
            }
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for result in data.get("data", []):
                    jobs.append(_normalize_job(
                        title=result.get("job_title", ""),
                        company=result.get("employer_name", ""),
                        location=f"{result.get('job_city', '')}, {result.get('job_state', '')}".strip(", "),
                        url=result.get("job_apply_link", "") or result.get("job_google_link", ""),
                        source=result.get("job_publisher", "JSearch"),
                        skills=result.get("job_required_skills") or [],
                        salary=_format_jsearch_salary(result),
                        posted=result.get("job_posted_at_datetime_utc", "")[:10],
                        description=result.get("job_description", "")[:500]
                    ))
            time.sleep(2)  # Be polite with free tier
        print(f"   ✅ JSearch: {len(jobs)} jobs")
    except Exception as e:
        print(f"   ⚠️ JSearch failed: {e}")
    return jobs


def _format_jsearch_salary(result: dict) -> str:
    """Format JSearch salary data."""
    sal_min = result.get("job_min_salary")
    sal_max = result.get("job_max_salary")
    sal_currency = result.get("job_salary_currency", "")
    sal_period = result.get("job_salary_period", "")
    if sal_min and sal_max:
        return f"{sal_currency} {sal_min:,.0f} - {sal_max:,.0f} {sal_period}".strip()
    elif sal_min:
        return f"{sal_currency} {sal_min:,.0f}+ {sal_period}".strip()
    return ""


# ── Source 4: Naukri (from existing scraper data) ─────
def fetch_naukri_cached() -> list[dict]:
    """
    Load jobs from the last Naukri scrape stored in our database.
    These come from intelligence/job_scraper.py runs.
    """
    print("   📡 Loading cached Naukri data...")
    jobs = []
    try:
        from database.models import _get_connection
        conn = _get_connection()
        cur = conn.cursor()
        # Check if scraped_jobs table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'scraped_jobs'
            )
        """)
        exists = cur.fetchone()[0]
        if not exists:
            print("   ⏭️ Naukri: No scraped_jobs table (run scraper first)")
            cur.close()
            conn.close()
            return []

        cur.execute("""
            SELECT title, company, location, apply_link, skills, scraped_date
            FROM scraped_jobs
            WHERE scraped_date >= %s
            ORDER BY scraped_date DESC
            LIMIT 50
        """, ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),))
        
        columns = [desc[0] for desc in cur.description]
        for row in cur.fetchall():
            r = dict(zip(columns, row))
            skill_list = r.get("skills", "")
            if isinstance(skill_list, str):
                skill_list = [s.strip() for s in skill_list.split(",") if s.strip()]
            
            jobs.append(_normalize_job(
                title=r.get("title", ""),
                company=r.get("company", ""),
                location=r.get("location", "India"),
                url=r.get("apply_link", ""),
                source="Naukri",
                skills=skill_list,
                posted=str(r.get("scraped_date", "")),
            ))
        cur.close()
        conn.close()
        print(f"   ✅ Naukri (cached): {len(jobs)} jobs")
    except Exception as e:
        print(f"   ⚠️ Naukri cache failed: {e}")
    return jobs


# ── Deduplication ─────────────────────────────────────
def _deduplicate(jobs: list[dict]) -> list[dict]:
    """Remove duplicate jobs based on title + company similarity."""
    seen = set()
    unique = []
    for job in jobs:
        key = f"{job['title'].lower().strip()[:40]}|{job['company'].lower().strip()[:20]}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ── AI Match Scoring ──────────────────────────────────
def score_jobs_with_ai(jobs: list[dict], top_n: int = 30) -> list[dict]:
    """
    Use Gemini to score each job's match against the user's profile.
    Returns jobs sorted by match_score (highest first).
    """
    if not jobs:
        return []
    
    profile = load_master_profile()
    user_skills = profile.get("skills", {}).get("proven", [])
    user_summary = profile.get("personal", {}).get("summary", "")
    user_roles = TARGET_ROLES
    user_experience = profile.get("personal", {}).get("experience_level", "Entry Level / Fresher")

    # Build a compact job list for the AI prompt
    job_summaries = []
    for i, job in enumerate(jobs[:top_n]):
        job_summaries.append(
            f"{i}: {job['title']} @ {job['company']} | "
            f"Skills: {', '.join(job['skills'][:8]) if job['skills'] else 'N/A'} | "
            f"Loc: {job['location']}"
        )

    prompt = f"""You are a career advisor. Score each job's match against this candidate's profile.
CANDIDATE:
- Target roles: {', '.join(user_roles)}
- Skills: {', '.join(user_skills)}
- Experience Level: {user_experience}
- Summary: {user_summary[:200]}
JOBS:
{chr(10).join(job_summaries)}
For EACH job, return a match score from 0-100 based on:
- Skill overlap (40%)
- Role relevance (30%)
- Experience level fit (30%). CRITICAL: Use the candidate's 'Experience Level' to strictly evaluate match. Severely penalize (score < 40) jobs requiring more experience than the candidate has.
Return ONLY a JSON array of objects: [{{"index": 0, "score": 85}}, ...]
No markdown, no explanation."""

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        from config.settings import generate_with_retry
        response = generate_with_retry(model, prompt)
        text = response.text.strip()
        
        # Clean markdown fences
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        
        scores = json.loads(text)
        for item in scores:
            idx = item.get("index", -1)
            score = item.get("score", 0)
            if 0 <= idx < len(jobs):
                jobs[idx]["match_score"] = score
    except Exception as e:
        print(f"   ⚠️ AI scoring failed: {e}")
        # Fallback: simple keyword-based scoring
        for job in jobs:
            overlap = len(set(s.lower() for s in job.get("skills", [])) & 
                         set(s.lower() for s in user_skills))
            job["match_score"] = min(overlap * 15, 100)

    # Sort by match score
    jobs.sort(key=lambda x: x["match_score"], reverse=True)
    return jobs


# ── HTML Cleanup ──────────────────────────────────────
def _clean_html(text: str) -> str:
    """Strip HTML tags from description text."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:500]


# ── Profile Relevance Pre-filter ──────────────────────
def _pre_filter_relevant(jobs: list[dict]) -> list[dict]:
    """
    Drop obviously irrelevant jobs before sending to Gemini.
    Keeps jobs whose title or skills overlap with the user's profile.
    """
    profile = load_master_profile()
    user_skills = set(s.lower() for s in profile.get("skills", {}).get("proven", []))
    
    # Keywords that indicate a relevant role
    relevant_keywords = {
        "developer", "engineer", "software", "full stack", "fullstack",
        "frontend", "front-end", "backend", "back-end", "react", "node",
        ".net", "dotnet", "python", "typescript", "javascript",
        "data scientist", "ml engineer", "ai engineer", "devops",
        "web developer", "sde", "swe", "programmer",
    }
    # Add user's target role keywords
    for role in TARGET_ROLES:
        for word in role.lower().split():
            if len(word) > 2:
                relevant_keywords.add(word)
    
    filtered = []
    for job in jobs:
        title_lower = job["title"].lower()
        desc_lower = job.get("description", "").lower()
        job_skills = set(s.lower() for s in job.get("skills", []))
        
        # Check 1: Title contains a relevant keyword
        title_match = any(kw in title_lower for kw in relevant_keywords)
        
        # Check 2: Skills overlap with user's skills
        skill_overlap = bool(user_skills & job_skills)
        
        # Check 3: Description mentions user's core skills
        desc_match = any(skill.lower() in desc_lower for skill in list(user_skills)[:8])
        
        if title_match or skill_overlap or desc_match:
            filtered.append(job)
    
    dropped = len(jobs) - len(filtered)
    if dropped > 0:
        print(f"   🔍 Pre-filter: Dropped {dropped} irrelevant jobs")
    
    return filtered


def fetch_all_api_jobs() -> list[dict]:
    """
    Pure data fetching function. Pulls from all configured APIs.
    No deduplication, no filtering, no DB saving.
    """
    all_jobs = []
    all_jobs.extend(fetch_remotive_jobs(limit=15))
    all_jobs.extend(fetch_adzuna_jobs(limit=15))
    all_jobs.extend(fetch_jsearch_jobs(limit=10))
    # We do NOT include fetch_naukri_cached() here to avoid circular logic
    return all_jobs


# ── Main Feed Function ────────────────────────────────
def get_hot_job_feed(use_ai_scoring: bool = True) -> list[dict]:
    """
    Main entry point — fetches from all sources, deduplicates,
    pre-filters for relevance, and scores with Gemini AI.
    Returns a sorted list of the best matching jobs.
    """
    print("\n🔥 Building Hot Job Feed...")
    
    all_jobs = fetch_all_api_jobs()
    all_jobs.extend(fetch_naukri_cached())
    
    print(f"\n   📊 Total raw jobs: {len(all_jobs)}")
    
    # Deduplicate
    all_jobs = _deduplicate(all_jobs)
    print(f"   📊 After dedup: {len(all_jobs)}")
    
    # Pre-filter: drop irrelevant jobs (sales, accounting, etc.)
    all_jobs = _pre_filter_relevant(all_jobs)
    print(f"   📊 After relevance filter: {len(all_jobs)}")
    
    # Score with AI
    if use_ai_scoring and all_jobs:
        print("   🧠 Scoring jobs with Gemini...")
        all_jobs = score_jobs_with_ai(all_jobs, top_n=50)
    
    # DB Save Logic
    if all_jobs:
        try:
            from database.models import save_hot_jobs
            # Save only the top 10 best matches
            save_hot_jobs(all_jobs[:10])
            print("   💾 Saved Top 10 jobs to database.")
        except Exception as e:
            print(f"   ⚠️ Failed to save jobs to DB: {e}")

    print(f"   ✅ Hot Job Feed ready: {len(all_jobs)} jobs")
    return all_jobs


# ── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    jobs = get_hot_job_feed(use_ai_scoring=True)
    
    print(f"\n{'='*70}")
    print(f"  TOP 10 MATCHING JOBS")
    print(f"{'='*70}")
    
    for i, job in enumerate(jobs[:10], 1):
        print(f"\n  #{i} [{job['match_score']}% match] {job['title']}")
        print(f"     🏢 {job['company']} | 📍 {job['location']}")
        print(f"     📡 Source: {job['source']}")
        if job['salary']:
            print(f"     💰 {job['salary']}")
        print(f"     🔗 {job['apply_url'][:80]}...")
