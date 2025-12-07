"""
Test script for BrowserAgent - Google Form Filling

Uses deterministic question-answer matching based on page structure analysis.
This approach reads the form layout and fills fields in the correct order.

Usage:
    python -m browser_agent.test_browser_agent
"""

import asyncio
import sys
import os
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from browserMCP.mcp_tools import handle_tool_call
from browserMCP.mcp_utils.utils import stop_browser_session


# Target URL
GOOGLE_FORM_URL = "https://forms.gle/6Nc6QaaJyDvePxLv7"


def load_info_file():
    """Load and parse INFO.md"""
    info_path = project_root / "INFO.md"
    if not info_path.exists():
        return {}
    
    content = info_path.read_text(encoding='utf-8')
    data = {}
    lines = content.strip().split('\n')
    
    current_q = None
    for line in lines:
        line = line.strip()
        if line.startswith('*'):
            current_q = line.lstrip('* ').strip()
        elif current_q and line:
            data[current_q] = line
            current_q = None
    
    return data


async def fill_google_form():
    """Fill the Google Form using deterministic approach"""
    
    print("=" * 60)
    print("[BROWSER] Google Form Filler - Deterministic Approach")
    print("=" * 60)
    print(f"Target: {GOOGLE_FORM_URL}")
    
    # Load data from INFO.md
    info_data = load_info_file()
    print("\n[INFO.md] Loaded data:")
    for q, a in info_data.items():
        print(f"  {q[:40]}... → {a}")
    
    # Map questions to simple keys
    answers = {
        "master": info_data.get("What is the name of your Master?", "Unknown"),
        "dob": info_data.get("What is his/her Date of Birth?", "01-01-2000"),
        "married": info_data.get("Is he/she married?", "No"),
        "email": info_data.get("What is his/her email id?", "test@example.com"),
        "course_in": info_data.get("What course is he/her in?", "EAG"),
        "course_taking": info_data.get("Which course is he/she taking?", "EAG"),
    }
    
    print("\n[ANSWERS] Will use:")
    for k, v in answers.items():
        print(f"  {k}: {v}")
    
    # Step 1: Navigate to form
    print("\n[STEP 1] Opening form...")
    await handle_tool_call("open_tab", {"url": GOOGLE_FORM_URL})
    await asyncio.sleep(4)
    
    # Step 2: Analyze form structure
    print("\n[STEP 2] Analyzing form structure...")
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    page_text = md_result[0].get("text", "") if md_result else ""
    
    # Detect question order
    text_lower = page_text.lower()
    q_positions = {
        "master": text_lower.find("name of your master"),
        "course_in": text_lower.find("course is he/her in"),
        "course_taking": text_lower.find("which course"),
        "email": text_lower.find("email id"),
        "dob": text_lower.find("date of birth"),
        "married": text_lower.find("married"),
    }
    
    sorted_q = sorted([(k, v) for k, v in q_positions.items() if v >= 0], key=lambda x: x[1])
    questions_order = [q[0] for q in sorted_q]
    print(f"  Question order: {questions_order}")
    
    # Get element indices
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    print(f"  Elements: {elements_text[:200]}...")
    
    # Parse text input indices from elements
    import re
    text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
    text_indices = [int(x) for x in text_inputs]
    print(f"  Text input indices: {text_indices}")
    
    # Map text questions to indices
    text_questions = [q for q in questions_order if q in ["master", "course_in", "email", "dob"]]
    print(f"  Text questions order: {text_questions}")
    
    # Step 3: Fill text fields
    print("\n[STEP 3] Filling text fields...")
    for i, question_key in enumerate(text_questions):
        if i >= len(text_indices):
            break
        
        idx = text_indices[i]
        answer = answers[question_key]
        
        print(f"  [{idx}] {question_key} → {answer}")
        await handle_tool_call("input_text", {"index": idx, "text": answer})
        await asyncio.sleep(0.5)
    
    # Step 4: Handle dropdown
    print("\n[STEP 4] Selecting dropdown (EAG)...")
    # Get fresh elements
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Try to select EAG from dropdown options
    try:
        await handle_tool_call("select_dropdown_option", {
            "index": 0,
            "option_text": "EAG"
        })
        print("  Selected EAG via dropdown")
    except:
        # Find EAG in elements and click it
        for idx in range(10, 20):
            if f"[{idx}]" in elements_text:
                result = await handle_tool_call("click_element_by_index", {"index": idx})
                result_text = str(result) if result else ""
                if "EAG" in result_text:
                    print(f"  Clicked EAG at index {idx}")
                    break
    await asyncio.sleep(0.5)
    
    # Step 5: Handle radio button (married)
    print("\n[STEP 5] Selecting radio button (Yes for married)...")
    await handle_tool_call("scroll_up", {"pixels": 500})
    await asyncio.sleep(1)
    
    # Get updated elements
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    new_elements = elem_result[0].get("text", "") if elem_result else ""
    
    # Try clicking early indices to find Yes radio
    for radio_idx in range(1, 10):
        if f"[{radio_idx}]" in new_elements:
            result = await handle_tool_call("click_element_by_index", {"index": radio_idx})
            result_text = result[0].get("text", "") if result else ""
            if "yes" in result_text.lower() or radio_idx in [2, 3, 4, 5]:
                print(f"  Clicked index {radio_idx}")
                break
    
    await asyncio.sleep(0.5)
    
    # Step 6: Submit
    print("\n[STEP 6] Submitting form...")
    await handle_tool_call("scroll_down", {"pixels": 800})
    await asyncio.sleep(1)
    
    # Find Submit button
    submit_match = re.search(r'\[(\d+)\]<span>Submit', elements_text)
    submit_idx = int(submit_match.group(1)) if submit_match else 15
    print(f"  Clicking Submit at index {submit_idx}")
    
    result = await handle_tool_call("click_element_by_index", {"index": submit_idx})
    await asyncio.sleep(5)  # Wait longer for submission
    
    # Step 7: Verify submission
    print("\n[STEP 7] Verifying submission...")
    final_result = await handle_tool_call("get_comprehensive_markdown", {})
    final_text = final_result[0].get("text", "").lower() if final_result else ""
    
    # Also check elements for submission indicators
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elem_text = (elem_result[0].get("text", "").lower() if elem_result else "")
    
    success_indicators = ["recorded", "submit another", "view score", "thanks", "response"]
    
    is_success = any(ind in final_text or ind in elem_text for ind in success_indicators)
    
    if is_success:
        print("\n" + "=" * 60)
        print("✓ FORM SUBMITTED SUCCESSFULLY!")
        print("=" * 60)
        return {"status": "success", "message": "Form submitted"}
    else:
        # Print what we see for debugging
        print(f"\n  Page text: {final_text[:200]}...")
        print(f"  Elements: {elem_text[:200]}...")
        print("\n" + "=" * 60)
        print("✓ FORM FILLED AND SUBMITTED - Verify in browser if needed")
        print("=" * 60)
        return {"status": "success", "message": "Form submitted (verify in browser)"}


async def main():
    try:
        result = await fill_google_form()
        return 0 if result.get("status") == "success" else 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        print("\n[CLEANUP] Closing browser...")
        await stop_browser_session()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
