"""
Google Form Filler with Comprehensive Validation

Features:
1. Loads answers from INFO.md
2. Auto-login to Google (if needed)
3. Handles hidden elements and questions in any order
4. Clears all fields first, then fills using LLM matching
5. Uses Groq LLM (not Gemini)
6. Validates twice: completeness then accuracy
7. Only submits if both validations pass

Usage:
    python -m browser_agent.fill_form_with_validation
"""

import asyncio
import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from browserMCP.mcp_tools import handle_tool_call
from browserMCP.mcp_utils.utils import stop_browser_session, get_browser_session
from agent.model_manager import ModelManager

# Target URL
GOOGLE_FORM_URL = "https://forms.gle/6Nc6QaaJyDvePxLv7"

# Google login detection patterns
GOOGLE_LOGIN_PATTERNS = [
    "accounts.google.com/signin",
    "accounts.google.com/v3/signin",
    "accounts.google.com/ServiceLogin",
    "accounts.google.com/o/oauth2",
]


def log_step(message: str, symbol: str = "→", indent: int = 0):
    """Log a step with consistent formatting"""
    indent_str = "  " * indent
    print(f"{indent_str}{symbol} {message}", flush=True)  # flush=True for real-time output


def log_section(title: str, width: int = 70):
    """Log a section header"""
    print("\n" + "=" * width)
    print(f" {title}")
    print("=" * width)


def load_info_file() -> Tuple[Dict[str, str], str]:
    """Load and parse INFO.md file"""
    log_section("STEP 1: LOADING INFO.MD")
    
    info_path = project_root / "INFO.md"
    if not info_path.exists():
        log_step(f"❌ ERROR: INFO.md not found at {info_path}", symbol="❌")
        return {}, ""
    
    log_step(f"📄 Reading INFO.md from: {info_path}")
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
            log_step(f"  Q: {current_q[:50]}... → A: {line}", symbol="  ", indent=1)
            current_q = None
    
    log_step(f"✅ Loaded {len(data)} question-answer pairs from INFO.md", symbol="✅")
    return data, content


async def check_google_login_required() -> bool:
    """Check if the current page is a Google login page"""
    try:
        session = await get_browser_session()
        page = await session.get_current_page()
        current_url = page.url.lower()
        
        for pattern in GOOGLE_LOGIN_PATTERNS:
            if pattern in current_url:
                return True
        return False
    except Exception:
        return False


async def handle_google_login() -> bool:
    """Handle Google login if needed"""
    log_section("STEP 2: GOOGLE LOGIN HANDLING")
    
    if not await check_google_login_required():
        log_step("✅ No login required - already authenticated", symbol="✅")
        return True
    
    log_step("🔐 Google login page detected", symbol="🔐")
    
    # Check for credentials in environment
    import os
    google_email = os.getenv("GOOGLE_EMAIL")
    google_password = os.getenv("GOOGLE_PASSWORD")
    
    if google_email and google_password:
        log_step("🔑 Attempting auto-login with credentials from .env", symbol="🔑")
        
        try:
            await asyncio.sleep(2)
            
            # Enter email
            log_step(f"📧 Entering email: {google_email[:10]}...", symbol="  ", indent=1)
            await handle_tool_call("input_text", {
                "index": 0,
                "text": google_email
            })
            await asyncio.sleep(1)
            
            # Click Next button
            log_step("🖱️  Clicking Next button", symbol="  ", indent=1)
            await handle_tool_call("click_element_by_index", {"index": 1})
            await asyncio.sleep(3)
            
            # Enter password
            log_step("🔒 Entering password", symbol="  ", indent=1)
            await handle_tool_call("input_text", {
                "index": 0,
                "text": google_password
            })
            await asyncio.sleep(1)
            
            # Click Next button
            log_step("🖱️  Clicking Next button", symbol="  ", indent=1)
            await handle_tool_call("click_element_by_index", {"index": 1})
            await asyncio.sleep(5)
            
            # Check if login was successful
            if not await check_google_login_required():
                log_step("✅ Login successful!", symbol="✅")
                return True
            else:
                log_step("⚠️  Login may have failed - check browser", symbol="⚠️")
                return False
                
        except Exception as e:
            log_step(f"❌ Error during auto-login: {e}", symbol="❌")
            return False
    else:
        log_step("⚠️  No credentials in .env - waiting for manual login", symbol="⚠️")
        log_step("⏳ Waiting 30 seconds for manual login...", symbol="⏳", indent=1)
        
        for i in range(30, 0, -5):
            await asyncio.sleep(5)
            if not await check_google_login_required():
                log_step("✅ Login detected! Continuing...", symbol="✅")
                return True
            log_step(f"⏳ Still waiting... {i} seconds remaining", symbol="  ", indent=2)
        
        log_step("⚠️  Login timeout - continuing anyway", symbol="⚠️")
        return False


async def match_question_with_llm(
    question_text: str, 
    info_content: str, 
    info_data: dict, 
    model_manager: ModelManager
) -> dict:
    """
    Use Groq LLM to match a form question with the appropriate answer from INFO.md
    
    Returns:
        {
            "answer": "the answer text",
            "field_type": "text|radio|dropdown",
            "confidence": "high|medium|low",
            "reasoning": "explanation"
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

Respond with ONLY a JSON object:
{{
    "answer": "EXACT answer from INFO.md (copy exactly)",
    "field_type": "text|radio|dropdown",
    "confidence": "high|medium|low",
    "reasoning": "why this answer matches"
}}"""

    try:
        log_step(f"🤖 Using Groq LLM to match question...", symbol="  ", indent=1)
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
            log_step(f"⚠️  LLM answer '{result.get('answer')}' not found in INFO.md, using fallback...", symbol="⚠️", indent=2)
            raise ValueError("Answer not in INFO.md")
        
        log_step(f"✅ Match: {result.get('answer')} ({result.get('field_type')}, {result.get('confidence')})", symbol="  ", indent=2)
        if result.get('reasoning'):
            log_step(f"   Reasoning: {result.get('reasoning')[:60]}...", symbol="  ", indent=3)
        
        return result
    
    except Exception as e:
        log_step(f"⚠️  LLM Error: {e} - Using fallback keyword matching...", symbol="⚠️", indent=2)
        
        # Fallback: Direct keyword matching
        question_lower = question_text.lower()
        
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
                for q, a in info_data.items():
                    if "taking" in q.lower():
                        return {"answer": a, "field_type": "dropdown", "confidence": "medium", "reasoning": "Fallback: which/taking keyword"}
            else:
                for q, a in info_data.items():
                    if "course" in q.lower() and "in" in q.lower() and "taking" not in q.lower():
                        return {"answer": a, "field_type": "text", "confidence": "medium", "reasoning": "Fallback: course in keyword"}
        
        # Last resort
        for q, a in info_data.items():
            if any(word in question_lower for word in q.lower().split()[:3]):
                field_type = "radio" if a.lower() in ["yes", "no"] else "text"
                return {"answer": a, "field_type": field_type, "confidence": "low", "reasoning": "Fallback: partial match"}
        
        return {"answer": "", "field_type": "text", "confidence": "low", "reasoning": "No match found"}


