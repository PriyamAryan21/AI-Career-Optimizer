"""
End-to-end test of the FIXED scoring pipeline.
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.job_feed import (
    fetch_all_api_jobs, fetch_naukri_cached,
    _deduplicate, _pre_filter_relevant, score_jobs_with_ai
)

print("=" * 70)
print("END-TO-END TEST: Fixed Scoring Pipeline")
print("=" * 70)

# Fetch
all_jobs = fetch_all_api_jobs()
all_jobs.extend(fetch_naukri_cached())
print(f"\nRaw: {len(all_jobs)}")
all_jobs = _deduplicate(all_jobs)
print(f"After dedup: {len(all_jobs)}")
all_jobs = _pre_filter_relevant(all_jobs)
print(f"After relevance filter: {len(all_jobs)}")

# Score with the FIXED function
print("\n🧠 Scoring with FIXED pipeline...")
scored = score_jobs_with_ai(all_jobs, top_n=50)

# Results
print(f"\n{'='*70}")
print(f"TOP 15 RESULTS:")
print(f"{'='*70}")
for i, job in enumerate(scored[:15], 1):
    print(f"  #{i:02d} [{job['match_score']:3d}%] {job['title']}")
    print(f"       🏢 {job['company']} | 📍 {job['location']}")
    print(f"       📡 {job['source']} | Skills: {job['skills'][:5]}")
    desc = job.get('description', '')[:80]
    if desc:
        print(f"       📝 {desc}...")
    print()

# Score distribution
scores = [j['match_score'] for j in scored]
print(f"\nSCORE DISTRIBUTION:")
print(f"  >= 90%: {sum(1 for s in scores if s >= 90)}")
print(f"  >= 80%: {sum(1 for s in scores if s >= 80)}")
print(f"  >= 60%: {sum(1 for s in scores if s >= 60)}")
print(f"  >= 40%: {sum(1 for s in scores if s >= 40)}")
print(f"  == 0%:  {sum(1 for s in scores if s == 0)}")
print(f"  Total:  {len(scores)}")
