import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.job_feed import _normalize_job
from config.settings import generate_with_retry, GEMINI_API_KEY, GEMINI_MODEL
import google.generativeai as genai

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

jobs = []
for i in range(50):
    jobs.append(_normalize_job(
        title=f"Software Engineer {i}", company=f"Company {i}", location="Remote",
        url="", source="Test", skills=["Python", "React", "Node.js"]
    ))

from intelligence.job_feed import score_jobs_with_ai
jobs = score_jobs_with_ai(jobs, top_n=50)
for j in jobs[:5]:
    print(j["title"], j["match_score"])
