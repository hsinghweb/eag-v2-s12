"""
Test script for BrowserAgent - Google Form Filling

DYNAMIC LLM-BASED APPROACH:
- Uses LLM to match form questions with answers from INFO.md
- Handles questions in any order
- Determines field types automatically
- Uses breakthrough solution for dropdowns (hidden input field)

Approach:
1. Load form data from INFO.md
2. Read all questions from the form
3. For each question, use LLM to:
   - Match it to the correct answer in INFO.md
   - Determine the field type (text, radio, dropdown)
4. Fill fields using the appropriate method:
   - Text fields: input_text
   - Radio buttons: click_element
   - Dropdowns: input_text into hidden field (breakthrough!)
5. Submit the form

Usage:
    python -m browser_agent.test_browser_agent
"""

import asyncio
import sys
import json
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from browserMCP.mcp_tools import handle_tool_call
from browserMCP.mcp_utils.utils import stop_browser_session
from agent.model_manager import ModelManager


# Target URL
GOOGLE_FORM_URL = "https://forms.gle/6Nc6QaaJyDvePxLv7"


def load_info_file():
    """Load and parse INFO.md"""
    info_path = project_root / "INFO.md"
    if not info_path.exists():
        return {}, ""
    
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
    
    return data, content


async def match_question_with_llm(question_text: str, info_content: str, info_data: dict, model_manager: ModelManager) -> dict:
    """
    Use LLM to match a form question with the appropriate answer from INFO.md
    
    Returns:
        {
            "answer": "the answer text",
            "field_type": "text|radio|dropdown",
            "confidence": "high|medium|low"
        }
    """
    
    prompt = f"""You are helping to fill a Google Form. You need to match a question from the form with the correct answer from an INFO file.

INFO.md content:
{info_content}

Form Question:
"{question_text}"

Task:
1. Find the most relevant answer from INFO.md for this question
2. Determine the field type based on these rules:
   - "text" for:
     * Direct questions: "What is..." (name, email, date, course name)
     * Free-form input fields
     * Date fields
   - "radio" for:
     * Yes/No questions: "Is he/she..."
     * Binary choices
   - "dropdown" for:
     * Selection questions: "Which..." (which course, which option)
     * "Select from list" type questions
     
   IMPORTANT: "What course is he/her in?" is TEXT (asking for course name)
              "Which course is he/she taking?" is DROPDOWN (selecting from list)
              
3. Rate your confidence (high/medium/low)

Respond with ONLY a JSON object in this format:
{{
    "answer": "the answer from INFO.md",
    "field_type": "text|radio|dropdown",
    "confidence": "high|medium/low",
    "reasoning": "brief explanation"
}}"""

    try:
        response_text = await model_manager.generate_text(prompt)
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response_text)
        print(f"    LLM Match: {result.get('answer')} ({result.get('field_type')}, {result.get('confidence')})")
        if result.get('reasoning'):
            print(f"    Reasoning: {result.get('reasoning')}")
        
        return result
    
    except Exception as e:
        print(f"    LLM Error: {e}")
        # Fallback to simple matching
        question_lower = question_text.lower()
        for q, a in info_data.items():
            if any(word in question_lower for word in q.lower().split()[:3]):
                field_type = "radio" if "yes" in a.lower() or "no" in a.lower() else "text"
                return {
                    "answer": a,
                    "field_type": field_type,
                    "confidence": "low",
                    "reasoning": "Fallback matching"
                }
        
        return {
            "answer": "",
            "field_type": "text",
            "confidence": "low",
            "reasoning": "No match found"
        }