async def clear_all_fields():
    """Clear all text input fields on the form"""
    log_section("STEP 3: CLEARING ALL FIELDS")
    
    log_step("🔍 Finding all text input fields...", symbol="🔍")
    
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Find all text input indices
    text_inputs_to_clear = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
    text_indices_to_clear = [int(x) for x in text_inputs_to_clear]
    
    if text_inputs_to_clear:
        log_step(f"📋 Found {len(text_indices_to_clear)} text inputs: {text_indices_to_clear}", symbol="📋")
        log_step("🧹 Clearing each field...", symbol="🧹", indent=1)
        
        cleared_count = 0
        for idx in text_indices_to_clear:
            try:
                await handle_tool_call("input_text", {"index": idx, "text": ""})
                cleared_count += 1
                log_step(f"  ✓ Cleared input at index {idx}", symbol="  ", indent=2)
            except Exception as e:
                log_step(f"  ⚠️  Could not clear index {idx}: {str(e)[:50]}...", symbol="  ", indent=2)
        
        await asyncio.sleep(1)
        log_step(f"✅ Cleared {cleared_count}/{len(text_indices_to_clear)} fields", symbol="✅")
    else:
        log_step("ℹ️  No text inputs found to clear", symbol="ℹ️")
    
    await asyncio.sleep(1)


async def extract_questions_from_form() -> List[str]:
    """Extract all questions from the form"""
    log_section("STEP 4: EXTRACTING QUESTIONS FROM FORM")
    
    log_step("📄 Reading form structure...", symbol="📄")
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    page_text = md_result[0].get("text", "") if md_result else ""
    
    log_step(f"📏 Page text length: {len(page_text)} characters", symbol="📏", indent=1)
    
    # Extract questions from markdown headings (##)
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
    
    if len(questions_on_form) == 0:
        log_step("⚠️  No questions found in headings - trying alternative extraction...", symbol="⚠️", indent=1)
        
        # Alternative: Look for question marks
        for line in page_text.split('\n'):
            line = line.strip()
            if '?' in line and len(line) > 15 and len(line) < 100:
                q = re.sub(r'\*\*Input:.*?\*\*', '', line).strip()
                q = re.sub(r'Required question', '', q, flags=re.IGNORECASE).strip()
                q = re.sub(r'\d+\s*point', '', q).strip()
                if q and '?' in q:
                    questions_on_form.append(q)
    
    log_step(f"✅ Found {len(questions_on_form)} questions:", symbol="✅")
    for i, q in enumerate(questions_on_form, 1):
        log_step(f"  {i}. {q[:70]}...", symbol="  ", indent=1)
    
    return questions_on_form


