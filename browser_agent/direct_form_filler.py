"""
Direct Form Filler - No LLM required
Fills Google Form by analyzing page structure and matching questions deterministically
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
from browserMCP.mcp_utils.utils import get_browser_session, stop_browser_session

# Answers from INFO.md - hardcoded for reliability
FORM_DATA = {
    "master": "Himanshu Singh",
    "birth": "17-Dec-1984",
    "married": "Yes",
    "email": "himanshu.kumar.singh@gmail.com",
    "course": "EAG",
}


def match_question_to_answer(question_text: str) -> tuple:
    """Match question to answer. Returns (answer, type)"""
    q = question_text.lower()
    
    if "master" in q or "name of" in q:
        return (FORM_DATA["master"], "text")
    if "birth" in q or "dob" in q:
        return (FORM_DATA["birth"], "text")
    if "married" in q:
        return (FORM_DATA["married"], "radio")
    if "email" in q:
        return (FORM_DATA["email"], "text")
    if "course" in q:
        return (FORM_DATA["course"], "text" if "what course" in q else "dropdown")
    
    return (None, None)


async def get_form_structure():
    """Get form fields with their labels"""
    result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": True
    })
    
    if result and len(result) > 0:
        import json
        text = result[0].get("text", "{}")
        try:
            return json.loads(text)
        except:
            return {"elements": []}
    return {"elements": []}


async def fill_form():
    """Fill the Google Form directly"""
    print("=" * 60)
    print("DIRECT FORM FILLER")
    print("=" * 60)
    
    # Navigate to form
    print("\n[1] Opening form...")
    await handle_tool_call("open_tab", {"url": "https://forms.gle/6Nc6QaaJyDvePxLv7"})
    await asyncio.sleep(3)
    
    # Get page markdown to see questions
    print("\n[2] Reading form structure...")
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    if md_result:
        page_text = md_result[0].get("text", "")
        print(f"Page preview: {page_text[:500]}...")
    
    # Get interactive elements
    elements_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all"
    })
    
    if elements_result:
        elements_text = elements_result[0].get("text", "")
        print(f"\nInteractive elements:\n{elements_text[:2000]}")
    
    # Now fill each field based on what we see
    # The form typically has fields in order, but we need to match by label
    
    filled = set()
    
    # Strategy: Go through each input field index and check what's around it
    for field_idx in range(1, 15):  # Check first 15 elements
        if field_idx in filled:
            continue
            
        # Try to get context around this element
        try:
            # Get element info
            element_result = await handle_tool_call("get_interactive_elements", {
                "viewport_mode": "all",
                "structured_output": True
            })
            
            if not element_result:
                continue
                
            import json
            try:
                data = json.loads(element_result[0].get("text", "{}"))
                elements = data.get("interactive_elements", [])
            except:
                continue
            
            # Find element at this index
            element = None
            for e in elements:
                if e.get("id") == field_idx:
                    element = e
                    break
            
            if not element:
                continue
            
            # Check element type and label
            elem_type = element.get("type", "").lower()
            label = element.get("label", "") or element.get("text", "") or ""
            
            print(f"\n[FIELD {field_idx}] Type: {elem_type}, Label: {label[:50]}")
            
            if not label:
                continue
            
            # Match to answer
            answer, field_type = match_question_to_answer(label)
            
            if answer:
                print(f"  → Matched! Answer: {answer}, Type: {field_type}")
                
                if field_type == "text" and "input" in elem_type:
                    await handle_tool_call("input_text", {
                        "index": field_idx,
                        "text": answer
                    })
                    filled.add(field_idx)
                    print(f"  ✓ Filled!")
                    await asyncio.sleep(1)
                    
                elif field_type == "radio":
                    # For radio, we need to find the "Yes" option
                    await handle_tool_call("click_element_by_index", {
                        "index": field_idx
                    })
                    filled.add(field_idx)
                    print(f"  ✓ Clicked!")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            print(f"  Error: {e}")
            continue
    
    # Try to submit
    print("\n[3] Looking for Submit button...")
    await asyncio.sleep(2)
    
    # Usually submit is one of the last buttons
    for submit_idx in range(10, 20):
        try:
            result = await handle_tool_call("click_element_by_index", {"index": submit_idx})
            result_text = result[0].get("text", "") if result else ""
            if "submit" in result_text.lower():
                print(f"  → Clicked Submit at index {submit_idx}")
                break
        except:
            continue
    
    print("\n[DONE] Form filling attempted")
    print("Check the browser to verify results")


async def main():
    try:
        await fill_form()
    finally:
        print("\n[CLEANUP]")
        await stop_browser_session()


if __name__ == "__main__":
    asyncio.run(main())