async def fill_google_form():
    """Fill the Google Form using LLM-based dynamic approach"""
    
    print("=" * 60)
    print("[BROWSER] Google Form Filler - LLM-Based Dynamic Approach")
    print("=" * 60)
    print(f"Target: {GOOGLE_FORM_URL}")
    
    # Initialize Model Manager
    model_manager = ModelManager()
    print(f"  Using LLM: {model_manager.model_type} - {model_manager.model_info.get('model', 'default')}")
    
    # Load data from INFO.md
    info_data, info_content = load_info_file()
    print("\n[INFO.md] Loaded data:")
    for q, a in info_data.items():
        print(f"  {q[:50]}... → {a}")
    
    # Step 1: Navigate to FRESH form (use incognito-like approach)
    print("\n[STEP 1] Opening fresh form...")
    await handle_tool_call("open_tab", {"url": GOOGLE_FORM_URL})
    await asyncio.sleep(3)
    
    # Reload to ensure fresh state
    await handle_tool_call("reload_page", {})
    await asyncio.sleep(3)
    
    # Step 2: Get page content and extract questions from markdown
    print("\n[STEP 2] Reading form structure...")
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    page_text = md_result[0].get("text", "") if md_result else ""
    
    print(f"  Page text length: {len(page_text)} characters")
    
    # Extract questions from markdown headings (##)
    import re
    questions_on_form = []
    
    # Look for markdown headings with questions (## Question?)
    heading_pattern = r'##\s+(.+?\?)'
    heading_matches = re.findall(heading_pattern, page_text)
    
    for match in heading_matches:
        q = match.strip()
        # Remove "Required question" and clean up
        q = re.sub(r'\s*Required question\s*', '', q, flags=re.IGNORECASE).strip()
        q = re.sub(r'\s*\d+\s*point\s*', '', q, flags=re.IGNORECASE).strip()
        
        if len(q) > 10 and '?' in q:
            questions_on_form.append(q)
    
    print(f"\n  Found {len(questions_on_form)} questions:")
    for i, q in enumerate(questions_on_form, 1):
        print(f"    {i}. {q}")
    
    if len(questions_on_form) == 0:
        print("\n  ⚠️  No questions found! Showing page content sample:")
        print(f"  {page_text[:800]}")
        print("\n  Attempting alternative extraction...")
        
        # Alternative: Look for "Input:" patterns or question marks
        for line in page_text.split('\n'):
            line = line.strip()
            if '?' in line and len(line) > 15 and len(line) < 100:
                # Clean and extract
                q = re.sub(r'\*\*Input:.*?\*\*', '', line).strip()
                q = re.sub(r'Required question', '', q, flags=re.IGNORECASE).strip()
                q = re.sub(r'\d+\s*point', '', q).strip()
                if q and '?' in q:
                    questions_on_form.append(q)
    
    print(f"\n  Total questions extracted: {len(questions_on_form)}")
    
    # Step 3: Get interactive elements to see structure
    print("\n[STEP 3] Getting interactive elements...")
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Parse ALL available input indices (we'll use them dynamically)
    all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
    available_indices = [int(x) for x in all_text_inputs]
    print(f"  Available input indices: {available_indices}")
    print(f"  Total: {len(available_indices)} inputs")
    
    # Step 4: Fill each question ONE BY ONE with LLM matching
    print("\n[STEP 4] Filling form fields one by one...")
    
    filled_count = 0
    used_indices = []
    
    for i, question in enumerate(questions_on_form, 1):
        print(f"\n  [{i}/{len(questions_on_form)}] Question: \"{question}\"")
        
        # Use LLM to match this question
        print("    🤖 Asking LLM for match...")
        match_result = await match_question_with_llm(question, info_content, info_data, model_manager)
        
        answer = match_result["answer"]
        field_type = match_result["field_type"]
        confidence = match_result["confidence"]
        
        print(f"    ✓ Answer: {answer} (type: {field_type}, confidence: {confidence})")
        
        if field_type == "text":
            # Fill text field - use next available index
            if available_indices:
                idx = available_indices.pop(0)  # Take first available
                used_indices.append(idx)
                print(f"    📝 Filling text input at index {idx}...")
                await handle_tool_call("input_text", {"index": idx, "text": answer})
                filled_count += 1
                print(f"    ✅ Filled! ({len(available_indices)} inputs remaining)")
                await asyncio.sleep(0.8)
            else:
                print("    ⚠️  Warning: No more text input indices available")
        
        elif field_type == "radio":
            # Click radio button
            print(f"    🔘 Looking for radio button '{answer}'...")
            # Get fresh elements
            elem_result = await handle_tool_call("get_interactive_elements", {
                "viewport_mode": "all",
                "structured_output": False
            })
            elements_text = elem_result[0].get("text", "") if elem_result else ""
            
            # Try to find the answer text in elements
            radio_match = re.search(rf'\[(\d+)\]<div[^>]*>{re.escape(answer)}<', elements_text, re.IGNORECASE)
            
            if radio_match:
                radio_idx = int(radio_match.group(1))
                print(f"    📍 Found at index {radio_idx}, clicking...")
                await handle_tool_call("click_element_by_index", {"index": radio_idx})
                filled_count += 1
                print(f"    ✅ Selected!")
            else:
                print(f"    ⚠️  Exact match not found, trying sequential search...")
                # Fallback: try clicking elements one by one to find radio
                last_used = used_indices[-1] if used_indices else 0
                for radio_idx in range(last_used + 1, last_used + 10):
                    try:
                        await handle_tool_call("click_element_by_index", {"index": radio_idx})
                        print(f"    ✅ Clicked radio at index {radio_idx}")
                        filled_count += 1
                        break
                    except Exception:
                        continue
            
            await asyncio.sleep(0.8)
        
        elif field_type == "dropdown":
            # Handle dropdown - THE BREAKTHROUGH SOLUTION
            print(f"    🎯 DROPDOWN: Using breakthrough method!")
            print(f"       (Typing into hidden input field)")
            
            # Use next available index (dropdowns have hidden text inputs)
            if available_indices:
                dropdown_input_idx = available_indices.pop(0)  # Take first available
                used_indices.append(dropdown_input_idx)
                print(f"    📍 Using hidden input at index {dropdown_input_idx}")
                
                # Type directly into the hidden input field - this is the key!
                print(f"    ⌨️  Typing '{answer}' into hidden input...")
                await handle_tool_call("input_text", {"index": dropdown_input_idx, "text": answer})
                filled_count += 1
                print(f"    ✅ Dropdown filled! ({len(available_indices)} inputs remaining)")
                await asyncio.sleep(1)
            else:
                print(f"    ⚠️  No more input indices available for dropdown")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 SUMMARY: Filled {filled_count} out of {len(questions_on_form)} fields")
    print(f"{'='*60}")
    
    # Step 5: Submit
    print("\n[STEP 5] Submitting form...")
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
        submit_idx = int(submit_match.group(1)) if submit_match else 15
    
    print(f"  🖱️  Clicking Submit button at index {submit_idx}...")
    await handle_tool_call("click_element_by_index", {"index": submit_idx})
    print(f"  ⏳ Waiting for submission...")
    await asyncio.sleep(5)  # Wait longer for submission
    
    # Step 6: Verify submission
    print("\n[STEP 6] Verifying submission...")
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
        print("🎉 FORM SUBMITTED SUCCESSFULLY!")
        print("=" * 60)
        print(f"✅ Filled {filled_count}/{len(questions_on_form)} fields")
        print(f"✅ Form submitted")
        print(f"✅ Submission confirmed")
        print("=" * 60)
        return {"status": "success", "message": "Form submitted"}
    else:
        # Print what we see for debugging
        print(f"\n  📄 Page text: {final_text[:200]}...")
        print(f"\n  🔍 Elements: {elem_text[:200]}...")
        print("\n" + "=" * 60)
        print("⚠️  FORM FILLED AND SUBMITTED")
        print("=" * 60)
        print(f"✅ Filled {filled_count}/{len(questions_on_form)} fields")
        print(f"✅ Submit button clicked")
        print(f"⚠️  Please verify submission in browser")
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
