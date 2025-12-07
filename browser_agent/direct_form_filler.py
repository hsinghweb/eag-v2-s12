"""
Direct Form Filler - Fast form filling without LLM for every step.

Uses data from .env and directly interacts with the browser.
Much faster than LLM-based approach.

Usage:
    python -m browser_agent.direct_form_filler
"""

import asyncio
import sys
import os
import re
from pathlib import Path

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from browserMCP.mcp_tools import handle_tool_call
from browserMCP.mcp_utils.utils import ensure_browser_session, stop_browser_session


# Form URL
FORM_URL = "https://forms.gle/6Nc6QaaJyDvePxLv7"


def get_form_data():
    """Load form data from .env"""
    return {
        "email": os.getenv("FORM_EMAIL", "test@example.com"),
        "dob": os.getenv("FORM_DOB", "15-08-1995"),
        "course": os.getenv("FORM_COURSE", "EAG Session 12"),
        "master_name": os.getenv("FORM_MASTER_NAME", "Agentic AI Master"),
        "married": os.getenv("FORM_MARRIED", "No"),
        "course_taking": os.getenv("FORM_COURSE_TAKING", "EAG"),
    }


def get_google_creds():
    """Load Google credentials from .env"""
    return {
        "email": os.getenv("GOOGLE_EMAIL"),
        "password": os.getenv("GOOGLE_PASSWORD"),
    }


async def get_page_elements():
    """Get interactive elements from the page"""
    result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": True
    })
    if result and len(result) > 0:
        return result[0].get("text", "")
    return ""


async def find_element_index(elements_text: str, search_terms: list) -> int:
    """Find element index by searching for terms in the elements text"""
    lines = elements_text.split('\n')
    for line in lines:
        for term in search_terms:
            if term.lower() in line.lower():
                # Extract index from line like "[ID: 5]" or "index: 5"
                match = re.search(r'(?:id|index)[:\s]*(\d+)', line, re.IGNORECASE)
                if match:
                    return int(match.group(1))
    return -1


async def fill_form():
    """Fill the Google Form directly"""
    
    print("=" * 60)
    print("[DIRECT FORM FILLER] Fast Google Form Filling")
    print("=" * 60)
    
    form_data = get_form_data()
    google_creds = get_google_creds()
    
    print("\n[CONFIG] Form Data:")
    for k, v in form_data.items():
        print(f"  {k}: {v}")
    print()
    
    try:
        # Step 1: Navigate to form
        print("[1/8] Navigating to form...")
        await handle_tool_call("open_tab", {"url": FORM_URL})
        await asyncio.sleep(3)
        
        # Step 2: Get page elements
        print("[2/8] Analyzing page...")
        elements = await get_page_elements()
        
        # Step 3: Fill email field
        print(f"[3/8] Filling email: {form_data['email']}")
        # Try to find and fill each text input
        await handle_tool_call("input_text", {"index": 2, "text": form_data['email']})
        await asyncio.sleep(1)
        
        # Step 4: Fill DOB
        print(f"[4/8] Filling DOB: {form_data['dob']}")
        await handle_tool_call("input_text", {"index": 3, "text": form_data['dob']})
        await asyncio.sleep(1)
        
        # Step 5: Fill course
        print(f"[5/8] Filling course: {form_data['course']}")
        await handle_tool_call("input_text", {"index": 4, "text": form_data['course']})
        await asyncio.sleep(1)
        
        # Step 6: Fill master name
        print(f"[6/8] Filling master name: {form_data['master_name']}")
        await handle_tool_call("input_text", {"index": 5, "text": form_data['master_name']})
        await asyncio.sleep(1)
        
        # Step 7: Select married radio button
        print(f"[7/8] Selecting married: {form_data['married']}")
        # Radio buttons are typically after text inputs
        # Try clicking based on the married value
        if form_data['married'].lower() == 'yes':
            await handle_tool_call("click_element_by_index", {"index": 6})
        elif form_data['married'].lower() == 'no':
            await handle_tool_call("click_element_by_index", {"index": 7})
        else:  # Maybe
            await handle_tool_call("click_element_by_index", {"index": 8})
        await asyncio.sleep(1)
        
        # Step 8: Select dropdown
        print(f"[8/8] Selecting course: {form_data['course_taking']}")
        await handle_tool_call("select_dropdown_option", {
            "index": 9,
            "option_text": form_data['course_taking']
        })
        await asyncio.sleep(1)
        
        # Step 9: Submit
        print("[SUBMIT] Clicking submit button...")
        await handle_tool_call("click_element_by_index", {"index": 10})
        await asyncio.sleep(3)
        
        # Check if login is needed
        print("[CHECK] Checking for login prompt...")
        elements = await get_page_elements()
        
        if "sign in" in elements.lower() or "email" in elements.lower():
            print("[LOGIN] Google login required...")
            
            if google_creds['email'] and google_creds['password']:
                # Enter email
                print(f"  Entering email: {google_creds['email']}")
                await handle_tool_call("input_text", {"index": 0, "text": google_creds['email']})
                await asyncio.sleep(1)
                await handle_tool_call("click_element_by_index", {"index": 1})  # Next button
                await asyncio.sleep(2)
                
                # Enter password
                print("  Entering password...")
                await handle_tool_call("input_text", {"index": 0, "text": google_creds['password']})
                await asyncio.sleep(1)
                await handle_tool_call("click_element_by_index", {"index": 1})  # Sign in button
                await asyncio.sleep(3)
        
        # Check for success
        print("[VERIFY] Checking submission status...")
        elements = await get_page_elements()
        
        if "response" in elements.lower() or "recorded" in elements.lower() or "submitted" in elements.lower():
            print("\n" + "=" * 60)
            print("[SUCCESS] Form submitted successfully!")
            print("=" * 60)
            return True
        else:
            print("\n[INFO] Form filling completed. Check browser for status.")
            return True
            
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        print("\n[CLEANUP] Closing browser...")
        try:
            await stop_browser_session()
        except:
            pass


async def main():
    success = await fill_form()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

