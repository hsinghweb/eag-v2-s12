# LLM-Based Dynamic Form Filler

## 🎯 Overview

This is an **intelligent, adaptive form filler** that uses LLMs to dynamically match form questions with answers from `INFO.md`. It handles forms with questions in **any order** and automatically determines field types.

## ✨ Key Features

### 1. **Dynamic Question Matching**
- Extracts actual questions from the form
- Uses LLM to match each question with the correct answer
- No hardcoded field order or indices

### 2. **Automatic Field Type Detection**
- LLM determines if a field is:
  - `text` (name, email, date, etc.)
  - `radio` (Yes/No, multiple choice)
  - `dropdown` (select lists)

### 3. **Breakthrough Dropdown Solution**
- Types directly into hidden input fields
- Bypasses problematic Google Forms dropdown UI
- Works reliably every time

### 4. **Model Agnostic**
- Uses your configured LLM (Gemini, OpenAI, Groq, Ollama)
- Configured via `config/profiles.yaml`
- Fallback to simple matching if LLM fails

## 🚀 How It Works

### Step-by-Step Process

```
1. Load INFO.md → Parse Q&A pairs
2. Open form → Extract all questions (lines ending with ?)
3. For each question:
   ↓
   Ask LLM: "Match this question to INFO.md"
   ↓
   LLM returns: {answer, field_type, confidence}
   ↓
   Fill field using appropriate method
4. Submit form
5. Verify success
```

### LLM Prompt Template

```
You are helping to fill a Google Form.

INFO.md content:
{info_content}

Form Question:
"{question_text}"

Task:
1. Find the most relevant answer from INFO.md
2. Determine field type (text|radio|dropdown)
3. Rate confidence (high|medium|low)

Respond with JSON:
{
    "answer": "...",
    "field_type": "...",
    "confidence": "...",
    "reasoning": "..."
}
```

## 📋 Field Handling

### Text Fields
```python
# LLM determines: field_type = "text"
await handle_tool_call("input_text", {
    "index": text_input_index,
    "text": answer
})
```

### Radio Buttons
```python
# LLM determines: field_type = "radio"
# Find button with matching answer text
radio_match = re.search(rf'\[(\d+)\]<div[^>]*>{answer}<', elements)
await handle_tool_call("click_element_by_index", {"index": radio_idx})
```

### Dropdowns (Breakthrough!)
```python
# LLM determines: field_type = "dropdown"
# Type into hidden input field
await handle_tool_call("input_text", {
    "index": hidden_input_index,
    "text": answer
})
```

## 🔧 Configuration

### Set Your LLM in `config/profiles.yaml`

```yaml
llm:
  text_generation: "gemini-2.0-flash"  # or openai-gpt4, groq-llama, etc.
```

### Available Models (from `config/models.json`)

- **Gemini**: `gemini-2.0-flash`, `gemini-1.5-pro`
- **OpenAI**: `gpt-4o-mini`, `gpt-4o`
- **Groq**: `llama-3.1-8b-instant`
- **Ollama**: Local models

### Environment Variables

```env
# Choose one based on your LLM:
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
```

## 💡 Advantages Over Static Approach

| Feature | Static Approach | **LLM-Based Approach** |
|---------|----------------|----------------------|
| Question Order | ❌ Fixed | ✅ Any order |
| New Questions | ❌ Breaks | ✅ Adapts |
| Field Type | ❌ Hardcoded | ✅ Auto-detected |
| Fuzzy Matching | ❌ No | ✅ Yes |
| Confidence | ❌ No | ✅ High/Medium/Low |
| Form Changes | ❌ Breaks | ✅ Still works |

## 📊 Example Output

