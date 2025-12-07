"""
Direct Form Filler - Based on diagnosed indices
Fills the Google Form with exact field indices
"""

import asyncio
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from browserMCP.mcp_tools import handle_tool_call
from browserMCP.mcp_utils.utils import stop_browser_session

# Form data from INFO.md
MASTER_NAME = "Himanshu Singh"
DOB = "17-Dec-1984"
EMAIL = "himanshu.kumar.singh@gmail.com"
COURSE = "EAG"
MARRIED = "Yes"


async def fill_form():
    print("=" * 60)
    print("DIRECT FORM FILLER")
    print("=" * 60)
    
    # Navigate to form
    print("\n[1] Opening form...")
    await handle_tool_call("open_tab", {"url": "https://forms.gle/6Nc6QaaJyDvePxLv7"})
    await asyncio.sleep(4)
    
    # Get current elements to see the order
    print("\n[2] Getting form elements...")
    result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    
    if result:
        elements_text = result[0].get("text", "")
        print(f"Elements found:\n{elements_text}")
    
    # Also get markdown to see question order
    print("\n[3] Getting page content...")
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    page_text = ""
    if md_result:
        page_text = md_result[0].get("text", "")
        print(f"Page content preview:\n{page_text[:1500]}")
    
    # Parse the question order from markdown
    questions_order = []
    if "married" in page_text.lower():
        # Find order of questions
        text_lower = page_text.lower()
        q_positions = {
            "master": text_lower.find("name of your master"),
            "course_in": text_lower.find("course is he/her in"),
            "course_taking": text_lower.find("which course"),
            "email": text_lower.find("email id"),
            "dob": text_lower.find("date of birth"),
            "married": text_lower.find("married"),
        }
        
        # Sort by position
        sorted_q = sorted([(k, v) for k, v in q_positions.items() if v >= 0], key=lambda x: x[1])
        questions_order = [q[0] for q in sorted_q]
        print(f"\nQuestion order detected: {questions_order}")
    
    # Map question type to answer
    answers = {
        "master": MASTER_NAME,
        "course_in": COURSE,
        "course_taking": COURSE,
        "email": EMAIL,
        "dob": DOB,
        "married": MARRIED,
    }
    
    # Fill the text inputs in order (indices 8, 9, 12, 13 based on diagnosis)
    # But first, we need to map questions to indices based on their order
    text_indices = [8, 9, 12, 13]  # The 4 text inputs
    
    # Filter to only text-type questions
    text_questions = [q for q in questions_order if q in ["master", "course_in", "email", "dob"]]
    
    print(f"\nText questions in order: {text_questions}")
    print(f"Text input indices: {text_indices}")
    
    # Fill each text field
    for i, question in enumerate(text_questions):
        if i >= len(text_indices):
            break
        
        idx = text_indices[i]
        answer = answers[question]
        
        print(f"\n[FILL] Index {idx}: {question} → {answer}")
        
        try:
            result = await handle_tool_call("input_text", {
                "index": idx,
                "text": answer
            })
            print(f"  Result: {result[0].get('text', '') if result else 'OK'}")
        except Exception as e:
            print(f"  Error: {e}")
        
        await asyncio.sleep(1)
    
    # Handle dropdown (index 10 or 11 for EAG)
    print(f"\n[DROPDOWN] Selecting EAG...")
    try:
        # Click EAG option directly (index 11)
        await handle_tool_call("click_element_by_index", {"index": 11})
        print("  Clicked EAG option")
    except Exception as e:
        print(f"  Error: {e}")
        # Try selecting from dropdown
        try:
            await handle_tool_call("select_dropdown_option", {
                "index": 10,
                "option_text": "EAG"
            })
        except:
            pass
    
    await asyncio.sleep(1)
    
    # Handle married radio button - need to find it first
    print(f"\n[RADIO] Looking for 'Yes' radio button for married question...")
    # Scroll up to see radio buttons
    await handle_tool_call("scroll_up", {"pixels": 500})
    await asyncio.sleep(1)
    
    # Get elements again to find radio
    result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    if result:
        elements = result[0].get("text", "")
        print(f"Elements after scroll:\n{elements}")
        
        # Look for Yes radio
        # Usually radio buttons have lower indices
        for radio_idx in range(1, 8):
            try:
                r = await handle_tool_call("click_element_by_index", {"index": radio_idx})
                r_text = r[0].get("text", "") if r else ""
                print(f"  Clicked index {radio_idx}: {r_text[:50]}")
                if "yes" in r_text.lower():
                    print("  Found Yes!")
                    break
            except:
                continue
    
    # Scroll down and submit
    print(f"\n[SUBMIT] Looking for Submit button...")
    await handle_tool_call("scroll_down", {"pixels": 800})
    await asyncio.sleep(1)
    
    try:
        result = await handle_tool_call("click_element_by_index", {"index": 15})
        print(f"  Clicked Submit: {result[0].get('text', '') if result else 'OK'}")
    except Exception as e:
        print(f"  Error: {e}")
    
    await asyncio.sleep(3)
    
    # Check if submitted
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    if md_result:
        final_text = md_result[0].get("text", "")
        if "recorded" in final_text.lower() or "submitted" in final_text.lower():
            print("\n✓ FORM SUBMITTED SUCCESSFULLY!")
        else:
            print("\n? Check browser - form may need manual verification")
            print(f"Page says: {final_text[:500]}")


async def main():
    try:
        await fill_form()
    finally:
        print("\n[CLEANUP]")
        await stop_browser_session()


if __name__ == "__main__":
    asyncio.run(main())

