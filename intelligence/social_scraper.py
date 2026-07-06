import os
import re
import time
import random
import urllib.parse
import requests
from bs4 import BeautifulSoup
from database.models import save_verified_email_job
from config.settings import TARGET_ROLES

def scrape_hackernews_hiring():
    """
    Scrapes the official Hacker News 'Who is Hiring?' threads via their free public API.
    Zero rate limits, no blocks, and hundreds of authentic startup jobs with direct emails!
    """
    print("   🌐 Checking Hacker News 'Who is Hiring' (100% Free API)...")
    found_count = 0
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    try:
        # Get the 'whoishiring' user's submissions
        user_res = requests.get("https://hacker-news.firebaseio.com/v0/user/whoishiring.json").json()
        if not user_res or 'submitted' not in user_res:
            return 0
            
        # The most recent submissions are first. We find the latest "Ask HN: Who is hiring?"
        latest_thread_id = None
        for post_id in user_res['submitted'][:5]:
            post = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{post_id}.json").json()
            if post and post.get('title', '').startswith('Ask HN: Who is hiring?'):
                latest_thread_id = post_id
                print(f"   ✅ Found latest HN Hiring Thread: {post['title']}")
                break
                
        if latest_thread_id:
            # Fetch comments (jobs)
            thread = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{latest_thread_id}.json").json()
            kids = thread.get('kids', [])[:100]  # Check top 100 posts to save time
            
            for kid_id in kids:
                comment = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json").json()
                if not comment or 'text' not in comment or comment.get('deleted'):
                    continue
                
                text = comment['text']
                # Strip HTML tags
                clean_text = BeautifulSoup(text, "html.parser").get_text()
                
                # Check if it matches our target roles
                is_relevant = any(role.lower().split()[0] in clean_text.lower() for role in TARGET_ROLES)
                if not is_relevant:
                    continue
                    
                emails = list(set(re.findall(email_pattern, clean_text)))
                if emails:
                    target_email = emails[0]
                    # Extract roughly the first line as company name
                    company_line = clean_text.split('\n')[0][:50].replace('|', '').strip()
                    
                    save_verified_email_job(
                        title="Software Engineer (HN)",
                        company=company_line,
                        email=target_email,
                        description=f"HackerNews Thread {latest_thread_id}",
                        source="Hacker News API"
                    )
                    found_count += 1
    except Exception as e:
        print(f"   ⚠️ HN Scrape failed: {e}")
        
    return found_count

def scrape_social_posts():
    """
    Searches for public LinkedIn and Twitter posts containing explicit hiring emails.
    Implements Free-Tier Stealth mechanisms (User-Agent rotation, delays).
    """
    print("=" * 60)
    print("  🕵️‍♂️ Starting Free-Tier Social Media Scraping")
    print("=" * 60)

    total_found = 0
    
    # 1. Scrape Hacker News (100% Free & Reliable)
    hn_count = scrape_hackernews_hiring()
    total_found += hn_count
    print(f"   ✅ Hacker News yielded {hn_count} emails.")
    
    # 2. Scrape DuckDuckGo with Stealth
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
    ]
    
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

    for role in TARGET_ROLES:
        headers = {"User-Agent": random.choice(user_agents)}
        query = f'site:linkedin.com/posts "hiring" "{role}" "@gmail.com" OR "@"'
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        print(f"   Searching public posts for: {role}...")
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                results = soup.find_all('div', class_='result__body')
                
                for res in results:
                    snippet_el = res.find('a', class_='result__snippet')
                    if not snippet_el:
                        continue
                        
                    text = snippet_el.get_text()
                    emails = list(set(re.findall(email_pattern, text)))
                    
                    if emails:
                        company_domain = emails[0].split('@')[-1].split('.')[0].capitalize()
                        if company_domain.lower() in ["gmail", "yahoo", "hotmail", "outlook"]:
                            company_domain = "Fast-moving Startup"
                            
                        save_verified_email_job(
                            title=role,
                            company=company_domain,
                            email=emails[0],
                            description=f"Extracted from Social Post: {text}",
                            source="Social Scraper"
                        )
                        total_found += 1
            else:
                print(f"   ⚠️ Search blocked ({response.status_code}). Engine cooling down...")
                break # Stop hitting DDG if blocked to let IP cool off
                
        except Exception as e:
            print(f"   ⚠️ Failed to scrape for {role}: {e}")
            
        # Stealth Delay: Wait 5-10 seconds between searches so we don't get blocked
        sleep_time = random.uniform(5, 10)
        print(f"   ⏳ Sleeping {sleep_time:.1f}s to avoid bot detection...")
        time.sleep(sleep_time)

    print(f"\n✅ Total Social Scraping complete. Added {total_found} verified emails to the pool.")

if __name__ == "__main__":
    scrape_social_posts()
