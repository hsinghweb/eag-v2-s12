"""
Memory Cleanup Utility

Clears old session logs and memory indexes to ensure fresh task execution.
Use this when you want to retry a task without old memory interfering.

Usage:
    python -m utils.clear_memory                    # Clear all memory
    python -m utils.clear_memory --recent           # Clear only recent sessions (last 7 days)
    python -m utils.clear_memory --date 2025-12-08  # Clear specific date
    python -m utils.clear_memory --keep-latest      # Keep only latest session
"""

import argparse
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import json

project_root = Path(__file__).parent.parent
MEMORY_BASE = project_root / "memory"
SESSION_LOGS = MEMORY_BASE / "session_logs"
INDEX_BASE = MEMORY_BASE / "session_summaries_index"
META_FILE = INDEX_BASE / ".index_meta.json"


def clear_all_memory():
    """Clear all session logs and indexes"""
    print("🧹 Clearing ALL memory...")
    
    # Clear session logs
    if SESSION_LOGS.exists():
        count = sum(1 for _ in SESSION_LOGS.rglob("*.json"))
        shutil.rmtree(SESSION_LOGS)
        SESSION_LOGS.mkdir(parents=True, exist_ok=True)
        print(f"   ✅ Cleared {count} session log files")
    
    # Clear indexes
    if INDEX_BASE.exists():
        index_files = list(INDEX_BASE.glob("*.json"))
        for index_file in index_files:
            index_file.unlink()
        print(f"   ✅ Cleared {len(index_files)} index files")
    
    # Clear metadata
    if META_FILE.exists():
        META_FILE.unlink()
        print(f"   ✅ Cleared metadata file")
    
    print("✅ All memory cleared!")


def clear_recent_memory(days=7):
    """Clear memory from recent days"""
    print(f"🧹 Clearing memory from last {days} days...")
    
    cutoff_date = datetime.now() - timedelta(days=days)
    cleared_count = 0
    
    if SESSION_LOGS.exists():
        for log_file in SESSION_LOGS.rglob("*.json"):
            try:
                # Extract date from path: memory/session_logs/YYYY/MM/DD/file.json
                parts = log_file.parts
                if len(parts) >= 4:
                    year = int(parts[-4])
                    month = int(parts[-3])
                    day = int(parts[-2])
                    file_date = datetime(year, month, day)
                    
                    if file_date >= cutoff_date:
                        log_file.unlink()
                        cleared_count += 1
            except (ValueError, IndexError):
                continue
    
    # Rebuild index after clearing
    if cleared_count > 0:
        print(f"   ✅ Cleared {cleared_count} recent session files")
        print("   🔄 Rebuilding index...")
        from memory.memory_indexer import build_or_update_index
        build_or_update_index()
        print("   ✅ Index rebuilt")
    else:
        print("   ℹ️  No recent files to clear")
    
    print("✅ Recent memory cleared!")


def clear_date_memory(target_date_str):
    """Clear memory from a specific date"""
    print(f"🧹 Clearing memory from {target_date_str}...")
    
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        year = target_date.year
        month = target_date.month
        day = target_date.day
        
        target_dir = SESSION_LOGS / str(year) / f"{month:02d}" / f"{day:02d}"
        
        if target_dir.exists():
            count = sum(1 for _ in target_dir.glob("*.json"))
            shutil.rmtree(target_dir)
            print(f"   ✅ Cleared {count} files from {target_date_str}")
            
            # Rebuild index
            print("   🔄 Rebuilding index...")
            from memory.memory_indexer import build_or_update_index
            build_or_update_index()
            print("   ✅ Index rebuilt")
        else:
            print(f"   ℹ️  No files found for {target_date_str}")
    except ValueError:
        print(f"   ❌ Invalid date format. Use YYYY-MM-DD")
        return
    
    print("✅ Date memory cleared!")


