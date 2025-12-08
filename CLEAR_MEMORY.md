# Memory Cleanup Guide

If the agent is assuming tasks are already done due to old memory, use these methods to clean up and retry fresh.

## Quick Solutions

### Option 1: Run Form Filler in Fresh Mode (Recommended)
```bash
# Run without memory interference
python -m browser_agent.fill_form_with_validation --fresh

# Or explicitly bypass memory
python -m browser_agent.fill_form_with_validation
```

The form filler script now runs in **fresh mode by default**, bypassing memory search.

### Option 2: Clear Recent Memory
```bash
# Clear memory from last 7 days
python -m utils.clear_memory --recent

# Clear memory from last 3 days
python -m utils.clear_memory --recent --days 3
```

### Option 3: Clear Specific Date
```bash
# Clear memory from a specific date
python -m utils.clear_memory --date 2025-12-08
```

### Option 4: Clear All Memory (Nuclear Option)
```bash
# Clear everything - use with caution!
python -m utils.clear_memory --all
```

### Option 5: Keep Only Latest Session
```bash
# Keep only the most recent session, delete all others
python -m utils.clear_memory --keep-latest
```

## Check Memory Status

```bash
# See what's in memory
python -m utils.clear_memory --stats
```

## Why Memory Causes Issues

The agent uses memory search to:
1. Check if similar tasks were completed before
2. Skip tasks that seem already done (`original_goal_achieved`)
3. Use previous solutions as reference

If old memory says a task is done, the agent might skip it even if you want to retry.

## Recommended Workflow

1. **For form filling (recommended):**
   ```bash
   # Just run fresh - no memory needed
   python -m browser_agent.fill_form_with_validation
   ```

2. **If using main agent loop:**
   ```bash
   # Clear recent memory first
   python -m utils.clear_memory --recent
   
   # Then run your task
   python main.py
   ```

3. **For complete fresh start:**
   ```bash
   # Clear all memory
   python -m utils.clear_memory --all
   
   # Run task
   python main.py
   ```

## Memory Locations

- **Session Logs:** `memory/session_logs/YYYY/MM/DD/*.json`
- **Index Files:** `memory/session_summaries_index/*.json`
- **Metadata:** `memory/session_summaries_index/.index_meta.json`

## Notes

- The form filler (`fill_form_with_validation.py`) runs in **fresh mode by default**
- It doesn't use agent memory, so old memory won't interfere
- If you need memory for other tasks, use `--use-memory` flag
- Clearing memory doesn't affect browser sessions or form data