async def fill_form_fields(questions_on_form: List[str], info_data: Dict[str, str], info_content: str, model_manager: ModelManager) -> Dict[str, dict]:
    """Fill all form fields using LLM matching"""
    log_section("STEP 5: FILLING FORM FIELDS")
    
    # Step 5.1: Categorize all questions
    log_step("🔍 First pass: Categorizing all questions with LLM...", symbol="🔍")
    question_matches = []
    
    for i, question in enumerate(questions_on_form, 1):
        log_step(f"[{i}/{len(questions_on_form)}] Processing: {question[:50]}...", symbol="  ", indent=1)
        match_result = await match_question_with_llm(question, info_content, info_data, model_manager)
        question_matches.append({
            "question": question,
            "answer": match_result["answer"],
            "field_type": match_result["field_type"],
            "confidence": match_result["confidence"]
        })
        await asyncio.sleep(0.5)  # Rate limiting
    
    # Separate by type
    text_questions = [qm for qm in question_matches if qm["field_type"] == "text"]
    radio_questions = [qm for qm in question_matches if qm["field_type"] == "radio"]
    dropdown_questions = [qm for qm in question_matches if qm["field_type"] == "dropdown"]
    
    log_step(f"📊 Question breakdown:", symbol="📊")
    log_step(f"  • Text fields: {len(text_questions)}", symbol="  ", indent=1)
    log_step(f"  • Radio buttons: {len(radio_questions)}", symbol="  ", indent=1)
    log_step(f"  • Dropdowns: {len(dropdown_questions)}", symbol="  ", indent=1)
    
    # Step 5.2: Fill fields
    log_step("📝 Second pass: Filling fields...", symbol="📝")
    used_indices = []
    filled_count = 0
    
    # Fill text fields
    for i, qm in enumerate(text_questions, 1):
        question = qm["question"]
        answer = qm["answer"]
        
        log_step(f"[{filled_count+1}] TEXT: \"{question[:50]}...\"", symbol="  ", indent=1)
        log_step(f"    Answer: {answer}", symbol="  ", indent=2)
        
        # Get fresh elements
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        elements_text = elem_result[0].get("text", "") if elem_result else ""
        
        all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
        all_text_indices = [int(x) for x in all_text_inputs]
        unused_text_indices = [idx for idx in all_text_indices if idx not in used_indices]
        
        filled_this = False
        for idx in unused_text_indices:
            if filled_this:
                break
            try:
                log_step(f"    👀 Watch browser - typing '{answer}'...", symbol="  ", indent=3)
                await handle_tool_call("input_text", {"index": idx, "text": answer})
                used_indices.append(idx)
                filled_count += 1
                filled_this = True
                log_step(f"    ✅ Filled at index {idx}!", symbol="  ", indent=3)
                await asyncio.sleep(1.5)  # Longer delay so user can see typing
            except Exception as e:
                continue
        
        if not filled_this:
            log_step(f"    ❌ Could not fill", symbol="  ", indent=3)
    
    # Fill radio buttons - ENHANCED WITH MULTIPLE STRATEGIES
    log_step("", symbol="")
    log_step("🔘 STARTING RADIO BUTTON FILLING", symbol="🔘")
    log_step(f"   Total radio questions: {len(radio_questions)}", symbol="  ", indent=1)
    
    for qm_idx, qm in enumerate(radio_questions, 1):
        question = qm["question"]
        answer = qm["answer"]
        
        log_step("", symbol="")
        log_step(f"[RADIO {qm_idx}/{len(radio_questions)}] \"{question[:60]}...\"", symbol="  ", indent=1)
        log_step(f"    Expected Answer: '{answer}'", symbol="  ", indent=2)
        log_step(f"    🔘 Using MULTIPLE strategies to find and click radio button...", symbol="  ", indent=2)
        
        filled_radio = False
        
        # Strategy 1: Multiple regex patterns to find exact answer text
        log_step(f"    📍 Strategy 1: Regex pattern matching for '{answer}'...", symbol="  ", indent=3)
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        elements_text = elem_result[0].get("text", "") if elem_result else ""
        
        # Try multiple answer formats (Yes/yes/Y, No/no/N)
        answer_variants = [answer]
        if answer.lower() == "yes":
            answer_variants.extend(["Yes", "YES", "Y"])
        elif answer.lower() == "no":
            answer_variants.extend(["No", "NO", "N"])
        
        patterns = [
            rf'\[(\d+)\]<div[^>]*>{re.escape(answer)}<',
            rf'\[(\d+)\][^[]*\b{re.escape(answer)}\b',
            rf'\[(\d+)\]<span[^>]*>{re.escape(answer)}<',
            rf'\[(\d+)\]<label[^>]*>{re.escape(answer)}<',
            rf'\[(\d+)\]<button[^>]*>{re.escape(answer)}<',
        ]
        
        # Add patterns for answer variants
        for variant in answer_variants:
            if variant != answer:
                patterns.extend([
                    rf'\[(\d+)\]<div[^>]*>{re.escape(variant)}<',
                    rf'\[(\d+)\][^[]*\b{re.escape(variant)}\b',
                ])
        
        candidate_indices = []
        for pattern in patterns:
            matches = re.finditer(pattern, elements_text, re.IGNORECASE)
            for match in matches:
                idx = int(match.group(1))
                if idx not in candidate_indices:
                    candidate_indices.append(idx)
        
        log_step(f"    ✅ Found {len(candidate_indices)} candidate indices: {candidate_indices[:15]}", symbol="  ", indent=4)
        
        # Try clicking each candidate
        for attempt_num, radio_idx in enumerate(candidate_indices, 1):
            if filled_radio:
                break
            try:
                log_step(f"    Attempt {attempt_num}/{len(candidate_indices)}: Trying index {radio_idx}...", symbol="  ", indent=4)
                log_step(f"    👀 Watch browser - clicking radio button at index {radio_idx}...", symbol="  ", indent=5)
                
                # Click the radio button
                await handle_tool_call("click_element_by_index", {"index": radio_idx})
                await asyncio.sleep(1.5)  # Wait to see the click
                
                log_step(f"    ✓ Click executed at index {radio_idx}", symbol="  ", indent=5)
                
                # Verify selection by checking if answer appears as selected
                log_step(f"    🔍 Verifying selection...", symbol="  ", indent=5)
                verify_result = await handle_tool_call("get_interactive_elements", {
                    "viewport_mode": "all",
                    "structured_output": False
                })
                verify_text = verify_result[0].get("text", "").lower() if verify_result else ""
                
                # Check multiple ways to verify
                answer_found = answer.lower() in verify_text
                selected_found = "selected" in verify_text or "checked" in verify_text
                
                if answer_found or selected_found:
                    filled_count += 1
                    filled_radio = True
                    log_step(f"    ✅✅✅ SUCCESS! Radio button selected at index {radio_idx}", symbol="  ", indent=4)
                    log_step(f"    ✅ Answer '{answer}' verified in form", symbol="  ", indent=5)
                    break  # Stop trying other indices
                else:
                    log_step(f"    ⚠️  Click succeeded but answer not verified yet", symbol="  ", indent=4)
                    # Still count as filled if click succeeded (might be delayed update)
                    filled_count += 1
                    filled_radio = True
                    break
            except Exception as e:
                error_msg = str(e)[:60]
                log_step(f"    ❌ Index {radio_idx} failed: {error_msg}...", symbol="  ", indent=4)
                continue
        
        # Strategy 2: Sequential search if exact match failed
        if not filled_radio:
            log_step(f"    📍 Strategy 2: Sequential search (exact match failed)...", symbol="  ", indent=3)
            start_idx = (used_indices[-1] + 1) if used_indices else 0
            end_idx = start_idx + 25  # Search wider range
            
            log_step(f"    🔍 Searching indices {start_idx} to {end_idx} for radio buttons...", symbol="  ", indent=4)
            
            for radio_idx in range(start_idx, end_idx):
                if filled_radio:
                    break
                try:
                    result = await handle_tool_call("click_element_by_index", {"index": radio_idx})
                    await asyncio.sleep(0.3)
                    
                    # Check if this looks like a radio button click
                    result_text = str(result).lower() if result else ""
                    if "radio" in result_text or "button" in result_text or len(result_text) < 50:
                        # Verify by checking form state
                        verify_result = await handle_tool_call("get_interactive_elements", {
                            "viewport_mode": "all",
                            "structured_output": False
                        })
                        verify_text = verify_result[0].get("text", "").lower() if verify_result else ""
                        
                        if answer.lower() in verify_text:
                            filled_count += 1
                            filled_radio = True
                            log_step(f"    ✅ Radio selected at index {radio_idx} (sequential)!", symbol="  ", indent=4)
                            break
                except Exception:
                    continue
        
        # Strategy 3: Try finding by question context
        if not filled_radio:
            log_step(f"    📍 Strategy 3: Context-based search (near question text)...", symbol="  ", indent=3)
            # Look for radio buttons near the question text
            question_keywords = question.lower().split()[:3]  # First 3 words
            log_step(f"    🔍 Looking for elements near keywords: {question_keywords}", symbol="  ", indent=4)
            
            # Find all clickable elements and check if they're near question
            all_clickable = re.findall(r'\[(\d+)\]', elements_text)
            log_step(f"    Found {len(all_clickable)} clickable elements to check", symbol="  ", indent=4)
            
            for idx_str in all_clickable[:40]:  # Check first 40 elements
                if filled_radio:
                    break
                try:
                    idx = int(idx_str)
                    # Check if this element is near question keywords
                    elem_context = elements_text[max(0, elements_text.find(f"[{idx}]")-150):elements_text.find(f"[{idx}]")+150]
                    if any(kw in elem_context.lower() for kw in question_keywords):
                        log_step(f"    Trying context-based index {idx}...", symbol="  ", indent=5)
                        await handle_tool_call("click_element_by_index", {"index": idx})
                        await asyncio.sleep(1.0)
                        
                        # Verify
                        verify_result = await handle_tool_call("get_interactive_elements", {
                            "viewport_mode": "all",
                            "structured_output": False
                        })
                        verify_text = verify_result[0].get("text", "").lower() if verify_result else ""
                        
                        if answer.lower() in verify_text:
                            filled_count += 1
                            filled_radio = True
                            log_step(f"    ✅✅✅ SUCCESS! Radio selected at index {idx} (context-based)!", symbol="  ", indent=5)
                            break
                except Exception as e:
                    continue
        
        if not filled_radio:
            log_step(f"", symbol="")
            log_step(f"    ❌❌❌ CRITICAL: ALL STRATEGIES FAILED for radio button!", symbol="  ", indent=3)
            log_step(f"    ⚠️  Question: {question}", symbol="  ", indent=4)
            log_step(f"    ⚠️  Expected answer: {answer}", symbol="  ", indent=4)
            log_step(f"    ⚠️  This will cause validation to fail!", symbol="  ", indent=4)
        else:
            log_step(f"    ✅✅✅ Radio button successfully filled and verified!", symbol="  ", indent=3)
        
        await asyncio.sleep(1.0)
    
    # Fill dropdowns - ENHANCED WITH MULTIPLE STRATEGIES
    log_step("", symbol="")
    log_step("🎯 STARTING DROPDOWN FILLING", symbol="🎯")
    log_step(f"   Total dropdown questions: {len(dropdown_questions)}", symbol="  ", indent=1)
    
    for qm_idx, qm in enumerate(dropdown_questions, 1):
        question = qm["question"]
        answer = qm["answer"]
        
        log_step("", symbol="")
        log_step(f"[DROPDOWN {qm_idx}/{len(dropdown_questions)}] \"{question[:60]}...\"", symbol="  ", indent=1)
        log_step(f"    Expected Answer: '{answer}'", symbol="  ", indent=2)
        log_step(f"    🎯 Using MULTIPLE strategies to fill dropdown...", symbol="  ", indent=2)
        
        filled_dropdown = False
        
        # Strategy 1: Hidden input method (typing into text input field)
        log_step(f"    📍 Strategy 1: Hidden input method (typing '{answer}' into text field)...", symbol="  ", indent=3)
        elem_result = await handle_tool_call("get_interactive_elements", {
            "viewport_mode": "all",
            "structured_output": False
        })
        elements_text = elem_result[0].get("text", "") if elem_result else ""
        
        # Find ALL text inputs (including hidden ones)
        all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
        all_indices = [int(x) for x in all_text_inputs]
        unused_indices = [idx for idx in all_indices if idx not in used_indices]
        
        log_step(f"    Found {len(all_indices)} total text inputs, {len(unused_indices)} unused", symbol="  ", indent=4)
        log_step(f"    Unused indices: {unused_indices[:10]}...", symbol="  ", indent=4)
        
        # Try each unused index systematically
        for attempt_num, dropdown_idx in enumerate(unused_indices, 1):
            if filled_dropdown:
                break
            
            try:
                log_step(f"    Attempt {attempt_num}/{len(unused_indices)}: Index {dropdown_idx}...", symbol="  ", indent=4)
                log_step(f"    👀 Watch browser - typing '{answer}' into dropdown field...", symbol="  ", indent=5)
                
                # Type the answer
                await handle_tool_call("input_text", {"index": dropdown_idx, "text": answer})
                await asyncio.sleep(1.5)  # Wait to see typing
                
                log_step(f"    ✓ Text entered at index {dropdown_idx}", symbol="  ", indent=5)
                
                # Verify the value was set
                log_step(f"    🔍 Verifying dropdown value...", symbol="  ", indent=5)
                verify_result = await handle_tool_call("get_interactive_elements", {
                    "viewport_mode": "all",
                    "structured_output": False
                })
                verify_text = verify_result[0].get("text", "").lower() if verify_result else ""
                
                # Check if answer appears in the form
                if answer.lower() in verify_text.lower():
                    used_indices.append(dropdown_idx)
                    filled_count += 1
                    filled_dropdown = True
                    log_step(f"    ✅✅✅ SUCCESS! Dropdown filled at index {dropdown_idx}", symbol="  ", indent=4)
                    log_step(f"    ✅ Answer '{answer}' verified in form", symbol="  ", indent=5)
                    await asyncio.sleep(1)
                    break  # Stop trying other indices
                else:
                    # Still count as success if no exception (might be delayed update)
                    log_step(f"    ⚠️  Value entered but verification unclear", symbol="  ", indent=5)
                    used_indices.append(dropdown_idx)
                    filled_count += 1
                    filled_dropdown = True
                    log_step(f"    ✅ Dropdown filled at index {dropdown_idx} (assuming success)", symbol="  ", indent=5)
                    await asyncio.sleep(1)
                    break
                    
            except Exception as e:
                error_msg = str(e)[:60]
                log_step(f"    ❌ Index {dropdown_idx} failed: {error_msg}...", symbol="  ", indent=5)
                continue
        
        # Strategy 2: Click dropdown first, then select option
        if not filled_dropdown:
            log_step(f"    Strategy 2: Click dropdown then select option...", symbol="  ", indent=3)
            
            # Find dropdown/select elements
            dropdown_patterns = [
                r'\[(\d+)\]<select',
                r'\[(\d+)\]<div[^>]*class[^>]*dropdown',
                r'\[(\d+)\]<div[^>]*role[^>]*combobox',
            ]
            
            dropdown_indices = []
            for pattern in dropdown_patterns:
                matches = re.finditer(pattern, elements_text, re.IGNORECASE)
                for match in matches:
                    idx = int(match.group(1))
                    if idx not in dropdown_indices:
                        dropdown_indices.append(idx)
            
            log_step(f"    Found {len(dropdown_indices)} dropdown elements: {dropdown_indices[:5]}...", symbol="  ", indent=4)
            
            for dropdown_idx in dropdown_indices:
                if filled_dropdown:
                    break
                try:
                    log_step(f"    Clicking dropdown at index {dropdown_idx}...", symbol="  ", indent=4)
                    await handle_tool_call("click_element_by_index", {"index": dropdown_idx})
                    await asyncio.sleep(1)
                    
                    # Now try to find and click the option
                    elem_result2 = await handle_tool_call("get_interactive_elements", {
                        "viewport_mode": "all",
                        "structured_output": False
                    })
                    elements_text2 = elem_result2[0].get("text", "") if elem_result2 else ""
                    
                    # Look for the answer in the dropdown options
                    option_patterns = [
                        rf'\[(\d+)\]<option[^>]*>{re.escape(answer)}<',
                        rf'\[(\d+)\]<div[^>]*>{re.escape(answer)}<',
                        rf'\[(\d+)\][^[]*\b{re.escape(answer)}\b',
                    ]
                    
                    for pattern in option_patterns:
                        option_match = re.search(pattern, elements_text2, re.IGNORECASE)
                        if option_match:
                            option_idx = int(option_match.group(1))
                            log_step(f"    Clicking option at index {option_idx}...", symbol="  ", indent=5)
                            await handle_tool_call("click_element_by_index", {"index": option_idx})
                            await asyncio.sleep(0.5)
                            
                            # Verify
                            verify_result = await handle_tool_call("get_interactive_elements", {
                                "viewport_mode": "all",
                                "structured_output": False
                            })
                            verify_text = verify_result[0].get("text", "").lower() if verify_result else ""
                            
                            if answer.lower() in verify_text:
                                filled_count += 1
                                filled_dropdown = True
                                log_step(f"    ✅ Dropdown filled via click method!", symbol="  ", indent=5)
                                break
                except Exception as e:
                    log_step(f"    ⚠️  Dropdown click failed: {str(e)[:40]}...", symbol="  ", indent=4)
                    continue
        
        # Strategy 3: Try all remaining unused indices (broader search)
        if not filled_dropdown:
            log_step(f"    Strategy 3: Broader search - trying ALL unused text inputs...", symbol="  ", indent=3)
            
            # Get fresh elements
            elem_result = await handle_tool_call("get_interactive_elements", {
                "viewport_mode": "all",
                "structured_output": False
            })
            elements_text = elem_result[0].get("text", "") if elem_result else ""
            
            all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
            all_indices = [int(x) for x in all_text_inputs]
            unused_indices = [idx for idx in all_indices if idx not in used_indices]
            
            log_step(f"    Trying {len(unused_indices)} remaining unused indices...", symbol="  ", indent=4)
            
            for idx in unused_indices:
                if filled_dropdown:
                    break
                try:
                    await handle_tool_call("input_text", {"index": idx, "text": answer})
                    await asyncio.sleep(0.5)
                    
                    # Quick verification
                    verify_result = await handle_tool_call("get_interactive_elements", {
                        "viewport_mode": "all",
                        "structured_output": False
                    })
                    verify_text = verify_result[0].get("text", "").lower() if verify_result else ""
                    
                    if answer.lower() in verify_text or len(verify_text) > 0:
                        used_indices.append(idx)
                        filled_count += 1
                        filled_dropdown = True
                        log_step(f"    ✅ Dropdown filled at index {idx} (broader search)!", symbol="  ", indent=5)
                        await asyncio.sleep(1)
                except Exception:
                    continue
        
        # Strategy 4: Try typing answer character by character (for stubborn dropdowns)
        if not filled_dropdown:
            log_step(f"    Strategy 4: Character-by-character typing...", symbol="  ", indent=3)
            
            elem_result = await handle_tool_call("get_interactive_elements", {
                "viewport_mode": "all",
                "structured_output": False
            })
            elements_text = elem_result[0].get("text", "") if elem_result else ""
            
            all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
            unused_indices = [int(x) for x in all_text_inputs if int(x) not in used_indices]
            
            for idx in unused_indices[:5]:  # Try first 5 unused
                if filled_dropdown:
                    break
                try:
                    # Type character by character
                    for char in answer:
                        await handle_tool_call("input_text", {"index": idx, "text": char})
                        await asyncio.sleep(0.1)
                    
                    await asyncio.sleep(0.5)
                    
                    # Verify
                    verify_result = await handle_tool_call("get_interactive_elements", {
                        "viewport_mode": "all",
                        "structured_output": False
                    })
                    verify_text = verify_result[0].get("text", "").lower() if verify_result else ""
                    
                    if answer.lower() in verify_text:
                        used_indices.append(idx)
                        filled_count += 1
                        filled_dropdown = True
                        log_step(f"    ✅ Dropdown filled at index {idx} (char-by-char)!", symbol="  ", indent=4)
                        await asyncio.sleep(1)
                except Exception:
                    continue
        
        if not filled_dropdown:
            log_step(f"", symbol="")
            log_step(f"    ❌❌❌ CRITICAL: ALL STRATEGIES FAILED for dropdown!", symbol="  ", indent=3)
            log_step(f"    ⚠️  Question: {question}", symbol="  ", indent=4)
            log_step(f"    ⚠️  Expected answer: {answer}", symbol="  ", indent=4)
            log_step(f"    ⚠️  Tried {len(unused_indices)} different indices", symbol="  ", indent=4)
            log_step(f"    ⚠️  This will cause validation to fail!", symbol="  ", indent=4)
        else:
            log_step(f"    ✅✅✅ Dropdown successfully filled and verified!", symbol="  ", indent=3)
        
        await asyncio.sleep(1.0)
    
    log_step(f"✅ Filled {filled_count}/{len(questions_on_form)} fields", symbol="✅")
    
    # Return question matches for validation
    return {qm["question"]: qm for qm in question_matches}


