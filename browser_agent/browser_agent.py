"""
BrowserAgent: A standalone agent for web interaction tasks.

Takes 1 instruction from Perception and can execute N internal steps
until the task succeeds. Specialized for form filling, navigation,
and UI-intensive browser workflows.
"""

import os
import json
import uuid
import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List, Dict
from dataclasses import dataclass, asdict

from agent.model_manager import ModelManager
from utils.utils import log_step, log_error, log_json_block
from utils.json_parser import parse_llm_json

# Import browser tools
from browserMCP.mcp_tools import handle_tool_call, get_tools
from browserMCP.mcp_utils.utils import get_browser_session, stop_browser_session

# Google login detection patterns
GOOGLE_LOGIN_PATTERNS = [
    "accounts.google.com/signin",
    "accounts.google.com/v3/signin",
    "accounts.google.com/ServiceLogin",
    "accounts.google.com/o/oauth2",
]


@dataclass
class BrowserAgentSnapshot:
    """Snapshot of a BrowserAgent execution"""
    run_id: str
    instruction: str
    steps_executed: List[Dict[str, Any]]
    final_status: str  # "success" | "failed" | "max_steps_reached"
    final_message: str
    total_steps: int
    timestamp: str
    error: Optional[str] = None


@dataclass 
class BrowserStep:
    """A single step in the browser agent's execution"""
    step_number: int
    action: str
    action_params: Dict[str, Any]
    reasoning: str
    result: Optional[str] = None
    success: bool = False
    timestamp: str = ""


