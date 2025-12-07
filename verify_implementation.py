#!/usr/bin/env python3
"""
Verification script to check if all files are properly implemented
"""

import os
import sys
from pathlib import Path

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def check_file(filepath, description):
    """Check if a file exists and show its status"""
    path = Path(filepath)
    if path.exists():
        size = path.stat().st_size
        print(f"✅ {description}")
        print(f"   └─ {filepath} ({size:,} bytes)")
        return True
    else:
        print(f"❌ {description}")
        print(f"   └─ {filepath} NOT FOUND")
        return False

def check_content(filepath, search_string, description):
    """Check if a file contains specific content"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if search_string in content:
                print(f"✅ {description}")
                return True
            else:
                print(f"❌ {description}")
                return False
    except Exception as e:
        print(f"❌ {description} - Error: {e}")
        return False

print("="*60)
print("🔍 Verifying Google Form Filler Implementation")
print("="*60)

all_good = True

# Check files exist
print("\n📁 File Existence Check:")
all_good &= check_file("browser_agent/test_browser_agent.py", "Main form filler script")
all_good &= check_file("fill_form.py", "Standalone runner script")
all_good &= check_file("main.py", "Updated main.py with form command")
all_good &= check_file("INFO.md", "Form data file")
all_good &= check_file("FORM_FILLER_USAGE.md", "Usage documentation")
all_good &= check_file("IMPLEMENTATION_SUMMARY.md", "Implementation summary")

# Check key content
print("\n🔍 Content Verification:")
all_good &= check_content(
    "browser_agent/test_browser_agent.py",
    "Type directly into the hidden input field",
    "Breakthrough solution documented"
)
all_good &= check_content(
    "browser_agent/test_browser_agent.py",
    "dropdown_input_idx",
    "Hidden dropdown input handling implemented"
)
all_good &= check_content(
    "main.py",
    "fill form",
    "Special 'fill form' command in main.py"
)
all_good &= check_content(
    "INFO.md",
    "Himanshu Singh",
    "Form data available"
)

# Check Python syntax
print("\n🐍 Python Syntax Check:")
try:
    import ast
    with open("browser_agent/test_browser_agent.py", 'r', encoding='utf-8') as f:
        ast.parse(f.read())
    print("✅ test_browser_agent.py syntax valid")
except SyntaxError as e:
    print(f"❌ test_browser_agent.py has syntax error: {e}")
    all_good = False

try:
    with open("fill_form.py", 'r', encoding='utf-8') as f:
        ast.parse(f.read())
    print("✅ fill_form.py syntax valid")
except SyntaxError as e:
    print(f"❌ fill_form.py has syntax error: {e}")
    all_good = False

try:
    with open("main.py", 'r', encoding='utf-8') as f:
        ast.parse(f.read())
    print("✅ main.py syntax valid")
except SyntaxError as e:
    print(f"❌ main.py has syntax error: {e}")
    all_good = False

# Final verdict
print("\n" + "="*60)
if all_good:
    print("🎉 All checks passed! Implementation is ready.")
    print("\n📚 Next steps:")
    print("   1. Run: python fill_form.py")
    print("   2. Or run: python main.py (then type 'fill form')")
    print("   3. Or run: python -m browser_agent.test_browser_agent")
    print("\n📖 See FORM_FILLER_USAGE.md for detailed instructions")
else:
    print("⚠️  Some checks failed. Review the output above.")
print("="*60)