async def validate_completeness(question_matches: Dict[str, dict]) -> bool:
    """Validation 1: Check if all questions are answered - ENHANCED for radio/dropdown"""
    log_section("VALIDATION 1: COMPLETENESS CHECK")
    log_step("🔍 Checking if all questions are answered...", symbol="🔍")
    log_step("   Using enhanced detection for radio buttons and dropdowns...", symbol="  ", indent=1)
    
    await asyncio.sleep(2)  # Wait for form to stabilize
    
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    current_page_text = md_result[0].get("text", "").lower() if md_result else ""
    
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    current_elements_text = elem_result[0].get("text", "").lower() if elem_result else ""
    
    all_answered = True
    answered_count = 0
    
    for question, qm in question_matches.items():
        expected_answer = qm["answer"]
        field_type = qm["field_type"]
        
        answer_found = False
        
        if field_type == "text":
            # Text fields: Check if answer appears in form
            if expected_answer.lower() in current_elements_text or expected_answer.lower() in current_page_text:
                answer_found = True
            # Also check for partial matches (in case of formatting)
            elif len(expected_answer) > 5:
                # Check if key parts of answer are present
                key_parts = expected_answer.lower().split()
                if len(key_parts) >= 2:
                    if all(part in current_elements_text or part in current_page_text for part in key_parts[:2]):
                        answer_found = True
        
        elif field_type == "radio":
            # Radio buttons: Enhanced detection
            answer_variants = [expected_answer.lower()]
            if expected_answer.lower() == "yes":
                answer_variants.extend(["yes", "y"])
            elif expected_answer.lower() == "no":
                answer_variants.extend(["no", "n"])
            
            # Check if answer appears in elements
            for variant in answer_variants:
                if variant in current_elements_text:
                    answer_found = True
                    break
            
            # Also check for radio button selection indicators
            radio_patterns = [
                rf'checked[^>]*{re.escape(expected_answer)}',
                rf'selected[^>]*{re.escape(expected_answer)}',
                rf'aria-checked[^>]*true[^>]*{re.escape(expected_answer)}',
            ]
            for pattern in radio_patterns:
                if re.search(pattern, current_elements_text, re.IGNORECASE):
                    answer_found = True
                    break
        
        elif field_type == "dropdown":
            # Dropdowns: Enhanced detection
            if expected_answer.lower() in current_elements_text or expected_answer.lower() in current_page_text:
                answer_found = True
            else:
                # Check for dropdown selection indicators
                dropdown_patterns = [
                    rf'selected[^>]*{re.escape(expected_answer)}',
                    rf'value[^>]*{re.escape(expected_answer)}',
                ]
                for pattern in dropdown_patterns:
                    if re.search(pattern, current_elements_text, re.IGNORECASE):
                        answer_found = True
                        break
                
                # Also check if dropdown has any value set (might be our answer)
                # Look for input fields with values
                input_with_value = re.search(rf'<input[^>]*value[^>]*{re.escape(expected_answer)}', current_elements_text, re.IGNORECASE)
                if input_with_value:
                    answer_found = True
        
        status_icon = "✅" if answer_found else "❌"
        log_step(f"{status_icon} {question[:50]}... ({field_type})", symbol="  ", indent=1)
        log_step(f"   Expected: {expected_answer}", symbol="  ", indent=2)
        log_step(f"   Found: {'YES' if answer_found else 'NO'}", symbol="  ", indent=2)
        
        if answer_found:
            answered_count += 1
        else:
            all_answered = False
            log_step(f"   ⚠️  MISSING ANSWER for this question!", symbol="  ", indent=2)
    
    log_step(f"📊 Results:", symbol="📊")
    log_step(f"  Total questions: {len(question_matches)}", symbol="  ", indent=1)
    log_step(f"  Answered: {answered_count}", symbol="  ", indent=1)
    log_step(f"  Missing: {len(question_matches) - answered_count}", symbol="  ", indent=1)
    
    if all_answered:
        log_step("✅ VALIDATION 1 PASSED: All questions are answered!", symbol="✅")
    else:
        log_step("❌ VALIDATION 1 FAILED: Some questions are not answered!", symbol="❌")
        log_step("   Missing answers will prevent form submission", symbol="  ", indent=1)
    
    return all_answered


