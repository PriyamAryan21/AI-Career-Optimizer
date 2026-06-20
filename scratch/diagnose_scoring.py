"""
Diagnostic script: traces the ENTIRE scoring pipeline to find 
where jobs get bad scores or fall through to keyword fallback.
"""
import os, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    load_master_profile, TARGET_ROLES, GEMINI_API_KEY, GEMINI_MODEL,
    generate_with_retry
)
import google.generativeai as genai

print("=" * 70)
print("DIAGNOSTIC: AI Job Scoring Pipeline")
print("=" * 70)

# ── Step 1: Check model being used ──
print(f"\n[1] GEMINI_MODEL = '{GEMINI_MODEL}'")

# ── Step 2: Check profile data being sent ──
profile = load_master_profile()
user_skills = profile.get("skills", {}).get("proven", [])
user_experience = profile.get("personal", {}).get("experience_level", "")
user_roles = TARGET_ROLES

print(f"\n[2] PROFILE DATA:")
print(f"    Skills ({len(user_skills)}): {user_skills}")
print(f"    Experience: {user_experience}")
print(f"    Target Roles: {user_roles}")

# ── Step 3: Fetch real jobs and check what the prompt looks like ──
from intelligence.job_feed import (
    fetch_all_api_jobs, fetch_naukri_cached,
    _deduplicate, _pre_filter_relevant
)

print(f"\n[3] FETCHING REAL JOBS...")
all_jobs = fetch_all_api_jobs()
all_jobs.extend(fetch_naukri_cached())
print(f"    Raw: {len(all_jobs)}")
all_jobs = _deduplicate(all_jobs)
print(f"    After dedup: {len(all_jobs)}")
all_jobs = _pre_filter_relevant(all_jobs)
print(f"    After relevance filter: {len(all_jobs)}")

# ── Step 4: Inspect what the AI actually sees ──
top_n = 30  # default in score_jobs_with_ai
job_summaries = []
for i, job in enumerate(all_jobs[:top_n]):
    summary_line = (
        f"{i}: {job['title']} @ {job['company']} | "
        f"Skills: {', '.join(job['skills'][:8]) if job['skills'] else 'N/A'} | "
        f"Loc: {job['location']}"
    )
    job_summaries.append(summary_line)

print(f"\n[4] PROMPT INSPECTION (first 5 of {len(job_summaries)} jobs sent to AI):")
for line in job_summaries[:5]:
    print(f"    {line}")

# Check how many jobs have EMPTY skills
empty_skills_count = sum(1 for j in all_jobs[:top_n] if not j.get("skills"))
print(f"\n    ⚠️  Jobs with EMPTY skills list: {empty_skills_count}/{top_n}")
print(f"    ⚠️  Jobs with EMPTY description: {sum(1 for j in all_jobs[:top_n] if not j.get('description'))}/{top_n}")

# ── Step 5: Build the EXACT prompt and send it ──
user_summary = profile.get("personal", {}).get("summary", "")

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

print(f"\n[5] PROMPT LENGTH: {len(prompt)} chars")

# ── Step 6: Call Gemini and inspect the raw response ──
print(f"\n[6] CALLING GEMINI...")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

try:
    response = generate_with_retry(
        model, prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    raw_text = response.text.strip()
    
    # Clean
    text = re.sub(r'^```(?:json)?\s*', '', raw_text)
    text = re.sub(r'```$', '', text).strip()
    
    print(f"    ✅ Gemini responded ({len(text)} chars)")
    
    scores = json.loads(text)
    print(f"    ✅ JSON parsed: {len(scores)} score entries for {top_n} jobs")
    
    # Check for missing indices
    returned_indices = {item.get("index") for item in scores}
    expected_indices = set(range(top_n))
    missing = expected_indices - returned_indices
    if missing:
        print(f"    ⚠️  MISSING indices (Gemini skipped these): {sorted(missing)}")
    
    # Check score distribution
    score_values = [item.get("score", 0) for item in scores]
    print(f"\n[7] SCORE DISTRIBUTION:")
    print(f"    Max: {max(score_values)}")
    print(f"    Min: {min(score_values)}")
    print(f"    Avg: {sum(score_values)/len(score_values):.1f}")
    print(f"    Scores >= 80: {sum(1 for s in score_values if s >= 80)}")
    print(f"    Scores >= 60: {sum(1 for s in score_values if s >= 60)}")
    print(f"    Scores == 0:  {sum(1 for s in score_values if s == 0)}")
    
    # Show top 5 scored jobs
    scored = sorted(scores, key=lambda x: x.get("score", 0), reverse=True)
    print(f"\n[8] TOP 5 SCORED JOBS:")
    for item in scored[:5]:
        idx = item["index"]
        if idx < len(all_jobs):
            job = all_jobs[idx]
            print(f"    {item['score']}% - {job['title']} @ {job['company']}")
            print(f"         Skills: {job['skills'][:6]}")
            print(f"         Desc: {job.get('description', '')[:100]}...")
    
    # Show bottom 5
    print(f"\n[9] BOTTOM 5 SCORED JOBS:")
    for item in scored[-5:]:
        idx = item["index"]
        if idx < len(all_jobs):
            job = all_jobs[idx]
            print(f"    {item['score']}% - {job['title']} @ {job['company']}")
            print(f"         Skills: {job['skills'][:6]}")

    # ── Step 10: Check what the fallback would produce ──
    print(f"\n[10] FALLBACK KEYWORD SCORING (for comparison):")
    user_skills_lower = set(s.lower() for s in user_skills)
    for item in scored[:5]:
        idx = item["index"]
        if idx < len(all_jobs):
            job = all_jobs[idx]
            job_skills_lower = set(s.lower() for s in job.get("skills", []))
            overlap = user_skills_lower & job_skills_lower
            fallback_score = min(len(overlap) * 15, 100)
            print(f"    AI={item['score']}% vs Fallback={fallback_score}% - {job['title']}")
            print(f"         Overlapping skills: {overlap}")
            
except Exception as e:
    print(f"    ❌ GEMINI FAILED: {type(e).__name__}: {e}")
    print(f"    → This means ALL jobs would use fallback keyword scoring!")
    
    # Show what fallback would produce
    print(f"\n[FALLBACK] What keyword scoring produces:")
    user_skills_lower = set(s.lower() for s in user_skills)
    fallback_scores = []
    for i, job in enumerate(all_jobs[:top_n]):
        job_skills_lower = set(s.lower() for s in job.get("skills", []))
        overlap = user_skills_lower & job_skills_lower
        fb_score = min(len(overlap) * 15, 100)
        fallback_scores.append((fb_score, job["title"], job["company"], overlap))
    
    fallback_scores.sort(key=lambda x: x[0], reverse=True)
    for score, title, company, overlap in fallback_scores[:10]:
        print(f"    {score}% - {title} @ {company}")
        print(f"         Overlap: {overlap}")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
