"""
Diagnose Form Structure - See what indices map to what questions
"""

import asyncio
import sys
import json
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from browserMCP.mcp_tools import handle_tool_call
from browserMCP.mcp_utils.utils import stop_browser_session


async def diagnose():
    print("=" * 60)
    print("FORM STRUCTURE DIAGNOSIS")
    print("=" * 60)
    
    # Navigate to form
    print("\n[1] Opening form...")
    await handle_tool_call("open_tab", {"url": "https://forms.gle/6Nc6QaaJyDvePxLv7"})
    await asyncio.sleep(4)
    
    # Get interactive elements (non-structured to see raw indices)
    print("\n[2] Getting interactive elements...")
    result = await handle_tool_call("get_interactive_elements", {
        "viewport_mode": "all",
        "structured_output": False
    })
    
    if result:
        text = result[0].get("text", "")
        print("\nInteractive elements (raw):")
        print("-" * 60)
        print(text[:4000])
        print("-" * 60)
    
    # Also get markdown view
    print("\n[3] Page content (markdown):")
    md_result = await handle_tool_call("get_comprehensive_markdown", {})
    if md_result:
        md_text = md_result[0].get("text", "")[:3000]
        print(md_text)


async def main():
    try:
        await diagnose()
    finally:
        print("\n[CLEANUP]")
        await stop_browser_session()


if __name__ == "__main__":
    asyncio.run(main())