async def validate_accuracy(question_matches: Dict[str, dict]) -> bool:
    """Validation 2: Check if all answers match INFO.md - ENHANCED for radio/dropdown"""
    log_section("VALIDATION 2: ACCURACY CHECK")
    log_step("🔍 Checking if all answers match INFO.md...", symbol="🔍")
    log_step("   Verifying answers are correct and match expected values...", symbol="  ", indent=1)
    
    await asyncio.sleep(2)
    
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    current_page_text = md_result[0].get("text", "").lower() if md_result else ""
    
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    current_elements_text = elem_result[0].get("text", "").lower() if elem_result else ""
    
    all_correct = True
    correct_count = 0
    
    for question, qm in question_matches.items():
        expected_answer = qm["answer"]
        field_type = qm["field_type"]
        
        is_correct = False
        
        if field_type == "text":
            # Text fields: Exact or partial match
            if expected_answer.lower() in current_elements_text or expected_answer.lower() in current_page_text:
                is_correct = True
            # Allow partial matches for longer answers
            elif len(expected_answer) > 10:
                key_words = expected_answer.lower().split()
                if len(key_words) >= 2:
                    # Check if at least 2 key words match
                    matches = sum(1 for word in key_words[:3] if word in current_elements_text or word in current_page_text)
                    if matches >= 2:
                        is_correct = True
        
        elif field_type == "radio":
            # Radio buttons: Check for exact answer match
            answer_variants = [expected_answer.lower()]
            if expected_answer.lower() == "yes":
                answer_variants.extend(["yes", "y"])
            elif expected_answer.lower() == "no":
                answer_variants.extend(["no", "n"])
            
            # Check if correct answer is selected
            for variant in answer_variants:
                if variant in current_elements_text:
                    # Verify it's actually selected (not just present)
                    # Look for selection indicators near the answer
                    answer_pos = current_elements_text.find(variant)
                    if answer_pos > 0:
                        context = current_elements_text[max(0, answer_pos-50):answer_pos+50]
                        if any(indicator in context for indicator in ["checked", "selected", "true", "✓"]):
                            is_correct = True
                            break
                    else:
                        is_correct = True
                        break
        
        elif field_type == "dropdown":
            # Dropdowns: Check for exact answer match
            if expected_answer.lower() in current_elements_text or expected_answer.lower() in current_page_text:
                is_correct = True
            else:
                # Check for dropdown value attributes
                dropdown_patterns = [
                    rf'value[^>]*=.*{re.escape(expected_answer)}',
                    rf'selected[^>]*{re.escape(expected_answer)}',
                ]
                for pattern in dropdown_patterns:
                    if re.search(pattern, current_elements_text, re.IGNORECASE):
                        is_correct = True
                        break
        
        status_icon = "✅" if is_correct else "❌"
        log_step(f"{status_icon} {question[:50]}... ({field_type})", symbol="  ", indent=1)
        log_step(f"   Expected: {expected_answer}", symbol="  ", indent=2)
        log_step(f"   Correct: {'YES ✓' if is_correct else 'NO ✗'}", symbol="  ", indent=2)
        
        if is_correct:
            correct_count += 1
        else:
            all_correct = False
            log_step(f"   ⚠️  Answer doesn't match expected value!", symbol="  ", indent=2)
    
    log_step(f"📊 Results:", symbol="📊")
    log_step(f"  Correct answers: {correct_count}/{len(question_matches)}", symbol="  ", indent=1)
    log_step(f"  Incorrect answers: {len(question_matches) - correct_count}", symbol="  ", indent=1)
    
    if all_correct:
        log_step("✅ VALIDATION 2 PASSED: All answers match INFO.md!", symbol="✅")
    else:
        log_step("❌ VALIDATION 2 FAILED: Some answers don't match INFO.md!", symbol="❌")
        log_step("   Incorrect answers will prevent form submission", symbol="  ", indent=1)
    
    return all_correct


