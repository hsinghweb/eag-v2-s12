"""
One-time Google Login Setup Script

Run this once to manually log into Google in the persistent browser profile.
After logging in, all future BrowserAgent runs will be authenticated.

Usage:
    python -m browser_agent.setup_google_login
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from browserMCP.mcp_utils.utils import ensure_browser_session, stop_browser_session


async def setup_google_login():
    """Open browser for manual Google login"""
    
    print("=" * 60)
    print("GOOGLE LOGIN SETUP")
    print("=" * 60)
    print()
    print("This script will open a browser for you to log into Google.")
    print("After logging in, the session will be saved and used for")
    print("future BrowserAgent runs.")
    print()
    print("The browser profile is saved at:")
    print("  C:\\Users\\Himanshu\\.config\\browseruse\\profiles\\default")
    print()
    
    try:
        # Start browser session
        print("[INFO] Starting browser...")
        await ensure_browser_session()
        
        from browserMCP.mcp_tools import handle_tool_call
        
        # Navigate to Google login
        print("[INFO] Navigating to Google login page...")
        await handle_tool_call("open_tab", {"url": "https://accounts.google.com"})
        
        print()
        print("=" * 60)
        print("PLEASE LOG INTO YOUR GOOGLE ACCOUNT IN THE BROWSER WINDOW")
        print("=" * 60)
        print()
        print("After logging in successfully, press ENTER here to continue...")
        print("(Or type 'q' to quit without saving)")
        print()
        
        user_input = input("> ").strip().lower()
        
        if user_input == 'q':
            print("[INFO] Cancelled. Login not saved.")
        else:
            # Navigate to confirm login worked
            await handle_tool_call("open_tab", {"url": "https://myaccount.google.com"})
            await asyncio.sleep(2)
            
            print()
            print("[SUCCESS] Google login has been saved to the browser profile!")
            print("You can now run the BrowserAgent and it will use this login.")
            print()
        
    except Exception as e:
        print(f"[ERROR] Error during setup: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("[INFO] Closing browser...")
        await stop_browser_session()
        print("[DONE] Setup complete.")


if __name__ == "__main__":
    asyncio.run(setup_google_login())