class BrowserAgent:
    """
    Standalone Browser Agent for UI-intensive tasks.
    
    Takes a single instruction and autonomously executes multiple browser
    actions until the task is complete or max steps is reached.
    
    Design Pattern: Similar to Summarizer/Decision agents
    - Single entry point (run)
    - Uses LLM for planning each step
    - Executes browser tools directly
    - Maintains internal loop until success
    """
    
    def __init__(
        self, 
        prompt_path: str,
        max_steps: int = 15,
        api_key: Optional[str] = None
    ):
        self.prompt_path = prompt_path
        self.max_steps = max_steps
        self.model = ModelManager()
        self.snapshots: List[BrowserAgentSnapshot] = []
        
        # Load Google credentials from environment
        self.google_email = os.getenv("GOOGLE_EMAIL")
        self.google_password = os.getenv("GOOGLE_PASSWORD")
    
    async def _check_google_login_required(self) -> bool:
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
    
    async def _handle_google_login(self) -> bool:
        """
        Handle Google login if credentials are available in environment.
        Returns True if login was successful or not needed.
        """
        if not await self._check_google_login_required():
            return True  # No login needed
        
        log_step("[AUTH] Google login page detected...", symbol="!")
        
        # Check if credentials are available
        if not self.google_email or not self.google_password:
            log_step("[AUTH] No Google credentials in .env file.", symbol="!")
            log_step("[AUTH] Please either:", symbol="!")
            log_step("[AUTH]   1. Run: python -m browser_agent.setup_google_login", symbol="!")
            log_step("[AUTH]   2. Add GOOGLE_EMAIL and GOOGLE_PASSWORD to .env", symbol="!")
            log_step("[AUTH] Waiting 30 seconds for manual login...", symbol="!")
            
            # Wait for manual login
            for i in range(30):
                await asyncio.sleep(1)
                if not await self._check_google_login_required():
                    log_step("[AUTH] Login detected! Continuing...", symbol="+")
                    return True
            
            log_step("[AUTH] Login timeout. Continuing anyway...", symbol="!")
            return False
        
        try:
            log_step("[AUTH] Attempting auto-login with credentials from .env...", symbol="->")
            
            # Wait for page to load
            await asyncio.sleep(2)
            
            # Enter email
            await handle_tool_call("input_text", {
                "index": 0,  # Usually the first input is email
                "text": self.google_email
            })
            await asyncio.sleep(1)
            
            # Click Next button
            await handle_tool_call("click_element_by_index", {"index": 1})
            await asyncio.sleep(3)
            
            # Enter password
            await handle_tool_call("input_text", {
                "index": 0,  # Password field
                "text": self.google_password
            })
            await asyncio.sleep(1)
            
            # Click Next button
            await handle_tool_call("click_element_by_index", {"index": 1})
            await asyncio.sleep(5)
            
            # Check if login was successful
            if not await self._check_google_login_required():
                log_step("[AUTH] Login successful!", symbol="+")
                return True
            else:
                log_step("[AUTH] Login may have failed. Check browser for verification.", symbol="!")
                return False
                
        except Exception as e:
            log_error(f"[AUTH] Error during Google login: {e}")
            return False
        
    async def run(
        self, 
        instruction: str,
        session: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Main entry point - takes 1 instruction, executes N steps internally.
        
        Args:
            instruction: The task to accomplish (e.g., "Fill the form at URL X")
            session: Optional AgentSession for logging
            
        Returns:
            Dict with status, message, and execution details
        """
        run_id = str(uuid.uuid4())
        steps_executed: List[Dict[str, Any]] = []
        
        log_step(f"[BROWSER] BrowserAgent starting: {instruction[:100]}...", symbol="->")
        
        # Step 1: Navigate to URL if instruction contains one
        url = self._extract_url(instruction)
        if url:
            log_step(f"[NAV] Navigating to: {url}")
            nav_result = await self._execute_browser_action("open_tab", {"url": url})
            steps_executed.append({
                "step": 0,
                "action": "open_tab",
                "params": {"url": url},
                "result": nav_result,
                "reasoning": "Initial navigation to target URL"
            })
            await asyncio.sleep(2)  # Wait for page to load
            
            # Check for Google login requirement
            await self._handle_google_login()
            await asyncio.sleep(1)  # Wait after login handling
        
        # Step 2: Main execution loop
        current_step = 1
        task_complete = False
        final_message = ""
        
        while current_step <= self.max_steps and not task_complete:
            log_step(f"[STEP] Step {current_step}/{self.max_steps}", symbol="*")
            
            # Get current page state
            page_state = await self._get_page_state()
            
            # Ask LLM what to do next
            next_action = await self._plan_next_action(
                instruction=instruction,
                page_state=page_state,
                steps_executed=steps_executed,
                current_step=current_step
            )
            
            if next_action.get("error"):
                log_error(f"Planning error: {next_action['error']}")
                break
                
            action_name = next_action.get("action", "")
            action_params = next_action.get("params", {})
            reasoning = next_action.get("reasoning", "")
            
            log_step(f"[ACTION] Action: {action_name} | Reasoning: {reasoning[:80]}...")
            
            # Check if task is marked as complete
            if action_name == "done" or next_action.get("task_complete", False):
                task_complete = True
                final_message = next_action.get("message", "Task completed successfully")
                steps_executed.append({
                    "step": current_step,
                    "action": "done",
                    "params": {},
                    "result": final_message,
                    "reasoning": reasoning,
                    "success": True
                })
                break
            
            # Execute the action
            result = await self._execute_browser_action(action_name, action_params)
            
            success = "[OK]" in result or "success" in result.lower() or not result.startswith("[ERROR]")
            
            steps_executed.append({
                "step": current_step,
                "action": action_name,
                "params": action_params,
                "result": result[:500] if result else "",  # Truncate long results
                "reasoning": reasoning,
                "success": success
            })
            
            log_step(f"{'[OK]' if success else '[FAIL]'} Result: {result[:100]}...")
            
            # Small delay between actions
            await asyncio.sleep(1)
            current_step += 1
        
        # Determine final status
        if task_complete:
            status = "success"
        elif current_step > self.max_steps:
            status = "max_steps_reached"
            final_message = f"Reached maximum steps ({self.max_steps})"
        else:
            status = "failed"
            final_message = "Task did not complete"
        
        # Create snapshot
        snapshot = BrowserAgentSnapshot(
            run_id=run_id,
            instruction=instruction,
            steps_executed=steps_executed,
            final_status=status,
            final_message=final_message,
            total_steps=len(steps_executed),
            timestamp=datetime.utcnow().isoformat()
        )
        self.snapshots.append(snapshot)
        
        log_step(f"[DONE] BrowserAgent finished: {status} - {final_message}", symbol="<-")
        
        return {
            "status": status,
            "message": final_message,
            "steps_executed": len(steps_executed),
            "run_id": run_id,
            "details": asdict(snapshot)
        }
    
    async def _get_page_state(self) -> str:
        """Get current page state using interactive elements with structured output"""
        try:
            # Get interactive elements with structured output (includes IDs)
            result = await handle_tool_call("get_interactive_elements", {
                "viewport_mode": "all",
                "strict_mode": False,
                "structured_output": True
            })
            
            if result and len(result) > 0:
                elements_json = result[0].get("text", "{}")
                
                # Also get a brief page summary for context
                markdown_result = await handle_tool_call("get_comprehensive_markdown", {})
                markdown_text = ""
                if markdown_result and len(markdown_result) > 0:
                    markdown_text = markdown_result[0].get("text", "")[:3000]  # Limit markdown
                
                # Combine both for a complete picture
                return f"""## Page Content Summary
{markdown_text}

## Interactive Elements (with IDs for actions)
{elements_json}
"""
        except Exception as e:
            log_error(f"Error getting page state: {e}")
        return "Unable to get page state"
    
    async def _plan_next_action(
        self,
        instruction: str,
        page_state: str,
        steps_executed: List[Dict],
        current_step: int
    ) -> Dict[str, Any]:
        """Use LLM to plan the next browser action"""
        
        # Track which indices have been interacted with
        filled_indices = set()
        clicked_indices = set()
        filled_values = {}  # Track what was filled
        for s in steps_executed:
            params = s.get('params', {})
            idx = params.get('index')
            if s['action'] == 'input_text' and idx is not None:
                filled_indices.add(idx)
                filled_values[idx] = params.get('text', '')[:30]
            elif s['action'] in ['click_element_by_index', 'select_dropdown_option'] and idx is not None:
                clicked_indices.add(idx)
        
        # Check for success indicators in page state (very specific to avoid false positives)
        success_indicators = ["your response has been recorded", "thanks for submitting", "response submitted successfully"]
        page_lower = page_state.lower()
        # Only trigger if we've executed at least 5 steps (form filling takes multiple steps)
        if len(steps_executed) >= 5 and any(indicator in page_lower for indicator in success_indicators):
            return {
                "action": "done",
                "params": {"success": True, "message": "Form submitted successfully - confirmation detected"},
                "reasoning": "Detected success confirmation in page state",
                "task_complete": True
            }
        
        # Detect if we're on ACTUAL Google login page (accounts.google.com URL)
        # NOT just a page that shows "Sign in to Google" button
        is_login_page = "accounts.google.com" in page_lower and "identifier" in page_lower
        
        # Build simple steps list
        recent_steps = steps_executed[-5:] if len(steps_executed) > 5 else steps_executed
        steps_list = [f"{s['action']}(idx={s.get('params',{}).get('index')})" for s in recent_steps]
        
        # Truncate page state - focus on form elements
        truncated_page_state = page_state[:3500] if len(page_state) > 3500 else page_state
        
        if is_login_page:
            # Skip login page - session should be pre-logged-in
            # Just mark as done or wait
            log_step("[INFO] Login page detected - session should already be logged in")
            return {
                "action": "done",
                "params": {},
                "reasoning": "Login page appeared but session should be pre-authenticated. Run setup_login.py first.",
                "task_complete": False,
                "error": "Login required - run: python -m browser_agent.setup_login"
            }
        else:
            # Regular form filling prompt - more explicit about avoiding repeats
            full_prompt = f"""Fill Google Form. Return ONE JSON action.

TASK: {instruction[:800]}

PAGE:
{truncated_page_state}

=== CRITICAL: ALREADY FILLED (SKIP THESE INDICES) ===
{filled_indices if filled_indices else 'None'}
Values filled: {filled_values if filled_values else 'None'}

Recent actions: {steps_list}
Step {current_step}/{self.max_steps}

RULES:
1. DO NOT use indices {list(filled_indices)} - already filled!
2. For Yes/No questions: click_element_by_index on the radio button
3. For dropdowns: use select_dropdown_option
4. For text fields: use input_text
5. After all fields filled: click_element_by_index on Submit button
6. If form complete: return {{"action":"done","params":{{}},"reasoning":"complete"}}

Return JSON (one action only):
{{"action": "ACTION", "params": {{"index": N, "text": "VALUE"}}, "reasoning": "brief"}}

JSON:"""
        
        try:
            time.sleep(1)  # Rate limiting
            response = await self.model.generate_text(prompt=full_prompt)
            
            # Parse the LLM response
            output = parse_llm_json(
                response, 
                required_keys=["action", "params", "reasoning"]
            )
            
            # Validate - don't re-fill already filled indices
            if output.get("action") == "input_text":
                proposed_idx = output.get("params", {}).get("index")
                if proposed_idx in filled_indices:
                    log_step(f"[WARN] LLM tried to re-fill index {proposed_idx}, skipping...")
                    # Force it to look for submit button instead
                    return {
                        "action": "click_element_by_index",
                        "params": {"index": 0},  # Try first clickable
                        "reasoning": "All text fields filled, looking for submit"
                    }
            
            return output
            
        except Exception as e:
            log_error(f"LLM planning error: {e}")
            return {"error": str(e)}
    
    async def _execute_browser_action(self, action: str, params: Dict) -> str:
        """Execute a browser action using mcp_tools"""
        try:
            result = await handle_tool_call(action, params)
            if result and len(result) > 0:
                return result[0].get("text", "Action completed")
            return "Action completed (no output)"
        except Exception as e:
            return f"[ERROR] Error: {str(e)}"
    
    def _extract_url(self, instruction: str) -> Optional[str]:
        """Extract URL from instruction if present"""
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        matches = re.findall(url_pattern, instruction)
        return matches[0] if matches else None
    
    def _get_tools_summary(self) -> str:
        """Get a summary of available browser tools"""
        return """
- open_tab(url): Open URL in new tab
- go_to_url(url): Navigate current tab to URL
- click_element_by_index(index): Click element by its index number
- input_text(index, text): Type text into input field at index
- send_keys(keys): Send keyboard keys (Enter, Tab, etc.)
- scroll_down(pixels): Scroll down the page
- scroll_up(pixels): Scroll up the page
- get_dropdown_options(index): Get options from dropdown
- select_dropdown_option(index, option_text): Select dropdown option
- get_interactive_elements(): Get list of interactive elements
- get_comprehensive_markdown(): Get page content as markdown
- take_screenshot(): Take screenshot of current page
- done(success, message): Mark task as complete
"""

    def get_snapshots(self) -> List[BrowserAgentSnapshot]:
        """Get all execution snapshots"""
        return self.snapshots


# Convenience function for standalone testing
async def run_browser_agent(instruction: str, max_steps: int = 15) -> Dict[str, Any]:
    """
    Convenience function to run BrowserAgent standalone.
    
    Usage:
        result = await run_browser_agent("Go to https://forms.gle/xxx and fill the form")
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / "browser_agent_prompt.txt"
    agent = BrowserAgent(prompt_path=str(prompt_path), max_steps=max_steps)
    return await agent.run(instruction)