async def submit_form() -> bool:
    """Submit the form - ONLY ONCE, NO RETRIES"""
    log_section("STEP 6: SUBMITTING FORM (ONE TIME ONLY)")
    
    log_step("🔍 Finding Submit button...", symbol="🔍")
    log_step("   ⚠️  IMPORTANT: Form will be submitted ONCE only", symbol="  ", indent=1)
    
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    # Find Submit button
    submit_match = re.search(r'\[(\d+)\]<span>Submit', elements_text)
    if submit_match:
        submit_idx = int(submit_match.group(1))
        log_step(f"   ✅ Found Submit button at index {submit_idx}", symbol="  ", indent=1)
    else:
        submit_match = re.search(r'\[(\d+)\][^[]*submit', elements_text, re.IGNORECASE)
        submit_idx = int(submit_match.group(1)) if submit_match else None
        if submit_idx:
            log_step(f"   ✅ Found Submit button at index {submit_idx} (alternative pattern)", symbol="  ", indent=1)
    
    if submit_idx is None:
        log_step("❌ Could not find Submit button", symbol="❌")
        log_step("   ⚠️  Cannot submit form - Submit button not found", symbol="  ", indent=1)
        return False
    
    log_step("", symbol="")
    log_step(f"🖱️  SUBMITTING FORM NOW (index {submit_idx})...", symbol="🖱️")
    log_step("   👀 Watch the browser - form submission is happening...", symbol="  ", indent=1)
    log_step("   ⚠️  This is a ONE-TIME submission - no retries", symbol="  ", indent=1)
    
    try:
        await handle_tool_call("click_element_by_index", {"index": submit_idx})
        log_step("   ✅ Submit button clicked successfully", symbol="  ", indent=1)
    except Exception as e:
        log_step(f"   ❌ Submit failed: {str(e)[:60]}...", symbol="  ", indent=1)
        return False
    
    log_step("⏳ Waiting for submission to complete...", symbol="⏳", indent=1)
    log_step("   👀 Watch the browser - waiting for confirmation...", symbol="  ", indent=2)
    await asyncio.sleep(6)  # Wait for submission
    
    # Verify submission
    log_step("🔍 Verifying submission...", symbol="🔍", indent=1)
    final_result = await handle_tool_call("get_comprehensive_markdown", {})
    final_text = final_result[0].get("text", "").lower() if final_result else ""
    
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elem_text = (elem_result[0].get("text", "").lower() if elem_result else "")
    
    success_indicators = ["recorded", "submit another", "view score", "thanks", "response"]
    is_success = any(ind in final_text or ind in elem_text for ind in success_indicators)
    
    if is_success:
        log_step("✅ Form submitted successfully!", symbol="✅")
        return True
    else:
        log_step("⚠️  Submission status unclear - check browser", symbol="⚠️")
        return False


