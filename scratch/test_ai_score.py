import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.job_feed import get_hot_job_feed

if __name__ == "__main__":
    jobs = get_hot_job_feed(use_ai_scoring=True)
    for j in jobs[:5]:
        print(j["title"], j["company"], j["match_score"])
