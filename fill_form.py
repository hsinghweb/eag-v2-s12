#!/usr/bin/env python3
"""
Simple runner to fill the Google Form
Usage: python fill_form.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import the form filler
from browser_agent.test_browser_agent import main

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Google Form Filler - Automated Submission")
    print("="*60)
    print("\nThis script will:")
    print("  1. Open the Google Form")
    print("  2. Fill all fields with data from INFO.md")
    print("  3. Submit the form automatically")
    print("\nUsing BREAKTHROUGH solution for dropdown:")
    print("  → Typing into hidden input field (not clicking UI)")
    print("="*60 + "\n")
    
    exit_code = asyncio.run(main())
    
    if exit_code == 0:
        print("\n" + "="*60)
        print("✅ SUCCESS! Form has been submitted.")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ There was an issue. Check the output above.")
        print("="*60)
    
    sys.exit(exit_code)