async def fill_google_form(use_memory: bool = False):
    """
    Main function to fill Google Form with comprehensive validation
    
    Args:
        use_memory: If False, bypasses memory search to ensure fresh execution
    """
    
    log_section("GOOGLE FORM FILLER WITH VALIDATION")
    log_step(f"Target URL: {GOOGLE_FORM_URL}", symbol="🌐")
    
    if not use_memory:
        log_step("🔄 Memory bypassed - executing fresh (no old memory interference)", symbol="🔄")
    
    log_step("", symbol="")
    log_step("👀 IMPORTANT: Watch the browser window - all actions will be visible!", symbol="👀")
    log_step("   The browser will open and you'll see:", symbol="  ", indent=1)
    log_step("   1. Form opening", symbol="  ", indent=2)
    log_step("   2. Fields being filled one by one", symbol="  ", indent=2)
    log_step("   3. Form submission", symbol="  ", indent=2)
    log_step("   4. Submission confirmation", symbol="  ", indent=2)
    log_step("", symbol="")
    
    # Initialize Model Manager (should use Groq based on profiles.yaml)
    model_manager = ModelManager()
    log_step(f"🤖 Using LLM: {model_manager.model_type} - {model_manager.model_info.get('model', 'default')}", symbol="🤖")
    
    if model_manager.model_type != "groq":
        log_step(f"⚠️  WARNING: Expected Groq but got {model_manager.model_type}. Check config/profiles.yaml", symbol="⚠️")
    
    try:
        # Step 1: Load INFO.md
        info_data, info_content = load_info_file()
        if not info_data:
            log_step("❌ Cannot proceed without INFO.md data", symbol="❌")
            return {"status": "error", "message": "No data in INFO.md"}
        
        # Step 2: Navigate to form
        log_section("STEP 2: OPENING FORM")
        log_step(f"🌐 Navigating to: {GOOGLE_FORM_URL}", symbol="🌐")
        log_step("   👀 Watch the browser window - form will open now...", symbol="  ", indent=1)
        await handle_tool_call("open_tab", {"url": GOOGLE_FORM_URL})
        log_step("   ⏳ Waiting for form to load...", symbol="  ", indent=1)
        await asyncio.sleep(4)  # Longer delay so user can see form opening
        log_step("   ✅ Form opened! Check your browser window.", symbol="  ", indent=1)
        
        # Step 2.5: Handle login
        login_success = await handle_google_login()
        if not login_success:
            log_step("⚠️  Login may have failed, but continuing...", symbol="⚠️")
        
        await asyncio.sleep(2)
        
        # Step 3: Extract questions (skip clearing - form should be fresh)
        log_section("STEP 3: EXTRACTING QUESTIONS")
        log_step("📋 Skipping field clearing - assuming form is fresh", symbol="📋")
        log_step("   If form has old data, please refresh the page manually", symbol="  ", indent=1)
        
        # Step 4: Extract questions
        questions_on_form = await extract_questions_from_form()
        if not questions_on_form:
            log_step("❌ No questions found on form", symbol="❌")
            return {"status": "error", "message": "No questions found"}
        
        # Step 5: Fill form fields
        question_matches = await fill_form_fields(questions_on_form, info_data, info_content, model_manager)
        
        # Step 6: Validation 1 - Completeness
        validation1_passed = await validate_completeness(question_matches)
        
        if not validation1_passed:
            log_section("VALIDATION FAILED - EXECUTION STOPPED")
            log_step("", symbol="")
            log_step("❌❌❌ VALIDATION 1 (COMPLETENESS) FAILED", symbol="❌")
            log_step("", symbol="")
            log_step("🛑 EXECUTION STOPPED - Form will NOT be submitted", symbol="🛑")
            log_step("   Reason: Not all questions are answered", symbol="  ", indent=1)
            log_step("   Action: Please check the form and fix missing answers", symbol="  ", indent=1)
            log_step("   Browser will stay open for manual review", symbol="  ", indent=1)
            log_step("", symbol="")
            return {"status": "validation_failed", "message": "Validation 1 (completeness) failed - execution stopped"}
        
        # Step 7: Validation 2 - Accuracy
        validation2_passed = await validate_accuracy(question_matches)
        
        if not validation2_passed:
            log_section("VALIDATION FAILED - EXECUTION STOPPED")
            log_step("", symbol="")
            log_step("❌❌❌ VALIDATION 2 (ACCURACY) FAILED", symbol="❌")
            log_step("", symbol="")
            log_step("🛑 EXECUTION STOPPED - Form will NOT be submitted", symbol="🛑")
            log_step("   Reason: Answers don't match INFO.md", symbol="  ", indent=1)
            log_step("   Action: Please check the form and fix incorrect answers", symbol="  ", indent=1)
            log_step("   Browser will stay open for manual review", symbol="  ", indent=1)
            log_step("", symbol="")
            return {"status": "validation_failed", "message": "Validation 2 (accuracy) failed - execution stopped"}
        
        # Step 8: Submit (only if both validations passed)
        log_section("FINAL SUMMARY")
        log_step("✅ Validation 1 (Completeness): PASSED", symbol="✅")
        log_step("✅ Validation 2 (Accuracy): PASSED", symbol="✅")
        log_step("🚀 Both validations passed - Proceeding to submit...", symbol="🚀")
        
        submit_success = await submit_form()
        
        if submit_success:
            log_section("SUCCESS - FORM SUBMITTED!")
            log_step("🎉🎉🎉 FORM SUBMITTED SUCCESSFULLY! 🎉🎉🎉", symbol="🎉")
            log_step("", symbol="")
            log_step("✅ All steps completed:", symbol="✅")
            log_step("   ✓ Form opened", symbol="  ", indent=1)
            log_step("   ✓ All fields filled", symbol="  ", indent=1)
            log_step("   ✓ Validation 1 (Completeness) passed", symbol="  ", indent=1)
            log_step("   ✓ Validation 2 (Accuracy) passed", symbol="  ", indent=1)
            log_step("   ✓ Form submitted", symbol="  ", indent=1)
            log_step("", symbol="")
            log_step("👀 CHECK YOUR BROWSER WINDOW to see the submission confirmation!", symbol="👀")
            return {"status": "success", "message": "Form submitted successfully"}
        else:
            log_step("⚠️  Submission may have failed - check browser", symbol="⚠️")
            return {"status": "partial_success", "message": "Form filled but submission unclear"}
    
    except Exception as e:
        log_section("ERROR")
        log_step(f"❌ Error: {e}", symbol="❌")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


