"""
Naukri authentication & session management.
- First-time: opens a visible browser for manual login + OTP
- Subsequent runs: loads saved cookies from Supabase
- If session expired: sends email alert
"""

import json
import sys
import os
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from config.settings import (
    NAUKRI_LOGIN_URL, NAUKRI_PROFILE_URL, NAUKRI_BASE_URL,
    SESSION_DIR
)
from database.models import update_session_status, get_session_status
from notifications.email_notifier import notify_session_expired


# Local cookie backup path (for local dev; Supabase is primary)
LOCAL_COOKIES_PATH = SESSION_DIR / "naukri_cookies.json"


async def manual_login():
    """
    Opens a VISIBLE browser for manual login.
    You complete the login + OTP, then press Enter in the terminal.
    Cookies are saved to Supabase + local backup.
    """
    print("\n🔐 Opening Naukri login page...")
    print("   Complete the login (including OTP) in the browser.")
    print("   Once you're on the dashboard/profile page, come back here and press ENTER.\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Visible browser
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(NAUKRI_LOGIN_URL, wait_until="domcontentloaded")

        # Wait for user to complete login manually
        input("✅ Press ENTER after you've logged in successfully...")

        # Save cookies
        cookies = await context.cookies()
        cookies_json = json.dumps(cookies)

        # Save to local file as backup
        LOCAL_COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCAL_COOKIES_PATH, "w") as f:
            f.write(cookies_json)

        # Save to Supabase (primary storage for GitHub Actions)
        update_session_status("active", cookies_json)

        await browser.close()

    print(f"✅ Session saved! ({len(cookies)} cookies captured)")
    print(f"   Local backup: {LOCAL_COOKIES_PATH}")
    print(f"   Supabase: synced")
    return True


async def load_session(context):
    """
    Load saved cookies into a Playwright browser context.
    Tries Supabase first, then local file as fallback.
    Returns True if cookies were loaded, False otherwise.
    """
    cookies_json = None

    # Try Supabase first (works in GitHub Actions)
    session = get_session_status()
    if session.get("status") == "active" and session.get("cookies_data"):
        cookies_json = session["cookies_data"]
        print("🔑 Loaded cookies from Supabase")

    # Fallback to local file (for local development)
    elif LOCAL_COOKIES_PATH.exists():
        with open(LOCAL_COOKIES_PATH, "r") as f:
            cookies_json = f.read()
        print("🔑 Loaded cookies from local file")

    if not cookies_json:
        print("❌ No saved session found.")
        return False

    try:
        cookies = json.loads(cookies_json)
        await context.add_cookies(cookies)
        return True
    except (json.JSONDecodeError, Exception) as e:
        print(f"❌ Failed to parse cookies: {e}")
        return False


async def validate_session() -> bool:
    """
    Check if the saved session is still valid by navigating to Naukri profile.
    Returns True if session is active, False if expired.
    """
    print("🔄 Validating session...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=os.getenv("CI_HEADLESS", "false").lower() == "true",
            args=['--disable-blink-features=AutomationControlled']
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        loaded = await load_session(context)
        if not loaded:
            await browser.close()
            return False

        page = await context.new_page()
        try:
            await page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
            current_url = page.url

            # If redirected to login page, session is expired
            if "login" in current_url.lower() or "nlogin" in current_url.lower():
                print("❌ Session expired — redirected to login page.")
                update_session_status("expired")
                await browser.close()
                return False

            print("✅ Session is valid!")
            update_session_status("active")
            await browser.close()
            return True

        except Exception as e:
            print(f"❌ Session validation failed: {e}")
            update_session_status("error")
            await browser.close()
            return False


async def ensure_authenticated() -> bool:
    """
    Main entry point for auth. Called at the start of every automation cycle.
    Returns True if we have a valid session, False if manual login is needed.
    """
    is_valid = await validate_session()

    if is_valid:
        return True

    # Session is invalid — notify user
    print("🔴 Session expired or not found. Sending notification...")
    notify_session_expired()
    return False


async def get_authenticated_context(playwright):
    """
    Create and return a Playwright browser context with loaded cookies.
    Used by other modules (freshness_manager, resume_uploader, etc.)
    """
    browser = await playwright.chromium.launch(
        headless=os.getenv("CI_HEADLESS", "false").lower() == "true",
        args=['--disable-blink-features=AutomationControlled']
    )

    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    loaded = await load_session(context)
    if not loaded:
        await browser.close()
        raise RuntimeError("No valid session cookies found. Run manual login first.")

    return browser, context


# ── CLI Entry Point ────────────────────────────────────

def main():
    """CLI interface for auth operations."""
    if "--login" in sys.argv:
        asyncio.run(manual_login())
    elif "--validate" in sys.argv:
        result = asyncio.run(validate_session())
        sys.exit(0 if result else 1)
    else:
        print("Usage:")
        print("  python -m core.auth --login      # Open browser for manual login")
        print("  python -m core.auth --validate   # Check if session is still valid")


if __name__ == "__main__":
    main()
