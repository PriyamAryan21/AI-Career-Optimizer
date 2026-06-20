import re
from database.models import save_profile_metrics

async def scrape_and_save_analytics(page):
    """
    Scrapes profile analytics from the Naukri homepage and saves to database.
    Expects an authenticated Playwright page object.
    """
    print("   Navigating to analytics homepage...")
    try:
        await page.goto("https://www.naukri.com/mnjuser/performance", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)  # Wait for initial React widgets to mount
        
        # Scroll to bottom to trigger any lazy-loaded widgets (like Profile Completeness)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        text_content = await page.locator("body").inner_text()
        
        search_app_90d = 0
        search_app_7d = 0
        recruiter_actions_90d = 0
        profile_completeness = 0
        activity_level = "UNKNOWN"
        
        # Example: "69Search appearances24Recruiter actions"
        m1 = re.search(r'(\d+)\s*Search appearances(?! in last)', text_content, re.IGNORECASE)
        if m1:
            search_app_90d = int(m1.group(1))
            
        # Example: "0 Search appearances in last \n 7 Days"
        m2 = re.search(r'(\d+)\s*Search appearances in last.*?7 Days', text_content, re.IGNORECASE | re.DOTALL)
        if m2:
            search_app_7d = int(m2.group(1))
            
        # Example: "24Recruiter actions"
        m3 = re.search(r'(\d+)\s*Recruiter actions', text_content, re.IGNORECASE)
        if m3:
            recruiter_actions_90d = int(m3.group(1))
            
        m4 = re.search(r'Profile completeness\s*(\d+)%?', text_content, re.IGNORECASE)
        if m4:
            profile_completeness = int(m4.group(1))
            
        # Example: "Activity level\nHIGH"
        m5 = re.search(r'Activity level\s*(HIGH|MEDIUM|LOW)', text_content, re.IGNORECASE)
        if m5:
            activity_level = m5.group(1).upper()
            
        print(f"   📈 Extracted Metrics:")
        print(f"      - Search Appearances (90d): {search_app_90d}")
        print(f"      - Search Appearances (7d):  {search_app_7d}")
        print(f"      - Recruiter Actions:        {recruiter_actions_90d}")
        print(f"      - Activity Level:           {activity_level}")
        print(f"      - Profile Completeness:     {profile_completeness}%")
        
        save_profile_metrics(
            search_appearances_90d=search_app_90d,
            search_appearances_7d=search_app_7d,
            recruiter_actions_90d=recruiter_actions_90d,
            activity_level=activity_level,
            profile_completeness=profile_completeness
        )
        return True
        
    except Exception as e:
        print(f"   ❌ Failed to scrape analytics: {e}")
        return False