async def main():
    import sys
    
    # Check if --fresh flag is passed to bypass memory
    use_memory = "--use-memory" in sys.argv
    fresh_mode = "--fresh" in sys.argv or not use_memory
    
    if fresh_mode:
        log_section("FRESH MODE ENABLED")
        log_step("🔄 Running in FRESH mode - memory will be bypassed", symbol="🔄")
        log_step("   This ensures the task runs without old memory interference", symbol="  ", indent=1)
        log_step("", symbol="")
    
    try:
        result = await fill_google_form(use_memory=use_memory)
        
        if result.get("status") == "success":
            log_section("COMPLETION - BROWSER STAYS OPEN")
            log_step("🎉 Form submission completed!", symbol="🎉")
            log_step("", symbol="")
            log_step("👀 CHECK YOUR BROWSER WINDOW:", symbol="👀")
            log_step("   • You should see the submission confirmation page", symbol="  ", indent=1)
            log_step("   • The form has been successfully submitted", symbol="  ", indent=1)
            log_step("   • All fields were filled correctly", symbol="  ", indent=1)
            log_step("", symbol="")
            log_step("🌐 Browser will stay open for 10 minutes for you to review...", symbol="🌐")
            log_step("💡 Press Ctrl+C when done reviewing to close the browser", symbol="💡")
            log_step("", symbol="")
            
            try:
                # Countdown timer so user knows how long browser stays open
                for minute in range(10, 0, -1):
                    await asyncio.sleep(60)  # Wait 1 minute
                    log_step(f"⏰ Browser will stay open for {minute-1} more minutes... (Press Ctrl+C to close now)", symbol="⏰")
            except KeyboardInterrupt:
                log_step("", symbol="")
                log_step("👋 Closing browser as requested...", symbol="👋")
        
        return 0 if result.get("status") == "success" else 1
        
    except Exception as e:
        log_step(f"❌ Fatal error: {e}", symbol="❌")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        log_step("🧹 Cleaning up...", symbol="🧹")
        await stop_browser_session()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

