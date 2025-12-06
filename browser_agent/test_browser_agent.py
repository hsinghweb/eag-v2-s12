"""
Test script for BrowserAgent - Google Form Filling

Usage:
    python -m browser_agent.test_browser_agent
    
Or from project root:
    python browser_agent/test_browser_agent.py
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


async def test_form_filling():
    """Test the BrowserAgent by filling the Google Form"""
    
    print("=" * 60)
    print("[BROWSER] BrowserAgent Test - Google Form Filling")
    print("=" * 60)
    print(f"Target URL: {GOOGLE_FORM_URL}")
    print()
    
    # Initialize the BrowserAgent
    prompt_path = project_root / "prompts" / "browser_agent_prompt.txt"
    
    agent = BrowserAgent(
        prompt_path=str(prompt_path),
        max_steps=20  # Allow up to 20 steps for form filling
    )
    
    # Create the instruction
    instruction = f"""
    Navigate to the Google Form at {GOOGLE_FORM_URL} and fill out the form completely.
    
    Fill in all required fields with appropriate test data:
    - For name fields, use "Browser Agent Test"
    - For email fields, use "browseragent.test@gmail.com"
    - For any other text fields, provide reasonable test responses
    - For multiple choice questions, select an appropriate option
    - For checkbox questions, select at least one option
    
    After filling all fields, submit the form and verify the submission was successful.
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

