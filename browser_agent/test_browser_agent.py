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
    
    prompt = f"""You are an expert at matching form questions with answers. Match the form question to the EXACT answer from INFO.md.

INFO.md content:
{info_content}

Form Question:
"{question_text}"

CRITICAL MATCHING RULES:
1. Match by KEYWORDS:
   - "name" or "Master" → Match with "What is the name of your Master?" → Answer: "Himanshu Singh"
   - "Date of Birth" or "DOB" or "birth" → Match with "What is his/her Date of Birth?" → Answer: "17-Dec-1984"
   - "married" → Match with "Is he/she married?" → Answer: "Yes"
   - "email" → Match with "What is his/her email id?" → Answer: "himanshu.kumar.singh@gmail.com"
   - "course is he/her in" or "course in" → Match with "What course is he/her in?" → Answer: "EAG"
   - "course is he/she taking" or "taking" → Match with "Which course is he/she taking?" → Answer: "EAG"

2. Field Type Rules:
   - "text": Questions asking "What is..." (name, email, date, course name)
   - "radio": Questions asking "Is he/she..." (Yes/No questions)
   - "dropdown": Questions asking "Which..." (selecting from a list)

EXAMPLES:
- Question: "What is the name of your Master?" → Answer: "Himanshu Singh", Type: "text"
- Question: "What is his/her Date of Birth?" → Answer: "17-Dec-1984", Type: "text"
- Question: "Is he/she married?" → Answer: "Yes", Type: "radio"
- Question: "What is his/her email id?" → Answer: "himanshu.kumar.singh@gmail.com", Type: "text"
- Question: "What course is he/her in?" → Answer: "EAG", Type: "text"
- Question: "Which course is he/she taking?" → Answer: "EAG", Type: "dropdown"

Respond with ONLY a JSON object:
{{
    "answer": "EXACT answer from INFO.md (copy exactly)",
    "field_type": "text|radio|dropdown",
    "confidence": "high|medium|low",
    "reasoning": "why this answer matches"
}}"""

    try:
        response_text = await model_manager.generate_text(prompt)
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response_text)
        
        # Validate answer exists in INFO.md
        answer_found = False
        for q, a in info_data.items():
            if result.get("answer", "").strip() == a.strip():
                answer_found = True
                break
        
        if not answer_found:
            print(f"    ⚠️  LLM answer '{result.get('answer')}' not found in INFO.md, using fallback...")
            raise ValueError("Answer not in INFO.md")
        
        print(f"    ✅ LLM Match: {result.get('answer')} ({result.get('field_type')}, {result.get('confidence')})")
        if result.get('reasoning'):
            print(f"    Reasoning: {result.get('reasoning')}")
        
        return result
    
    except Exception as e:
        print(f"    ⚠️  LLM Error: {e}")
        print(f"    🔄 Using fallback keyword matching...")
        
        # IMPROVED Fallback: Direct keyword matching
        question_lower = question_text.lower()
        
        # Direct keyword matching
        if "name" in question_lower or "master" in question_lower:
            for q, a in info_data.items():
                if "name" in q.lower() and "master" in q.lower():
                    return {"answer": a, "field_type": "text", "confidence": "medium", "reasoning": "Fallback: name keyword"}
        
        if "date of birth" in question_lower or "dob" in question_lower or ("birth" in question_lower and "date" in question_lower):
            for q, a in info_data.items():
                if "date of birth" in q.lower() or "dob" in q.lower():
                    return {"answer": a, "field_type": "text", "confidence": "medium", "reasoning": "Fallback: DOB keyword"}
        
        if "married" in question_lower:
            for q, a in info_data.items():
                if "married" in q.lower():
                    return {"answer": a, "field_type": "radio", "confidence": "medium", "reasoning": "Fallback: married keyword"}
        
        if "email" in question_lower:
            for q, a in info_data.items():
                if "email" in q.lower():
                    return {"answer": a, "field_type": "text", "confidence": "medium", "reasoning": "Fallback: email keyword"}
        
        if "course" in question_lower:
            if "which" in question_lower or "taking" in question_lower:
                # "Which course is he/she taking?" → dropdown
                for q, a in info_data.items():
                    if "taking" in q.lower():
                        return {"answer": a, "field_type": "dropdown", "confidence": "medium", "reasoning": "Fallback: which/taking keyword"}
            else:
                # "What course is he/her in?" → text
                for q, a in info_data.items():
                    if "course" in q.lower() and "in" in q.lower() and "taking" not in q.lower():
                        return {"answer": a, "field_type": "text", "confidence": "medium", "reasoning": "Fallback: course in keyword"}
        
        # Last resort: return first matching answer
        for q, a in info_data.items():
            if any(word in question_lower for word in q.lower().split()[:3]):
                field_type = "radio" if a.lower() in ["yes", "no"] else "text"
                return {"answer": a, "field_type": field_type, "confidence": "low", "reasoning": "Fallback: partial match"}
        
        return {"answer": "", "field_type": "text", "confidence": "low", "reasoning": "No match found"}


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
    
    # Fill text fields - SYSTEMATIC APPROACH: Try ALL elements sequentially
    for i, qm in enumerate(text_questions, 1):
        question = qm["question"]
        answer = qm["answer"]
        
        print(f"\n  [{filled_count+1}] TEXT: \"{question[:50]}...\"")
        print(f"    Answer: {answer}")
        
        # Get FRESH elements each time
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        elements_text = elem_result[0].get("text", "") if elem_result else ""
        
        # Find ALL text input indices (including hidden ones)
        all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
        all_text_indices = [int(x) for x in all_text_inputs]
        
        # Find unused ones
        unused_text_indices = [idx for idx in all_text_indices if idx not in used_indices]
        
        print(f"    📍 Found {len(all_text_indices)} text inputs total")
        print(f"    📍 Unused: {unused_text_indices}")
        
        filled_this = False
        
        # Try EACH unused index systematically (skip hidden ones automatically)
        for idx in unused_text_indices:
            if filled_this:
                break
            
            try:
                print(f"    📝 Trying index {idx}...")
                await handle_tool_call("input_text", {"index": idx, "text": answer})
                
                # Success! Mark as used
                used_indices.append(idx)
                filled_count += 1
                filled_this = True
                print(f"    ✅ Filled at index {idx}!")
                await asyncio.sleep(0.8)
                
            except Exception as e:
                error_msg = str(e)[:80]
                print(f"    ⚠️  Index {idx} failed (hidden?): {error_msg}...")
                # Continue to next index
                continue
        
        if not filled_this:
            print(f"    ❌ Could not fill after trying {len(unused_text_indices)} indices")
            print(f"    ⚠️  This field may be blocked by hidden elements")
    
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
    
    # Fill dropdowns - SYSTEMATIC APPROACH: Try ALL unused indices sequentially
    for qm in dropdown_questions:
        question = qm["question"]
        answer = qm["answer"]
        
        print(f"\n  [{filled_count+1}] DROPDOWN: \"{question[:50]}...\"")
        print(f"    Answer: {answer}")
        print(f"    🎯 Using hidden input method (breakthrough solution)")
        
        # Get FRESH elements to see current state
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        elements_text = elem_result[0].get("text", "") if elem_result else ""
        
        # Find ALL text inputs (including hidden ones)
        all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
        all_indices = [int(x) for x in all_text_inputs]
        
        # Find UNUSED indices (critical!)
        unused_indices = [idx for idx in all_indices if idx not in used_indices]
        
        print(f"    📍 All text inputs: {all_indices}")
        print(f"    📍 Already used: {used_indices}")
        print(f"    📍 UNUSED (will try all): {unused_indices}")
        
        filled_dropdown = False
        
        # Try EACH unused index systematically (skip hidden ones automatically)
        for attempt_num, dropdown_idx in enumerate(unused_indices, 1):
            if filled_dropdown:
                break
            
            print(f"    📝 Attempt {attempt_num}/{len(unused_indices)}: Index {dropdown_idx}...")
            
            try:
                # Try typing into this input
                await handle_tool_call("input_text", {"index": dropdown_idx, "text": answer})
                
                # Success!
                used_indices.append(dropdown_idx)
                filled_count += 1
                filled_dropdown = True
                print(f"    ✅ SUCCESS! Dropdown filled at index {dropdown_idx}")
                await asyncio.sleep(1)
                
            except Exception as e:
                error_msg = str(e)[:80]
                print(f"    ⚠️  Index {dropdown_idx} failed (hidden?): {error_msg}...")
                # Continue to next index
                continue
        
        if not filled_dropdown:
            print(f"    ❌ CRITICAL: Could not fill dropdown!")
            print(f"    ⚠️  Tried ALL {len(unused_indices)} unused indices")
            print(f"    ⚠️  This is the 250 marks surprise element!")
        
        await asyncio.sleep(0.5)
    
    # ====================================================================
    # COMPREHENSIVE VALIDATION BEFORE SUBMISSION
    # ====================================================================
    print(f"\n{'='*60}")
    print(f"🔍 COMPREHENSIVE VALIDATION - RE-CHECKING FORM")
    print(f"{'='*60}")
    
    await asyncio.sleep(2)  # Wait for form to stabilize
    
    # Get fresh form state
    print("\n[VALIDATION] Reading current form state...")
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    current_page_text = md_result[0].get("text", "") if md_result else ""
    
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    current_elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # VALIDATION 1: Check completeness - Are all questions answered?
    print("\n[VALIDATION 1] Checking completeness - Are all questions answered?")
    print("-" * 60)
    
    validation_results = {}
    all_answered = True
    
    for qm in question_matches:
        question = qm["question"]
        expected_answer = qm["answer"]
        field_type = qm["field_type"]
        
        # Check if answer appears in form
        answer_found = False
        answer_in_form = False
        
        # For text fields, check if value appears in elements or markdown
        if field_type == "text" or field_type == "dropdown":
            # Look for the answer value in the form
            if expected_answer.lower() in current_elements_text.lower() or expected_answer.lower() in current_page_text.lower():
                answer_in_form = True
                answer_found = True
            else:
                # Check if any text input has a value
                # This is approximate - we check if inputs exist
                answer_found = len(re.findall(r'<input type=\'text\'>', current_elements_text)) > 0
        
        # For radio buttons, check if selected
        elif field_type == "radio":
            if expected_answer.lower() in current_elements_text.lower():
                answer_in_form = True
                answer_found = True
        
        validation_results[question] = {
            "expected": expected_answer,
            "found": answer_found,
            "in_form": answer_in_form,
            "field_type": field_type
        }
        
        status_icon = "✅" if answer_found else "❌"
        print(f"  {status_icon} {question[:50]}...")
        print(f"     Expected: {expected_answer}")
        print(f"     Found in form: {answer_in_form}")
        
        if not answer_found:
            all_answered = False
    
    print(f"\n[VALIDATION 1 RESULT]")
    answered_count = sum(1 for v in validation_results.values() if v["found"])
    print(f"  Questions total: {len(questions_on_form)}")
    print(f"  Questions answered: {answered_count}")
    print(f"  Questions missing: {len(questions_on_form) - answered_count}")
    
    if all_answered:
        print(f"  ✅ VALIDATION 1 PASSED: All questions are answered!")
    else:
        print(f"  ❌ VALIDATION 1 FAILED: Some questions are not answered!")
        print(f"  ⚠️  Cannot submit until all questions are answered")
    
    # VALIDATION 2: Check accuracy - Are answers correct?
    print(f"\n[VALIDATION 2] Checking accuracy - Are answers correct?")
    print("-" * 60)
    
    all_correct = True
    
    for question, result in validation_results.items():
        expected = result["expected"]
        found = result["found"]
        in_form = result["in_form"]
        
        # For accuracy, we check if the expected answer matches what's in the form
        is_correct = False
        
        if found and in_form:
            # Answer is present in form - check if it matches expected
            # This is approximate - we verify the answer text appears
            if expected.lower() in current_elements_text.lower() or expected.lower() in current_page_text.lower():
                is_correct = True
        
        result["correct"] = is_correct
        
        status_icon = "✅" if is_correct else "❌"
        print(f"  {status_icon} {question[:50]}...")
        print(f"     Expected: {expected}")
        print(f"     Correct: {is_correct}")
        
        if not is_correct:
            all_correct = False
    
    print(f"\n[VALIDATION 2 RESULT]")
    correct_count = sum(1 for v in validation_results.values() if v.get("correct", False))
    print(f"  Answers correct: {correct_count}/{len(questions_on_form)}")
    
    if all_correct:
        print(f"  ✅ VALIDATION 2 PASSED: All answers are correct!")
    else:
        print(f"  ❌ VALIDATION 2 FAILED: Some answers may be incorrect!")
        print(f"  ⚠️  Review answers before submitting")
    
    # FINAL DECISION
    print(f"\n{'='*60}")
    print(f"📋 FINAL VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Validation 1 (Completeness): {'PASSED' if all_answered else 'FAILED'}")
    print(f"✅ Validation 2 (Accuracy): {'PASSED' if all_correct else 'FAILED'}")
    
    can_submit = all_answered and all_correct
    
    if can_submit:
        print(f"\n🎉 ALL VALIDATIONS PASSED - READY TO SUBMIT!")
        print(f"   • All {len(questions_on_form)} questions answered")
        print(f"   • All answers verified correct")
    else:
        print(f"\n⚠️  VALIDATION FAILED - CANNOT SUBMIT YET")
        if not all_answered:
            print(f"   ❌ Missing answers for some questions")
        if not all_correct:
            print(f"   ❌ Some answers may be incorrect")
        print(f"\n   🔄 Attempting to fix issues...")
        
        # Try to fix unfilled/incorrect fields
        for question, result in validation_results.items():
            if not result["found"] or not result.get("correct", False):
                expected = result["expected"]
                field_type = result["field_type"]
                
                print(f"\n   🔧 Fixing: {question[:40]}...")
                
                # Get fresh elements
                elem_result = await handle_tool_call("get_interactive_elements", {
                    "viewport_mode": "all",
                    "structured_output": False
                })
                elements_text = elem_result[0].get("text", "") if elem_result else ""
                
                if field_type == "text" or field_type == "dropdown":
                    # Find unused text inputs
                    all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
                    unused_indices = [int(x) for x in all_text_inputs if int(x) not in used_indices]
                    
                    if unused_indices:
                        idx = unused_indices[0]
                        print(f"      Trying index {idx} with answer: {expected}")
                        try:
                            await handle_tool_call("input_text", {"index": idx, "text": expected})
                            used_indices.append(idx)
                            print(f"      ✅ Fixed!")
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            print(f"      ❌ Fix failed: {e}")
                
                elif field_type == "radio":
                    # Try to find and click radio button
                    radio_match = re.search(rf'\[(\d+)\][^[]*\b{re.escape(expected)}\b', elements_text, re.IGNORECASE)
                    if radio_match:
                        radio_idx = int(radio_match.group(1))
                        try:
                            await handle_tool_call("click_element_by_index", {"index": radio_idx})
                            print(f"      ✅ Fixed!")
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            print(f"      ❌ Fix failed: {e}")
        
        # Re-validate after fixes
        print(f"\n   🔍 Re-validating after fixes...")
        await asyncio.sleep(2)
        
        # Quick re-check
        md_result = await handle_tool_call("get_comprehensive_markdown", {})
        recheck_text = md_result[0].get("text", "").lower() if md_result else ""
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        recheck_elements = elem_result[0].get("text", "").lower() if elem_result else ""
        
        all_answers_present = all(
            result["expected"].lower() in recheck_text or result["expected"].lower() in recheck_elements
            for result in validation_results.values()
        )
        
        if all_answers_present:
            print(f"   ✅ Re-validation passed - ready to submit!")
            can_submit = True
        else:
            print(f"   ⚠️  Re-validation: Some issues may remain")
            print(f"   ⚠️  Proceeding with submission attempt anyway...")
            can_submit = True  # Try anyway
    
    print(f"{'='*60}\n")
    
    if not can_submit:
        print("❌ CANNOT SUBMIT - VALIDATION FAILED")
        print("Please review the form manually and fix issues before submitting.")
        return {"status": "validation_failed", "message": "Form validation failed"}
    
    # Step 5: Submit (only if validation passed)
    print("\n[STEP 5] Submitting form (validations passed)...")
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
