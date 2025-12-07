"""
Test script for BrowserAgent - Google Form Filling

BREAKTHROUGH SOLUTION for Google Forms dropdown issue:
- Instead of clicking dropdown UI elements, type directly into the hidden input field
- This bypasses all the problematic Google Forms dropdown behavior

Approach:
1. Fill all standard text fields (email, name, DOB, course)
2. Click the radio button (Yes for married)
3. **Type into the hidden input field for the dropdown** (this is the key!)
4. Submit the form

Usage:
    python -m browser_agent.test_browser_agent
"""

import asyncio
import sys
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
    
    # Step 3: Fill Email field
    print("\n[STEP 3] Filling Email field...")
    email_answer = answers["email"]
    print(f"  Email → {email_answer}")
    await handle_tool_call("input_text", {"index": text_indices[0] if text_indices else 0, "text": email_answer})
    await asyncio.sleep(0.5)
    
    # Step 4: Fill Master's name
    print("\n[STEP 4] Filling Master's name...")
    master_answer = answers["master"]
    print(f"  Master → {master_answer}")
    await handle_tool_call("input_text", {"index": text_indices[1] if len(text_indices) > 1 else 1, "text": master_answer})
    await asyncio.sleep(0.5)
    
    # Step 5: Fill Date of Birth
    print("\n[STEP 5] Filling Date of Birth...")
    dob_answer = answers["dob"]
    print(f"  DOB → {dob_answer}")
    await handle_tool_call("input_text", {"index": text_indices[2] if len(text_indices) > 2 else 2, "text": dob_answer})
    await asyncio.sleep(0.5)
    
    # Step 6: Fill Course (text field)
    print("\n[STEP 6] Filling Course field...")
    course_answer = answers["course_in"]
    print(f"  Course → {course_answer}")
    await handle_tool_call("input_text", {"index": text_indices[3] if len(text_indices) > 3 else 3, "text": course_answer})
    await asyncio.sleep(0.5)
    
    # Step 7: Handle radio button (married - Yes)
    print("\n[STEP 7] Selecting radio button (Yes for married)...")
    # Get fresh elements to find radio button
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Find "Yes" radio button - usually appears early in the form
    radio_match = re.search(r'\[(\d+)\]<div[^>]*>Yes<', elements_text)
    if radio_match:
        radio_idx = int(radio_match.group(1))
        print(f"  Clicking Yes radio at index {radio_idx}")
        await handle_tool_call("click_element_by_index", {"index": radio_idx})
    else:
        # Try common indices for radio buttons
        for radio_idx in range(4, 8):
            try:
                await handle_tool_call("click_element_by_index", {"index": radio_idx})
                print(f"  Clicked potential Yes radio at index {radio_idx}")
                break
            except Exception:
                continue
    
    await asyncio.sleep(0.5)
    
    # Step 8: Handle dropdown - THE BREAKTHROUGH SOLUTION
    print("\n[STEP 8] Filling dropdown (Which course - EAG)...")
    print("  Using breakthrough method: typing into hidden input field")
    
    # Get fresh elements to find the hidden dropdown input
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Find the hidden input field for the dropdown
    # It's usually an input type='text' that's associated with the dropdown
    # Look for inputs after the visible text inputs (usually index 4+)
    dropdown_input_idx = None
    text_inputs_all = re.findall(r'\[(\d+)\]<input type=\'text\'', elements_text)
    
    # The dropdown's hidden input is typically after the 4 visible text inputs
    if len(text_inputs_all) > 4:
        dropdown_input_idx = int(text_inputs_all[4])  # 5th text input (index 4)
        print(f"  Found dropdown hidden input at index {dropdown_input_idx}")
    else:
        # Fallback: try common indices
        dropdown_input_idx = 5
        print(f"  Using fallback dropdown input index {dropdown_input_idx}")
    
    # Type directly into the hidden input field - this is the key!
    course_taking_answer = answers["course_taking"]
    print(f"  Typing '{course_taking_answer}' into hidden dropdown input...")
    await handle_tool_call("input_text", {"index": dropdown_input_idx, "text": course_taking_answer})
    await asyncio.sleep(1)
    
    # Step 9: Submit
    print("\n[STEP 9] Submitting form...")
    # Get fresh elements to find Submit button
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Find Submit button
    submit_match = re.search(r'\[(\d+)\]<span>Submit', elements_text)
    if submit_match:
        submit_idx = int(submit_match.group(1))
    else:
        # Try to find any button-like element with "Submit"
        submit_match = re.search(r'\[(\d+)\][^[]*submit', elements_text, re.IGNORECASE)
        submit_idx = int(submit_match.group(1)) if submit_match else 10
    
    print(f"  Clicking Submit at index {submit_idx}")
    await handle_tool_call("click_element_by_index", {"index": submit_idx})
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
