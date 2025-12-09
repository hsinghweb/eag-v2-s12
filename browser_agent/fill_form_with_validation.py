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
    print(f"{indent_str}{symbol} {message}", flush=True)


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
    
    import os
    google_email = os.getenv("GOOGLE_EMAIL")
    google_password = os.getenv("GOOGLE_PASSWORD")
    
    if google_email and google_password:
        log_step("🔑 Attempting auto-login with credentials from .env", symbol="🔑")
        
        try:
            await asyncio.sleep(2)
            
            log_step(f"📧 Entering email: {google_email[:10]}...", symbol="  ", indent=1)
            await handle_tool_call("input_text", {
                "index": 0,
                "text": google_email
            })
            await asyncio.sleep(1)
            
            log_step("🖱️  Clicking Next button", symbol="  ", indent=1)
            await handle_tool_call("click_element_by_index", {"index": 1})
            await asyncio.sleep(3)
            
            log_step("🔒 Entering password", symbol="  ", indent=1)
            await handle_tool_call("input_text", {
                "index": 0,
                "text": google_password
            })
            await asyncio.sleep(1)
            
            log_step("🖱️  Clicking Next button", symbol="  ", indent=1)
            await handle_tool_call("click_element_by_index", {"index": 1})
            await asyncio.sleep(5)
            
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
        response = await model_manager.generate_text(prompt)
        
        # Handle response - could be string or other format
        if isinstance(response, str):
            response_text = response
        elif isinstance(response, dict):
            response_text = response.get("text", "") or str(response)
        elif isinstance(response, list):
            response_text = response[0].get("text", "") if response and isinstance(response[0], dict) else str(response[0]) if response else ""
        else:
            response_text = str(response)
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # Try to parse JSON - handle cases with extra data
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            # If there's extra data, try to extract just the JSON object
            if "Extra data" in str(e):
                brace_start = response_text.find('{')
                if brace_start >= 0:
                    brace_count = 0
                    brace_end = -1
                    for i in range(brace_start, len(response_text)):
                        if response_text[i] == '{':
                            brace_count += 1
                        elif response_text[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                brace_end = i + 1
                                break
                    
                    if brace_end > brace_start:
                        json_text = response_text[brace_start:brace_end]
                        try:
                            result = json.loads(json_text)
                        except json.JSONDecodeError:
                            json_text = json_text.rstrip().rstrip(',').rstrip()
                            if json_text.endswith('}'):
                                result = json.loads(json_text)
                            else:
                                raise e
                    else:
                        raise e
                else:
                    raise e
            else:
                raise e
        
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
        q = re.sub(r'\s*Required question\s*', '', q, flags=re.IGNORECASE).strip()
        q = re.sub(r'\s*\d+\s*point\s*', '', q, flags=re.IGNORECASE).strip()
        
        if len(q) > 10 and '?' in q:
            questions_on_form.append(q)
    
    if len(questions_on_form) == 0:
        log_step("⚠️  No questions found in headings - trying alternative extraction...", symbol="⚠️", indent=1)
        
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


async def fill_text_field(question: str, answer: str, used_indices: List[int]) -> bool:
    """Fill a text input field"""
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    all_text_inputs = re.findall(r'\[(\d+)\]<input type=\'text\'>', elements_text)
    all_text_indices = [int(x) for x in all_text_inputs]
    unused_text_indices = [idx for idx in all_text_indices if idx not in used_indices]
    
    for idx in unused_text_indices:
        try:
            log_step(f"    👀 Watch browser - typing '{answer}'...", symbol="  ", indent=3)
            await handle_tool_call("input_text", {"index": idx, "text": answer})
            used_indices.append(idx)
            await asyncio.sleep(1.5)
            return True
        except Exception:
            continue
    
    return False


async def fill_radio_button(question: str, answer: str) -> bool:
    """Fill a radio button using JavaScript to find by data-value"""
    log_step(f"    🔘 Using JavaScript to find radio button with data-value='{answer}'...", symbol="  ", indent=3)
    
    session = await get_browser_session()
    page = await session.get_current_page()
    
    # JavaScript to find and click radio button by data-value
    js_code = f"""
    (async function() {{
        // Find the question heading
        const questionText = {json.dumps(question)};
        const answerValue = {json.dumps(answer)};
        
        // Find all headings (h3, h4, etc.) that contain the question text
        const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
        let targetHeading = null;
        
        for (const heading of headings) {{
            if (heading.textContent && heading.textContent.includes(questionText.split('?')[0])) {{
                targetHeading = heading;
                break;
            }}
        }}
        
        if (!targetHeading) {{
            return {{success: false, error: 'Question not found'}};
        }}
        
        // Find the radio button container (radiogroup) near this heading
        let radioGroup = null;
        let currentElement = targetHeading.parentElement;
        
        // Search in the same question container
        while (currentElement && currentElement !== document.body) {{
            const group = currentElement.querySelector('[role="radiogroup"]');
            if (group) {{
                radioGroup = group;
                break;
            }}
            currentElement = currentElement.parentElement;
        }}
        
        if (!radioGroup) {{
            // Fallback: search for radiogroup after the heading
            let nextSibling = targetHeading.parentElement.nextElementSibling;
            let searchCount = 0;
            while (nextSibling && searchCount < 5) {{
                const group = nextSibling.querySelector('[role="radiogroup"]');
                if (group) {{
                    radioGroup = group;
                    break;
                }}
                nextSibling = nextSibling.nextElementSibling;
                searchCount++;
            }}
        }}
        
        if (!radioGroup) {{
            return {{success: false, error: 'Radio group not found'}};
        }}
        
        // Find the radio button with matching data-value
        const radioButtons = radioGroup.querySelectorAll('[role="radio"][data-value]');
        for (const radio of radioButtons) {{
            if (radio.getAttribute('data-value') === answerValue) {{
                // Check if it's disabled
                if (radio.getAttribute('aria-disabled') === 'true') {{
                    return {{success: false, error: 'Radio button is disabled'}};
                }}
                
                // Click the radio button
                radio.click();
                
                // Wait a bit for the click to register
                await new Promise(resolve => setTimeout(resolve, 500));
                
                // Verify it was selected
                const isChecked = radio.getAttribute('aria-checked') === 'true';
                return {{
                    success: isChecked,
                    checked: isChecked,
                    dataValue: radio.getAttribute('data-value')
                }};
            }}
        }}
        
        return {{success: false, error: 'Radio button with matching data-value not found'}};
    }})();
    """
    
    try:
        # Execute JavaScript and wait for result
        result = await page.evaluate(js_code)
        
        # Wait a bit for the click to register
        await asyncio.sleep(1.0)
        
        if result and result.get("success"):
            log_step(f"    ✅✅✅ SUCCESS! Radio button '{answer}' clicked!", symbol="  ", indent=4)
            await asyncio.sleep(0.5)
            return True
        else:
            error_msg = result.get('error', 'Unknown error') if result else 'No result returned'
            log_step(f"    ⚠️  JavaScript result: {error_msg}", symbol="  ", indent=4)
            return False
    except Exception as e:
        error_str = str(e)
        log_step(f"    ❌ JavaScript execution failed: {error_str[:150]}...", symbol="  ", indent=4)
        import traceback
        log_step(f"    Full error: {traceback.format_exc()[:200]}...", symbol="  ", indent=5)
        return False


async def fill_dropdown(question: str, answer: str) -> bool:
    """Fill a dropdown using JavaScript to find by data-value"""
    log_step(f"    🎯 Using JavaScript to find dropdown option with data-value='{answer}'...", symbol="  ", indent=3)
    
    session = await get_browser_session()
    page = await session.get_current_page()
    
    # JavaScript to find and click dropdown option by data-value
    # Split into two steps: open dropdown, then select option
    js_find_and_open = f"""
    (function() {{
        const questionText = {json.dumps(question)};
        
        // Find the question heading
        const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
        let targetHeading = null;
        
        for (const heading of headings) {{
            if (heading.textContent && heading.textContent.includes(questionText.split('?')[0])) {{
                targetHeading = heading;
                break;
            }}
        }}
        
        if (!targetHeading) {{
            return {{success: false, error: 'Question not found'}};
        }}
        
        // Find the dropdown listbox near this heading
        let listbox = null;
        let currentElement = targetHeading.parentElement;
        
        while (currentElement && currentElement !== document.body) {{
            const box = currentElement.querySelector('[role="listbox"]');
            if (box) {{
                listbox = box;
                break;
            }}
            currentElement = currentElement.parentElement;
        }}
        
        if (!listbox) {{
            let nextSibling = targetHeading.parentElement.nextElementSibling;
            let searchCount = 0;
            while (nextSibling && searchCount < 5) {{
                const box = nextSibling.querySelector('[role="listbox"]');
                if (box) {{
                    listbox = box;
                    break;
                }}
                nextSibling = nextSibling.nextElementSibling;
                searchCount++;
            }}
        }}
        
        if (!listbox) {{
            return {{success: false, error: 'Dropdown listbox not found'}};
        }}
        
        // Click the dropdown to open it
        if (listbox.getAttribute('aria-expanded') === 'false') {{
            listbox.click();
        }}
        
        return {{success: true, listboxFound: true}};
    }})();
    """
    
    try:
        # Step 1: Open dropdown
        result1 = await page.evaluate(js_find_and_open)
        if not result1 or not result1.get("success"):
            error_msg = result1.get('error', 'Unknown error') if result1 else 'No result returned'
            log_step(f"    ⚠️  Failed to find/open dropdown: {error_msg}", symbol="  ", indent=4)
            return False
        
        # Wait for dropdown to open
        await asyncio.sleep(1.5)
        
        # Step 2: Select option
        js_select_option = f"""
        (function() {{
            const answerValue = {json.dumps(answer)};
            
            // Find all listboxes
            const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
            for (const listbox of listboxes) {{
                const options = listbox.querySelectorAll('[role="option"][data-value]');
                for (const option of options) {{
                    if (option.getAttribute('data-value') === answerValue) {{
                        if (option.getAttribute('aria-disabled') === 'true') {{
                            continue;
                        }}
                        
                        option.click();
                        return {{
                            success: true,
                            dataValue: option.getAttribute('data-value')
                        }};
                    }}
                }}
            }}
            
            return {{success: false, error: 'Option with matching data-value not found'}};
        }})();
        """
        
        result2 = await page.evaluate(js_select_option)
        await asyncio.sleep(1.0)
        
        if result2 and result2.get("success"):
            log_step(f"    ✅✅✅ SUCCESS! Dropdown option '{answer}' selected!", symbol="  ", indent=4)
            await asyncio.sleep(0.5)
            return True
        else:
            error_msg = result2.get('error', 'Unknown error') if result2 else 'No result returned'
            log_step(f"    ⚠️  Failed to select option: {error_msg}", symbol="  ", indent=4)
            return False
            
    except Exception as e:
        error_str = str(e)
        log_step(f"    ❌ JavaScript execution failed: {error_str[:150]}...", symbol="  ", indent=4)
        import traceback
        log_step(f"    Full error: {traceback.format_exc()[:200]}...", symbol="  ", indent=5)
        return False


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
        await asyncio.sleep(0.5)
    
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
        
        if await fill_text_field(question, answer, used_indices):
            filled_count += 1
            log_step(f"    ✅ Filled!", symbol="  ", indent=3)
        else:
            log_step(f"    ❌ Could not fill", symbol="  ", indent=3)
    
    # Fill radio buttons
    log_step("", symbol="")
    log_step("🔘 STARTING RADIO BUTTON FILLING", symbol="🔘")
    
    for qm_idx, qm in enumerate(radio_questions, 1):
        question = qm["question"]
        answer = qm["answer"]
        
        log_step("", symbol="")
        log_step(f"[RADIO {qm_idx}/{len(radio_questions)}] \"{question[:60]}...\"", symbol="  ", indent=1)
        log_step(f"    Expected Answer: '{answer}'", symbol="  ", indent=2)
        
        if await fill_radio_button(question, answer):
            filled_count += 1
        else:
            log_step(f"    ❌❌❌ CRITICAL: Radio button filling failed!", symbol="  ", indent=3)
    
    # Fill dropdowns
    log_step("", symbol="")
    log_step("🎯 STARTING DROPDOWN FILLING", symbol="🎯")
    
    for qm_idx, qm in enumerate(dropdown_questions, 1):
        question = qm["question"]
        answer = qm["answer"]
        
        log_step("", symbol="")
        log_step(f"[DROPDOWN {qm_idx}/{len(dropdown_questions)}] \"{question[:60]}...\"", symbol="  ", indent=1)
        log_step(f"    Expected Answer: '{answer}'", symbol="  ", indent=2)
        
        if await fill_dropdown(question, answer):
            filled_count += 1
        else:
            log_step(f"    ❌❌❌ CRITICAL: Dropdown filling failed!", symbol="  ", indent=3)
    
    log_step(f"✅ Filled {filled_count}/{len(questions_on_form)} fields", symbol="✅")
    
    return {qm["question"]: qm for qm in question_matches}


async def validate_completeness(question_matches: Dict[str, dict]) -> bool:
    """Validation 1: Check if all questions are answered"""
    log_section("VALIDATION 1: COMPLETENESS CHECK")
    log_step("🔍 Checking if all questions are answered...", symbol="🔍")
    
    await asyncio.sleep(2)
    
    session = await get_browser_session()
    page = await session.get_current_page()
    
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    current_page_text = md_result[0].get("text", "").lower() if md_result else ""
    
    all_answered = True
    answered_count = 0
    
    for question, qm in question_matches.items():
        expected_answer = qm["answer"]
        field_type = qm["field_type"]
        
        answer_found = False
        
        if field_type == "text":
            # Use JavaScript to check actual input field values
            js_check_text = f"""
            (function() {{
                const questionText = {json.dumps(question)};
                const expectedValue = {json.dumps(expected_answer)};
                
                // Find the question heading
                const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
                let targetHeading = null;
                for (const heading of headings) {{
                    if (heading.textContent && heading.textContent.includes(questionText.split('?')[0])) {{
                        targetHeading = heading;
                        break;
                    }}
                }}
                
                if (!targetHeading) return {{found: false}};
                
                // Find text input near this heading
                let inputField = null;
                let currentElement = targetHeading.parentElement;
                
                while (currentElement && currentElement !== document.body) {{
                    const input = currentElement.querySelector('input[type="text"]');
                    if (input) {{
                        inputField = input;
                        break;
                    }}
                    currentElement = currentElement.parentElement;
                }}
                
                if (!inputField) {{
                    let nextSibling = targetHeading.parentElement.nextElementSibling;
                    let searchCount = 0;
                    while (nextSibling && searchCount < 5) {{
                        const input = nextSibling.querySelector('input[type="text"]');
                        if (input) {{
                            inputField = input;
                            break;
                        }}
                        nextSibling = nextSibling.nextElementSibling;
                        searchCount++;
                    }}
                }}
                
                if (!inputField) return {{found: false}};
                
                const inputValue = inputField.value || '';
                // Check exact match or partial match for dates
                if (inputValue === expectedValue) {{
                    return {{found: true}};
                }}
                
                // For dates, try flexible matching
                if (expectedValue.includes('-')) {{
                    const dateParts = expectedValue.toLowerCase().split('-');
                    const inputLower = inputValue.toLowerCase();
                    if (dateParts.every(part => inputLower.includes(part))) {{
                        return {{found: true}};
                    }}
                }}
                
                return {{found: false}};
            }})();
            """
            try:
                result = await page.evaluate(js_check_text)
                answer_found = result.get("found", False) if result else False
            except Exception:
                # Fallback to markdown check
                answer_lower = expected_answer.lower()
                if answer_lower in current_page_text:
                    answer_found = True
                elif "-" in expected_answer:
                    date_formats = [
                        expected_answer.lower(),
                        expected_answer.replace("-", " ").lower(),
                        expected_answer.replace("-", "/").lower(),
                    ]
                    for fmt in date_formats:
                        if fmt in current_page_text:
                            answer_found = True
                            break
        
        elif field_type == "radio":
            # Use JavaScript to check if radio is checked
            js_check = f"""
            (function() {{
                const questionText = {json.dumps(question)};
                const answerValue = {json.dumps(expected_answer)};
                
                const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
                let targetHeading = null;
                for (const heading of headings) {{
                    if (heading.textContent && heading.textContent.includes(questionText.split('?')[0])) {{
                        targetHeading = heading;
                        break;
                    }}
                }}
                
                if (!targetHeading) return {{found: false}};
                
                let radioGroup = targetHeading.parentElement.querySelector('[role="radiogroup"]');
                if (!radioGroup) {{
                    let nextSibling = targetHeading.parentElement.nextElementSibling;
                    let searchCount = 0;
                    while (nextSibling && searchCount < 5) {{
                        const group = nextSibling.querySelector('[role="radiogroup"]');
                        if (group) {{
                            radioGroup = group;
                            break;
                        }}
                        nextSibling = nextSibling.nextElementSibling;
                        searchCount++;
                    }}
                }}
                
                if (!radioGroup) return {{found: false}};
                
                const radio = radioGroup.querySelector(`[role="radio"][data-value="${{answerValue}}"]`);
                if (radio && radio.getAttribute('aria-checked') === 'true') {{
                    return {{found: true}};
                }}
                return {{found: false}};
            }})();
            """
            try:
                result = await page.evaluate(js_check)
                answer_found = result.get("found", False) if result else False
            except Exception as e:
                log_step(f"    ⚠️  Radio validation JS failed: {str(e)[:50]}...", symbol="  ", indent=3)
                answer_found = expected_answer.lower() in current_page_text
        
        elif field_type == "dropdown":
            # Use JavaScript to check if dropdown is selected
            js_check = f"""
            (function() {{
                const questionText = {json.dumps(question)};
                const answerValue = {json.dumps(expected_answer)};
                
                const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
                let targetHeading = null;
                for (const heading of headings) {{
                    if (heading.textContent && heading.textContent.includes(questionText.split('?')[0])) {{
                        targetHeading = heading;
                        break;
                    }}
                }}
                
                if (!targetHeading) return {{found: false}};
                
                let listbox = targetHeading.parentElement.querySelector('[role="listbox"]');
                if (!listbox) {{
                    let nextSibling = targetHeading.parentElement.nextElementSibling;
                    let searchCount = 0;
                    while (nextSibling && searchCount < 5) {{
                        const box = nextSibling.querySelector('[role="listbox"]');
                        if (box) {{
                            listbox = box;
                            break;
                        }}
                        nextSibling = nextSibling.nextElementSibling;
                        searchCount++;
                    }}
                }}
                
                if (!listbox) return {{found: false}};
                
                // Check all options in the listbox
                const options = listbox.querySelectorAll('[role="option"][data-value]');
                for (const option of options) {{
                    if (option.getAttribute('data-value') === answerValue) {{
                        if (option.getAttribute('aria-selected') === 'true') {{
                            return {{found: true}};
                        }}
                    }}
                }}
                return {{found: false}};
            }})();
            """
            try:
                result = await page.evaluate(js_check)
                answer_found = result.get("found", False) if result else False
            except Exception as e:
                log_step(f"    ⚠️  Dropdown validation JS failed: {str(e)[:50]}...", symbol="  ", indent=3)
                answer_found = expected_answer.lower() in current_page_text
        
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
    
    return all_answered


async def validate_accuracy(question_matches: Dict[str, dict]) -> bool:
    """Validation 2: Check if all answers match INFO.md"""
    log_section("VALIDATION 2: ACCURACY CHECK")
    log_step("🔍 Checking if all answers match INFO.md...", symbol="🔍")
    
    await asyncio.sleep(2)
    
    session = await get_browser_session()
    page = await session.get_current_page()
    
    all_correct = True
    correct_count = 0
    
    for question, qm in question_matches.items():
        expected_answer = qm["answer"]
        field_type = qm["field_type"]
        
        is_correct = False
        
        if field_type == "text":
            md_result = await handle_tool_call("get_comprehensive_markdown", {})
            current_page_text = md_result[0].get("text", "").lower() if md_result else ""
            is_correct = expected_answer.lower() in current_page_text
        
        elif field_type == "radio":
            js_check = f"""
            (function() {{
                const questionText = {json.dumps(question)};
                const answerValue = {json.dumps(expected_answer)};
                
                const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
                let targetHeading = null;
                for (const heading of headings) {{
                    if (heading.textContent && heading.textContent.includes(questionText.split('?')[0])) {{
                        targetHeading = heading;
                        break;
                    }}
                }}
                
                if (!targetHeading) return {{correct: false}};
                
                let radioGroup = targetHeading.parentElement.querySelector('[role="radiogroup"]');
                if (!radioGroup) {{
                    let nextSibling = targetHeading.parentElement.nextElementSibling;
                    let searchCount = 0;
                    while (nextSibling && searchCount < 5) {{
                        const group = nextSibling.querySelector('[role="radiogroup"]');
                        if (group) {{
                            radioGroup = group;
                            break;
                        }}
                        nextSibling = nextSibling.nextElementSibling;
                        searchCount++;
                    }}
                }}
                
                if (!radioGroup) return {{correct: false}};
                
                const radio = radioGroup.querySelector(`[role="radio"][data-value="${{answerValue}}"]`);
                is_correct = radio && radio.getAttribute('aria-checked') === 'true';
                return {{correct: is_correct}};
            }})();
            """
            try:
                result = await page.evaluate(js_check)
                is_correct = result.get("correct", False)
            except Exception:
                is_correct = False
        
        elif field_type == "dropdown":
            js_check = f"""
            (function() {{
                const questionText = {json.dumps(question)};
                const answerValue = {json.dumps(expected_answer)};
                
                const headings = Array.from(document.querySelectorAll('h3, h4, [role="heading"]'));
                let targetHeading = null;
                for (const heading of headings) {{
                    if (heading.textContent && heading.textContent.includes(questionText.split('?')[0])) {{
                        targetHeading = heading;
                        break;
                    }}
                }}
                
                if (!targetHeading) return {{correct: false}};
                
                let listbox = targetHeading.parentElement.querySelector('[role="listbox"]');
                if (!listbox) {{
                    let nextSibling = targetHeading.parentElement.nextElementSibling;
                    let searchCount = 0;
                    while (nextSibling && searchCount < 5) {{
                        const box = nextSibling.querySelector('[role="listbox"]');
                        if (box) {{
                            listbox = box;
                            break;
                        }}
                        nextSibling = nextSibling.nextElementSibling;
                        searchCount++;
                    }}
                }}
                
                if (!listbox) return {{correct: false}};
                
                const option = listbox.querySelector(`[role="option"][data-value="${{answerValue}}"]`);
                is_correct = option && option.getAttribute('aria-selected') === 'true';
                return {{correct: is_correct}};
            }})();
            """
            try:
                result = await page.evaluate(js_check)
                is_correct = result.get("correct", False)
            except Exception:
                is_correct = False
        
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
    
    return all_correct


async def submit_form() -> bool:
    """Submit the form"""
    log_section("STEP 6: SUBMITTING FORM")
    
    log_step("🔍 Finding Submit button...", symbol="🔍")
    
    elem_result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    elements_text = elem_result[0].get("text", "") if elem_result else ""
    
    submit_match = re.search(r'\[(\d+)\]<span>Submit', elements_text)
    if submit_match:
        submit_idx = int(submit_match.group(1))
        log_step(f"   ✅ Found Submit button at index {submit_idx}", symbol="  ", indent=1)
        
        log_step("🖱️  Clicking Submit button...", symbol="🖱️", indent=1)
        log_step("   👀 Watch browser - form will be submitted now...", symbol="  ", indent=2)
        
        try:
            await handle_tool_call("click_element_by_index", {"index": submit_idx})
            await asyncio.sleep(3)
            log_step("✅ Submit button clicked!", symbol="✅", indent=1)
            return True
        except Exception as e:
            log_step(f"❌ Error clicking submit: {e}", symbol="❌", indent=1)
            return False
    else:
        log_step("⚠️  Could not find Submit button", symbol="⚠️")
        return False


async def fill_google_form(use_memory: bool = False):
    """Main function to fill Google Form with comprehensive validation"""
    
    log_section("GOOGLE FORM FILLER WITH VALIDATION")
    log_step(f"Target URL: {GOOGLE_FORM_URL}", symbol="🌐")
    
    if not use_memory:
        log_step("🔄 Memory bypassed - executing fresh (no old memory interference)", symbol="🔄")
    
    log_step("", symbol="")
    log_step("👀 IMPORTANT: Watch the browser window - all actions will be visible!", symbol="👀")
    
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
        await asyncio.sleep(4)
        log_step("   ✅ Form opened! Check your browser window.", symbol="  ", indent=1)
        
        # Step 2.5: Handle login
        login_success = await handle_google_login()
        if not login_success:
            log_step("⚠️  Login may have failed, but continuing...", symbol="⚠️")
        
        await asyncio.sleep(2)
        
        # Step 3: Clear form
        await clear_all_fields()
        
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
            return {"status": "validation_failed", "message": "Validation 1 (completeness) failed"}
        
        # Step 7: Validation 2 - Accuracy
        validation2_passed = await validate_accuracy(question_matches)
        
        if not validation2_passed:
            log_section("VALIDATION FAILED - EXECUTION STOPPED")
            log_step("", symbol="")
            log_step("❌❌❌ VALIDATION 2 (ACCURACY) FAILED", symbol="❌")
            log_step("", symbol="")
            log_step("🛑 EXECUTION STOPPED - Form will NOT be submitted", symbol="🛑")
            return {"status": "validation_failed", "message": "Validation 2 (accuracy) failed"}
        
        # Step 8: Submit form
        log_section("FINAL SUMMARY")
        log_step("✅ Validation 1 (Completeness): PASSED", symbol="✅")
        log_step("✅ Validation 2 (Accuracy): PASSED", symbol="✅")
        log_step("✅ Both validations passed - Submitting form!", symbol="✅")
        
        submit_success = await submit_form()
        
        if submit_success:
            log_section("SUCCESS - FORM SUBMITTED")
            log_step("🎉🎉🎉 FORM FILLING COMPLETED! 🎉🎉🎉", symbol="🎉")
            log_step("", symbol="")
            log_step("✅ All steps completed:", symbol="✅")
            log_step("   ✓ Form opened", symbol="  ", indent=1)
            log_step("   ✓ Form cleared", symbol="  ", indent=1)
            log_step("   ✓ All fields filled", symbol="  ", indent=1)
            log_step("   ✓ Validation 1 (Completeness) passed", symbol="  ", indent=1)
            log_step("   ✓ Validation 2 (Accuracy) passed", symbol="  ", indent=1)
            log_step("   ✓ Form submitted", symbol="  ", indent=1)
            log_step("", symbol="")
            return {"status": "success", "message": "Form filled and submitted successfully"}
        else:
            log_step("⚠️  Form submission may have failed - check browser", symbol="⚠️")
            return {"status": "partial_success", "message": "Form filled but submission may have failed"}
    
    except Exception as e:
        log_section("ERROR")
        log_step(f"❌ Error: {e}", symbol="❌")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


async def main():
    import sys
    
    use_memory = "--use-memory" in sys.argv
    fresh_mode = "--fresh" in sys.argv or not use_memory
    
    if fresh_mode:
        log_section("FRESH MODE ENABLED")
        log_step("🔄 Running in FRESH mode - memory will be bypassed", symbol="🔄")
        log_step("", symbol="")
    
    try:
        result = await fill_google_form(use_memory=use_memory)
        
        if result.get("status") == "success":
            log_section("COMPLETION - BROWSER STAYS OPEN")
            log_step("🎉 Form filling completed!", symbol="🎉")
            log_step("", symbol="")
            log_step("🌐 Browser will stay open for 10 minutes for review...", symbol="🌐")
            log_step("💡 Press Ctrl+C when done to close the browser", symbol="💡")
            log_step("", symbol="")
            
            try:
                for minute in range(10, 0, -1):
                    await asyncio.sleep(60)
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

