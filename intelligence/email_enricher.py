import os
import requests
import json
import time
from database.models import _get_connection, save_verified_email_job

# You will need to add HUNTER_API_KEY to your .env file
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")

def enrich_hot_jobs():
    """
    Scans the top hot_jobs that lack direct emails.
    Uses Hunter.io (or Apollo API format) to find the HR/Recruiter email for the company.
    If found, saves it directly to the verified_email_jobs table.
    """
    print("=" * 60)
    print("  🔍 Starting Data Enrichment (Hunter.io / Apollo)")
    print("=" * 60)

    if not HUNTER_API_KEY:
        print("⚠️  HUNTER_API_KEY not found in .env. Please configure it to use Enrichment.")
        print("    (You can get a free tier API key from hunter.io)")
        return

    conn = _get_connection()
    cur = conn.cursor()
    
    # We take the top 20 hot jobs
    cur.execute("SELECT title, company, skills, apply_url FROM hot_jobs ORDER BY match_score DESC LIMIT 20")
    jobs = cur.fetchall()

    enriched_count = 0
    for job in jobs:
        title, company, skills, apply_url = job
        
        # We need the company domain. Hunter has a company name to domain endpoint, 
        # or we can use domain search with company name directly.
        url = f"https://api.hunter.io/v2/domain-search?company={company}&department=hr&api_key={HUNTER_API_KEY}"
        
        try:
            print(f"   Searching HR emails for {company}...")
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json().get("data", {})
                emails = data.get("emails", [])
                
                if emails:
                    target_email = emails[0].get("value")
                    print(f"   ✅ Found verified email: {target_email}")
                    
                    # Save to verified pool
                    save_verified_email_job(
                        title=title,
                        company=company,
                        email=target_email,
                        description=f"Skills needed: {skills} | Link: {apply_url}",
                        source="Hunter.io Enrichment"
                    )
                    enriched_count += 1
                else:
                    print(f"   ❌ No HR emails found for {company}.")
            else:
                print(f"   ⚠️ API Error {response.status_code}: {response.text}")
                
        except Exception as e:
            print(f"   ⚠️ Enrichment failed for {company}: {e}")
        
        # Sleep to respect API rate limits
        time.sleep(2)

    cur.close()
    conn.close()
    print(f"\n✅ Enrichment complete. Added {enriched_count} verified emails to the pool.")

if __name__ == "__main__":
    enrich_hot_jobs()
