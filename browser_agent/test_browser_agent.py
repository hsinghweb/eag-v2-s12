"""
Test script for BrowserAgent - Google Form Filling

Usage:
    python -m browser_agent.test_browser_agent
    
Reads form data from INFO.md file in project root.
Google credentials should be in .env:
    GOOGLE_EMAIL=your_email@gmail.com
    GOOGLE_PASSWORD=your_password
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


def load_info_file():
    """Load and parse the INFO.md file"""
    info_path = project_root / "INFO.md"
    if not info_path.exists():
        print(f"[WARN] INFO.md not found at {info_path}")
        return None
    
    content = info_path.read_text(encoding='utf-8')
    print(f"[INFO] Loaded INFO.md:\n{content}")
    return content


def parse_info_content(content):
    """Parse INFO.md content into question-answer pairs"""
    data = {}
    lines = content.strip().split('\n')
    
    current_question = None
    for line in lines:
        line = line.strip()
        if line.startswith('*'):
            # This is a question
            current_question = line.lstrip('* ').strip()
        elif current_question and line:
            # This is an answer
            data[current_question] = line
            current_question = None
    
    return data


def get_form_data():
    """Load form data from INFO.md file"""
    content = load_info_file()
    if not content:
        # Fallback to env vars
        return {
            "master_name": os.getenv("FORM_MASTER_NAME", "Unknown"),
            "dob": os.getenv("FORM_DOB", "01-01-2000"),
            "married": os.getenv("FORM_MARRIED", "No"),
            "email": os.getenv("FORM_EMAIL", "test@example.com"),
            "course": os.getenv("FORM_COURSE", "EAG"),
            "course_taking": os.getenv("FORM_COURSE_TAKING", "EAG"),
        }
    
    parsed = parse_info_content(content)
    print(f"[INFO] Parsed data: {parsed}")
    
    # Map parsed questions to our keys
    return {
        "master_name": parsed.get("What is the name of your Master?", "Unknown"),
        "dob": parsed.get("What is his/her Date of Birth?", "01-01-2000"),
        "married": parsed.get("Is he/she married?", "No"),
        "email": parsed.get("What is his/her email id?", "test@example.com"),
        "course": parsed.get("What course is he/her in?", "EAG"),
        "course_taking": parsed.get("Which course is he/she taking?", "EAG"),
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
    
    # Create instruction with clear Q&A mapping from INFO.md
    instruction = f"""
=== KNOWLEDGE BASE (from INFO.md) - USE THESE EXACT ANSWERS ===

Q: What is the name of your Master?
A: {form_data['master_name']}

Q: What is his/her Date of Birth?
A: {form_data['dob']}

Q: Is he/she married?
A: {form_data['married']}

Q: What is his/her email id?
A: {form_data['email']}

Q: What course is he/her in?
A: {form_data['course']}

Q: Which course is he/she taking?
A: {form_data['course_taking']}

=== END KNOWLEDGE BASE ===

TASK: Fill the Google Form at {GOOGLE_FORM_URL}
Questions appear in RANDOM order - match each form question to the knowledge base above.

FIELD TYPES:
- "name of your Master" → TEXT input: {form_data['master_name']}
- "Date of Birth" → TEXT input: {form_data['dob']}
- "email" → TEXT input: {form_data['email']}
- "course is he/her in" → TEXT input: {form_data['course']}
- "married" → RADIO button: click "{form_data['married']}"
- "course is he/she taking" → DROPDOWN: select "{form_data['course_taking']}"

After filling ALL fields, click Submit button.
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