```
============================================================
[BROWSER] Google Form Filler - LLM-Based Dynamic Approach
============================================================
Target: https://forms.gle/6Nc6QaaJyDvePxLv7
  Using LLM: gemini - gemini-2.0-flash

[INFO.md] Loaded data:
  What is the name of your Master?... → Himanshu Singh
  What is his/her Date of Birth?... → 17-Dec-1984
  ...

[STEP 1] Opening form...

[STEP 2] Extracting questions from form...
  Found 6 questions on form:
    1. What is his/her email id?
    2. What is the name of your Master?
    3. What is his/her Date of Birth?
    4. What course is he/her in?
    5. Is he/she married?
    6. Which course is he/she taking?

[STEP 3] Using LLM to match questions with answers...

  Question: "What is his/her email id?"
    LLM Match: himanshu.kumar.singh@gmail.com (text, high)
    Reasoning: Email question matches email field in INFO.md

  Question: "What is the name of your Master?"
    LLM Match: Himanshu Singh (text, high)
    Reasoning: Master name question directly matches INFO.md

  Question: "What is his/her Date of Birth?"
    LLM Match: 17-Dec-1984 (text, high)
    Reasoning: DOB question matches date field

  Question: "What course is he/her in?"
    LLM Match: EAG (text, high)
    Reasoning: Course question matches EAG

  Question: "Is he/she married?"
    LLM Match: Yes (radio, high)
    Reasoning: Yes/No question indicates radio button

  Question: "Which course is he/she taking?"
    LLM Match: EAG (dropdown, high)
    Reasoning: "Which" suggests dropdown selection

[STEP 4] Getting form elements...
  Text input indices: [0, 1, 2, 3, 5]

[STEP 5] Filling form fields dynamically...

  [TEXT] What is his/her email id?...
    Answer: himanshu.kumar.singh@gmail.com
    Using text input index 0

  [TEXT] What is the name of your Master?...
    Answer: Himanshu Singh
    Using text input index 1

  [TEXT] What is his/her Date of Birth?...
    Answer: 17-Dec-1984
    Using text input index 2

  [TEXT] What course is he/her in?...
    Answer: EAG
    Using text input index 3

  [RADIO] Is he/she married?...
    Answer: Yes
    Clicking radio button 'Yes' at index 4

  [DROPDOWN] Which course is he/she taking?...
    Answer: EAG
    Using breakthrough method: typing into hidden input field
    Found dropdown hidden input at index 5
    Typing 'EAG' into hidden dropdown input...

[STEP 6] Submitting form...
  Clicking Submit at index 10

[STEP 7] Verifying submission...

============================================================
✓ FORM SUBMITTED SUCCESSFULLY!
============================================================
```

## 🎯 Why This Is Better

### Problem with Static Approach
```python
# ❌ Breaks if form changes
answers = {
    "email": info_data.get("What is his/her email id?"),
    "master": info_data.get("What is the name of your Master?"),
    # ... hardcoded mapping
}
```

### LLM-Based Solution
```python
# ✅ Adapts to any form
for question in questions_on_form:
    match = await match_question_with_llm(question, info_content)
    # Automatically finds correct answer and field type
```

## 🔍 LLM Matching Intelligence

The LLM can handle:

- **Exact matches**: "What is his/her email id?" → email field
- **Fuzzy matches**: "Enter your master's name" → name field
- **Synonyms**: "Marital status" → married field
- **Context**: "Which course are you taking?" → dropdown (not text)

## 🛠️ Fallback Mechanism

If LLM fails:
```python
# Simple keyword matching
for q, a in info_data.items():
    if any(word in question_lower for word in q.lower().split()[:3]):
        return {"answer": a, "field_type": "text", "confidence": "low"}
```

## 🚀 Usage

### Method 1: Standalone
```bash
python fill_form.py
```

### Method 2: Interactive
```bash
python main.py
# Type: fill form
```

### Method 3: Direct
```bash
python -m browser_agent.test_browser_agent
```

## 📝 Requirements

- Configured LLM in `config/profiles.yaml`
- API key in `.env` file
- `INFO.md` with question-answer pairs
- Browser automation running (browserMCP)

## 🎓 Key Learnings

1. **LLMs enable true dynamic automation**
   - Not just pattern matching
   - Semantic understanding

2. **Hidden fields are the key**
   - Dropdowns have hidden `<input>` elements
   - Typing into them bypasses UI complexity

3. **Confidence scoring helps debugging**
   - High: LLM is sure
   - Medium: Might need verification
   - Low: Used fallback

4. **Model-agnostic design**
   - Works with any LLM
   - No vendor lock-in

## 🔮 Future Enhancements

- [ ] Multi-turn LLM conversations for complex forms
- [ ] Visual field recognition (OCR)
- [ ] Learning from user corrections
- [ ] Support for conditional fields
- [ ] File upload handling

## 🏆 Conclusion

This LLM-based approach represents a **paradigm shift** in form automation:

- From **static** to **dynamic**
- From **fragile** to **robust**
- From **specific** to **general**

It can handle forms with questions in any order, new questions, and even slight variations in wording. Combined with the breakthrough dropdown solution, it provides reliable, intelligent form filling.