def keep_only_latest():
    """Keep only the most recent session, clear all others"""
    print("🧹 Keeping only latest session, clearing all others...")
    
    if not SESSION_LOGS.exists():
        print("   ℹ️  No session logs found")
        return
    
    # Find all session files with their modification times
    all_sessions = []
    for log_file in SESSION_LOGS.rglob("*.json"):
        try:
            mtime = log_file.stat().st_mtime
            all_sessions.append((mtime, log_file))
        except Exception:
            continue
    
    if not all_sessions:
        print("   ℹ️  No sessions found")
        return
    
    # Sort by modification time, keep the latest
    all_sessions.sort(key=lambda x: x[0], reverse=True)
    latest_file = all_sessions[0][1]
    
    # Clear all except latest
    cleared_count = 0
    for mtime, log_file in all_sessions[1:]:
        log_file.unlink()
        cleared_count += 1
    
    print(f"   ✅ Kept latest session: {latest_file.name}")
    print(f"   ✅ Cleared {cleared_count} older sessions")
    
    # Rebuild index
    print("   🔄 Rebuilding index...")
    from memory.memory_indexer import build_or_update_index
    build_or_update_index()
    print("   ✅ Index rebuilt")
    
    print("✅ Memory cleaned (latest kept)!")


def show_memory_stats():
    """Show current memory statistics"""
    print("\n📊 Memory Statistics:")
    print("=" * 60)
    
    if SESSION_LOGS.exists():
        session_files = list(SESSION_LOGS.rglob("*.json"))
        print(f"Total session files: {len(session_files)}")
        
        # Group by date
        dates = {}
        for log_file in session_files:
            try:
                parts = log_file.parts
                if len(parts) >= 4:
                    date_key = f"{parts[-4]}-{parts[-3]}-{parts[-2]}"
                    dates[date_key] = dates.get(date_key, 0) + 1
            except Exception:
                continue
        
        if dates:
            print("\nSessions by date:")
            for date_key in sorted(dates.keys(), reverse=True)[:10]:
                print(f"  {date_key}: {dates[date_key]} sessions")
            if len(dates) > 10:
                print(f"  ... and {len(dates) - 10} more dates")
    else:
        print("No session logs found")
    
    if INDEX_BASE.exists():
        index_files = list(INDEX_BASE.glob("*.json"))
        print(f"\nIndex files: {len(index_files)}")
        for index_file in index_files:
            size = index_file.stat().st_size
            print(f"  {index_file.name}: {size:,} bytes")
    else:
        print("\nNo index files found")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Clear memory to retry tasks fresh")
    parser.add_argument("--all", action="store_true", help="Clear all memory")
    parser.add_argument("--recent", action="store_true", help="Clear recent memory (last 7 days)")
    parser.add_argument("--days", type=int, default=7, help="Number of days for --recent (default: 7)")
    parser.add_argument("--date", type=str, help="Clear memory from specific date (YYYY-MM-DD)")
    parser.add_argument("--keep-latest", action="store_true", help="Keep only latest session")
    parser.add_argument("--stats", action="store_true", help="Show memory statistics only")
    
    args = parser.parse_args()
    
    if args.stats:
        show_memory_stats()
        return
    
    if args.all:
        response = input("⚠️  This will delete ALL memory. Are you sure? (yes/no): ")
        if response.lower() == "yes":
            clear_all_memory()
        else:
            print("❌ Cancelled")
    elif args.recent:
        clear_recent_memory(args.days)
    elif args.date:
        clear_date_memory(args.date)
    elif args.keep_latest:
        response = input("⚠️  This will delete all sessions except the latest. Continue? (yes/no): ")
        if response.lower() == "yes":
            keep_only_latest()
        else:
            print("❌ Cancelled")
    else:
        # Default: show stats and ask what to do
        show_memory_stats()
        print("\nOptions:")
        print("  --all          Clear all memory")
        print("  --recent       Clear recent memory (last 7 days)")
        print("  --date YYYY-MM-DD  Clear specific date")
        print("  --keep-latest  Keep only latest session")
        print("  --stats        Show statistics only")


if __name__ == "__main__":
    main()

