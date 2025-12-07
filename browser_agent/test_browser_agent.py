"""
Test script for BrowserAgent - Google Form Filling

Usage:
    python -m browser_agent.test_browser_agent
    
Or from project root:
    python browser_agent/test_browser_agent.py
    
Required .env variables:
    GOOGLE_EMAIL=your_email@gmail.com
    GOOGLE_PASSWORD=your_password
    FORM_EMAIL=submission_email@example.com
    FORM_DOB=15-08-1995
    FORM_COURSE=EAG Session 12
    FORM_MASTER_NAME=Agentic AI Master
    FORM_MARRIED=No
    FORM_COURSE_TAKING=EAG
"""

import asyncio
import sys
import os
from pathlib import Path

# Fix encoding for Windows terminal
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from browser_agent.browser_agent import BrowserAgent
from browserMCP.mcp_utils.utils import stop_browser_session


# Target Google Form URL
GOOGLE_FORM_URL = "https://forms.gle/6Nc6QaaJyDvePxLv7"


def get_form_data():
    """Load form data from environment variables"""
    return {
        "email": os.getenv("FORM_EMAIL", "test@example.com"),
        "dob": os.getenv("FORM_DOB", "15-08-1995"),
        "course": os.getenv("FORM_COURSE", "EAG Session 12"),
        "master_name": os.getenv("FORM_MASTER_NAME", "Agentic AI Master"),
        "married": os.getenv("FORM_MARRIED", "No"),
        "course_taking": os.getenv("FORM_COURSE_TAKING", "EAG"),
    }


def get_google_credentials():
    """Load Google login credentials from environment variables"""
    return {
        "email": os.getenv("GOOGLE_EMAIL"),
        "password": os.getenv("GOOGLE_PASSWORD"),
    }


async def test_form_filling():
    """Test the BrowserAgent by filling the Google Form"""
    
    print("=" * 60)
    print("[BROWSER] BrowserAgent Test - Google Form Filling")
    print("=" * 60)
    print(f"Target URL: {GOOGLE_FORM_URL}")
    print()
    
    # Load credentials and form data
    google_creds = get_google_credentials()
    form_data = get_form_data()
    
    print("[CONFIG] Form Data Loaded:")
    for key, value in form_data.items():
        print(f"  - {key}: {value}")
    print()
    
    if google_creds["email"] and google_creds["password"]:
        print(f"[CONFIG] Google Login: {google_creds['email']}")
    else:
        print("[CONFIG] Google Login: Not configured (will use existing session)")
    print()
    
    # Initialize the BrowserAgent
    prompt_path = project_root / "prompts" / "browser_agent_prompt.txt"
    
    agent = BrowserAgent(
        prompt_path=str(prompt_path),
        max_steps=25  # Allow up to 25 steps for login + form filling
    )
    
    # Create the instruction with EXACT question-to-value mapping
    instruction = f"""
TASK: Fill Google Form at {GOOGLE_FORM_URL}

EXACT FIELD MAPPINGS (match by question text keywords):
- Question contains "email" -> enter: {form_data['email']}
- Question contains "Date of Birth" or "DOB" -> enter: {form_data['dob']}
- Question contains "course is he/her in" or "what course" -> enter: {form_data['course']}
- Question contains "Master" or "name of your" -> enter: {form_data['master_name']}
- Question contains "married" -> click radio button: {form_data['married']}
- Question contains "taking" or "dropdown" with options ERA/EAG/EPAi -> select: {form_data['course_taking']}

PROCESS:
1. Fill ALL text fields by matching question keywords
2. Select radio button for married question ({form_data['married']})
3. Select dropdown option ({form_data['course_taking']})
4. Click Submit button
5. IF Google login page appears:
   - Enter email: {google_creds['email']}
   - Click Next
   - Enter password: {google_creds['password']}
   - Click Sign in
6. Mark DONE when you see "response recorded" or form is submitted

CRITICAL RULES:
- Match questions by KEYWORDS, not by position (form order is random)
- Use the EXACT values provided above
- After Submit, if login appears, complete the login
- Do NOT skip any field
"""
    
    try:
        # Run the BrowserAgent
        result = await agent.run(instruction)
        
        print("\n" + "=" * 60)
        print("[RESULT] EXECUTION RESULT")
        print("=" * 60)
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        print(f"Steps Executed: {result['steps_executed']}")
        print(f"Run ID: {result['run_id']}")
        
        # Print step details
        if result.get('details'):
            print("\n[STEPS] Step Details:")
            for step in result['details'].get('steps_executed', []):
                status_icon = "[OK]" if step.get('success') else "[FAIL]"
                print(f"  {status_icon} Step {step['step']}: {step['action']}")
                print(f"      Reasoning: {step.get('reasoning', 'N/A')[:80]}...")
                if step.get('result'):
                    print(f"      Result: {step['result'][:100]}...")
                print()
        
        return result
        
    except Exception as e:
        print(f"\n[ERROR] Error during execution: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
    
    finally:
        # Clean up browser session
        print("\n[CLEANUP] Cleaning up browser session...")
        try:
            await stop_browser_session()
            print("[OK] Browser session closed")
        except Exception as e:
            print(f"[WARN] Error closing browser: {e}")


async def main():
    """Main entry point"""
    result = await test_form_filling()
    
    print("\n" + "=" * 60)
    print("[DONE] TEST COMPLETE")
    print("=" * 60)
    
    if result.get('status') == 'success':
        print("[SUCCESS] Form filling completed successfully!")
        return 0
    else:
        print(f"[WARN] Form filling ended with status: {result.get('status')}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

