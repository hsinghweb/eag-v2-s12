"""
One-Time Google Login Setup

This script opens a browser with the persistent profile.
Login to Google ONCE manually, and all future BrowserAgent runs 
will be automatically logged in.

Usage:
    python -m browser_agent.setup_login
"""

import asyncio
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from browserMCP.mcp_utils.utils import get_browser_session, stop_browser_session


async def setup_google_login():
    print("=" * 60)
    print("GOOGLE LOGIN SETUP")
    print("=" * 60)
    print()
    print("This will open a browser with the persistent profile.")
    print("Please login to your Google account manually.")
    print("After login, the session will be saved for future runs.")
    print()
    print("Steps:")
    print("  1. Browser will open to Google accounts page")
    print("  2. Login with your Google account")
    print("  3. Once logged in, press ENTER here to close")
    print()
    
    try:
        # Get browser session (uses persistent profile)
        session = await get_browser_session()
        page = await session.get_current_page()
        
        # Navigate to Google accounts
        await page.goto("https://accounts.google.com")
        
        print("Browser opened! Please login to Google now...")
        print()
        print("You have 60 seconds to login...")
        print()
        
        # Wait 60 seconds for user to login
        for i in range(60, 0, -10):
            print(f"  {i} seconds remaining...")
            await asyncio.sleep(10)
        
        print()
        print("Checking login status...")
        
        # Check if logged in by visiting Google
        await page.goto("https://myaccount.google.com")
        await asyncio.sleep(2)
        
        current_url = page.url
        if "myaccount.google.com" in current_url and "signin" not in current_url:
            print("[SUCCESS] You are logged in!")
            print("Future BrowserAgent runs will use this session.")
        else:
            print("[WARNING] Login may not have completed.")
            print("Please try again or check if you're logged in.")
        
    except Exception as e:
        print(f"[ERROR] {e}")
    
    finally:
        print()
        print("Closing browser...")
        await stop_browser_session()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(setup_google_login())

