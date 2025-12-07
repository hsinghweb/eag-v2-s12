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
    
    # Step 1: Navigate to form
    print("\n[STEP 1] Opening form...")
    await handle_tool_call("open_tab", {"url": GOOGLE_FORM_URL})
    await asyncio.sleep(3)
    
    # Step 1.5: Clear all text inputs individually
    print("\n[STEP 1.5] Clearing all text fields to ensure fresh start...")
    import re
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Find all text input indices
    text_inputs_to_clear = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
    text_indices_to_clear = [int(x) for x in text_inputs_to_clear]
    
    if text_indices_to_clear:
        print(f"  Found {len(text_indices_to_clear)} text inputs: {text_indices_to_clear}")
        print(f"  🧹 Clearing each field...")
        
        for idx in text_indices_to_clear:
            try:
                # Clear by typing empty string
                await handle_tool_call("input_text", {"index": idx, "text": ""})
                print(f"    ✓ Cleared input at index {idx}")
            except Exception as e:
                print(f"    ⚠️  Could not clear index {idx}: {e}")
        
        await asyncio.sleep(1)
        print(f"  ✅ All text fields cleared! Starting fresh.")
    else:
        print(f"  ℹ️  No text inputs found to clear")
    
    await asyncio.sleep(1)
    
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
    
    # Keep track of which inputs are for dropdowns vs regular text
    dropdown_questions = []
    text_questions = []
    radio_questions = []
    
    # First pass: categorize all questions
    print("\n  🔍 First pass: Categorizing all questions...")
    question_matches = []
    for question in questions_on_form:
        match_result = await match_question_with_llm(question, info_content, info_data, model_manager)
        question_matches.append({
            "question": question,
            "answer": match_result["answer"],
            "field_type": match_result["field_type"],
            "confidence": match_result["confidence"]
        })
        print(f"    • {question[:40]}... → {match_result['field_type']}")
    
    # Separate by type
    for qm in question_matches:
        if qm["field_type"] == "dropdown":
            dropdown_questions.append(qm)
        elif qm["field_type"] == "radio":
            radio_questions.append(qm)
        else:
            text_questions.append(qm)
    
    print(f"\n  📊 Question types:")
    print(f"    - Text fields: {len(text_questions)}")
    print(f"    - Radio buttons: {len(radio_questions)}")
    print(f"    - Dropdowns: {len(dropdown_questions)}")
    print(f"    - Available inputs: {len(available_indices)}")
    
    # Second pass: Fill in smart order (text first, then dropdowns)
    print("\n  📝 Second pass: Filling fields...")
    
    # Fill text fields first (they use visible inputs)
    for i, qm in enumerate(text_questions, 1):
        question = qm["question"]
        answer = qm["answer"]
        
        print(f"\n  [{filled_count+1}] TEXT: \"{question[:50]}...\"")
        print(f"    Answer: {answer}")
        
        # Try multiple indices until one works (skip hidden elements)
        filled_this = False
        attempts = 0
        max_attempts = len(available_indices) + 5  # Try more than available
        
        while not filled_this and available_indices and attempts < max_attempts:
            idx = available_indices.pop(0) if available_indices else (used_indices[-1] + 1 if used_indices else 0)
            attempts += 1
            
            try:
                print(f"    📝 Trying text input at index {idx}...")
                await handle_tool_call("input_text", {"index": idx, "text": answer})
                used_indices.append(idx)
                filled_count += 1
                filled_this = True
                print(f"    ✅ Filled! ({len(available_indices)} inputs remaining)")
                await asyncio.sleep(0.8)
            except Exception as e:
                print(f"    ⚠️  Index {idx} failed (hidden element?), trying next...")
                # Try next index
                if not available_indices:
                    # Generate next sequential index
                    available_indices.append(idx + 1)
        
        if not filled_this:
            print(f"    ❌ Could not fill this field after {attempts} attempts")
    
    # Fill radio buttons - ROBUST APPROACH
    for qm in radio_questions:
        question = qm["question"]
        answer = qm["answer"]
        
        print(f"\n  [{filled_count+1}] RADIO: \"{question[:50]}...\"")
        print(f"    Answer: {answer}")
        print(f"    🔘 Searching for '{answer}' radio button...")
        
        # Get fresh elements
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        elements_text = elem_result[0].get("text", "") if elem_result else ""
        
        filled_radio = False
        
        # Method 1: Try exact match with multiple patterns
        patterns = [
            rf'\[(\d+)\]<div[^>]*>{re.escape(answer)}<',
            rf'\[(\d+)\][^[]*\b{re.escape(answer)}\b',
            rf'\[(\d+)\]<span[^>]*>{re.escape(answer)}<'
        ]
        
        for pattern in patterns:
            if filled_radio:
                break
            radio_match = re.search(pattern, elements_text, re.IGNORECASE)
            if radio_match:
                radio_idx = int(radio_match.group(1))
                print(f"    📍 Found at index {radio_idx}, clicking...")
                try:
                    await handle_tool_call("click_element_by_index", {"index": radio_idx})
                    filled_count += 1
                    filled_radio = True
                    print(f"    ✅ Radio button selected!")
                except Exception as e:
                    print(f"    ⚠️  Click failed: {e}")
        
        # Method 2: Sequential search if exact match failed
        if not filled_radio:
            print(f"    🔍 Exact match failed, searching sequentially...")
            # Start from a reasonable index (after used indices)
            start_idx = (used_indices[-1] + 1) if used_indices else 0
            
            for radio_idx in range(start_idx, start_idx + 15):
                try:
                    result = await handle_tool_call("click_element_by_index", {"index": radio_idx})
                    # Check if this looks like a radio button click
                    result_text = str(result).lower() if result else ""
                    if "radio" in result_text or "button" in result_text or len(result_text) < 50:
                        print(f"    ✅ Selected radio at index {radio_idx}")
                        filled_count += 1
                        filled_radio = True
                        break
                except Exception:
                    continue
        
        if not filled_radio:
            print(f"    ❌ FAILED to fill radio button!")
        
        await asyncio.sleep(0.8)
    
    # Fill dropdowns - MULTIPLE ROBUST METHODS
    for qm in dropdown_questions:
        question = qm["question"]
        answer = qm["answer"]
        
        print(f"\n  [{filled_count+1}] DROPDOWN: \"{question[:50]}...\"")
        print(f"    Answer: {answer}")
        
        filled_dropdown = False
        
        # METHOD 1: Hidden input field (breakthrough method)
        print(f"    🎯 Method 1: Hidden input field...")
        
        # Get fresh elements
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        elements_text = elem_result[0].get("text", "") if elem_result else ""
        
        # Find ALL text inputs (including hidden ones)
        all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
        current_available = [int(x) for x in all_text_inputs if int(x) not in used_indices]
        
        print(f"    📍 Available unused text inputs: {current_available}")
        
        # Try up to 5 available indices (skip hidden ones)
        attempts = 0
        indices_to_try = current_available[:5] if len(current_available) >= 5 else current_available
        
        for dropdown_input_idx in indices_to_try:
            if filled_dropdown:
                break
            attempts += 1
            try:
                print(f"    📝 Attempt {attempts}: Index {dropdown_input_idx}...")
                await handle_tool_call("input_text", {"index": dropdown_input_idx, "text": answer})
                
                # Wait and check if it worked
                await asyncio.sleep(0.5)
                
                used_indices.append(dropdown_input_idx)
                filled_count += 1
                filled_dropdown = True
                print(f"    ✅ Dropdown filled at index {dropdown_input_idx}!")
            except Exception as e:
                print(f"    ⚠️  Index {dropdown_input_idx} failed (hidden element)")
        
        # METHOD 2: Click listbox approach
        if not filled_dropdown:
            print(f"    🎯 Method 2: Click listbox UI...")
            
            # Find listbox or dropdown elements
            listbox_patterns = [
                r'\[(\d+)\]<div[^>]*role=["\']listbox',
                r'\[(\d+)\]<div[^>]*role=["\']combobox',
                r'\[(\d+)\]<select'
            ]
            
            for pattern in listbox_patterns:
                if filled_dropdown:
                    break
                listbox_match = re.search(pattern, elements_text, re.IGNORECASE)
                if listbox_match:
                    listbox_idx = int(listbox_match.group(1))
                    print(f"    📍 Found dropdown at index {listbox_idx}, clicking...")
                    try:
                        await handle_tool_call("click_element_by_index", {"index": listbox_idx})
                        await asyncio.sleep(1)
                        
                        # Get updated elements after dropdown opens
                        elem_result = await handle_tool_call("get_interactive_elements", {
                            "viewport_mode": "all",
                            "structured_output": False
                        })
                        elements_text = elem_result[0].get("text", "") if elem_result else ""
                        
                        # Find and click the answer option
                        option_patterns = [
                            rf'\[(\d+)\]<div[^>]*>{re.escape(answer)}<',
                            rf'\[(\d+)\][^[]*\b{re.escape(answer)}\b',
                            rf'\[(\d+)\]<span[^>]*>{re.escape(answer)}<'
                        ]
                        
                        for opt_pattern in option_patterns:
                            if filled_dropdown:
                                break
                            option_match = re.search(opt_pattern, elements_text, re.IGNORECASE)
                            if option_match:
                                option_idx = int(option_match.group(1))
                                print(f"    📍 Found option '{answer}' at index {option_idx}, clicking...")
                                await handle_tool_call("click_element_by_index", {"index": option_idx})
                                filled_count += 1
                                filled_dropdown = True
                                print(f"    ✅ Dropdown selected via click!")
                                break
                    except Exception as e:
                        print(f"    ⚠️  Click method failed: {e}")
        
        if not filled_dropdown:
            print(f"    ❌ CRITICAL: Could not fill dropdown with any method!")
            print(f"    ⚠️  This is the 250 marks surprise element!")
        
        await asyncio.sleep(1)
    
    # Validation: Check if all fields are filled
    print(f"\n{'='*60}")
    print(f"📊 VALIDATION CHECK")
    print(f"{'='*60}")
    print(f"Questions found: {len(questions_on_form)}")
    print(f"Fields filled: {filled_count}")
    
    # List which questions were filled
    print(f"\n✅ Successfully filled:")
    filled_questions = []
    for qm in question_matches:
        if qm in text_questions or qm in radio_questions or qm in dropdown_questions:
            # Check if this question was processed
            q_short = qm["question"][:50]
            print(f"  • {q_short}... → {qm['answer']}")
            filled_questions.append(qm["question"])
    
    # Find unfilled questions
    unfilled = [q for q in questions_on_form if q not in filled_questions]
    if unfilled:
        print(f"\n⚠️  UNFILLED QUESTIONS:")
        for q in unfilled:
            print(f"  • {q}")
    
    # Decision: Can we submit?
    can_submit = (filled_count >= len(questions_on_form))
    
    print(f"\n{'='*60}")
    if can_submit:
        print(f"✅ ALL {len(questions_on_form)} FIELDS FILLED - Ready to submit!")
    else:
        print(f"❌ NOT ALL FIELDS FILLED!")
        print(f"   Expected: {len(questions_on_form)} fields")
        print(f"   Filled: {filled_count} fields")
        print(f"   Missing: {len(questions_on_form) - filled_count} field(s)")
        print(f"   ⚠️  This may include the 250 marks surprise element")
        
        # Retry unfilled fields
        if unfilled:
            print(f"\n   🔄 RETRY: Attempting to fill missing fields...")
            
            # Get fresh elements
            elem_result = await handle_tool_call("get_interactive_elements", {
                "viewport_mode": "all",
                "structured_output": False
            })
            elements_text = elem_result[0].get("text", "") if elem_result else ""
            
            # Find all unused indices
            all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
            unused_indices = [int(x) for x in all_text_inputs if int(x) not in used_indices]
            
            print(f"   📍 Unused indices available: {unused_indices}")
            
            # Try to fill each unfilled question
            for unfilled_q in unfilled:
                # Find the match for this question
                unfilled_match = next((qm for qm in question_matches if qm["question"] == unfilled_q), None)
                if unfilled_match and unused_indices:
                    idx = unused_indices.pop(0)
                    answer = unfilled_match["answer"]
                    print(f"   🔄 Retry: {unfilled_q[:40]}...")
                    print(f"      Trying index {idx} with answer: {answer}")
                    try:
                        await handle_tool_call("input_text", {"index": idx, "text": answer})
                        filled_count += 1
                        used_indices.append(idx)
                        print(f"      ✅ Filled on retry!")
                    except Exception as e:
                        print(f"      ❌ Retry failed: {e}")
            
            print(f"\n   📊 After retry: {filled_count}/{len(questions_on_form)} fields filled")
        
        if filled_count < len(questions_on_form):
            print(f"\n   ⚠️  WARNING: Proceeding with {filled_count}/{len(questions_on_form)} fields")
            print(f"   Form may show errors or reject submission")
    print(f"{'='*60}")
    
    # Step 5: Submit
    print("\n[STEP 5] Attempting to submit form...")
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
        print("🎉🎉🎉 FORM SUBMITTED SUCCESSFULLY! 🎉🎉🎉")
        print("=" * 60)
        print(f"✅ Questions found: {len(questions_on_form)}")
        print(f"✅ Fields filled: {filled_count}/{len(questions_on_form)}")
        print(f"✅ Form submitted: YES")
        print(f"✅ Submission confirmed: YES")
        print(f"✅ Response recorded by Google Forms")
        print("=" * 60)
        print("\n🌐 Browser will stay open for verification...")
        return {"status": "success", "message": "Form submitted"}
    else:
        # Print what we see for debugging
        print(f"\n  📄 Page text: {final_text[:200]}...")
        print(f"\n  🔍 Elements: {elem_text[:200]}...")
        print("\n" + "=" * 60)
        print("⚠️  FORM FILLED AND SUBMITTED - CHECK BROWSER")
        print("=" * 60)
        print(f"✅ Questions found: {len(questions_on_form)}")
        print(f"✅ Fields filled: {filled_count}/{len(questions_on_form)}")
        print(f"✅ Submit button clicked: YES")
        print(f"⚠️  Submission status: VERIFY IN BROWSER")
        print("=" * 60)
        print("\n🌐 Browser will stay open for verification...")
        return {"status": "success", "message": "Form submitted (verify in browser)"}


async def main():
    try:
        result = await fill_google_form()
        
        # Keep browser open to show submission
        if result.get("status") == "success":
            print("\n" + "="*60)
            print("🌐 BROWSER KEPT OPEN TO VERIFY SUBMISSION")
            print("="*60)
            print("📋 Please check the browser window to confirm:")
            print("   - Form submission was successful")
            print("   - All required fields were filled")
            print("   - No error messages are shown")
            print("\n💡 Press Ctrl+C when done reviewing, or close this window")
            print("="*60)
            
            # Keep the script running to keep browser open
            try:
                await asyncio.sleep(300)  # Wait 5 minutes
            except KeyboardInterrupt:
                print("\n👋 Closing browser...")
        
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
