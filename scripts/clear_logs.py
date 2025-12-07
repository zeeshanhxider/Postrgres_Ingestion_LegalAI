#!/usr/bin/env python3
"""
Clear Logs Script
Clears all log files from the logs directory and root directory.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

def clear_logs(confirm: bool = True):
    """Clear all log files"""
    
    # Get project root
    project_root = Path(__file__).parent.parent
    logs_dir = project_root / "logs"
    
    # Find all log files
    log_files = []
    
    # Logs in logs/ directory
    if logs_dir.exists():
        log_files.extend(logs_dir.glob("*.log"))
    
    # Logs in root directory
    log_files.extend(project_root.glob("*.log"))
    
    if not log_files:
        print("✅ No log files found to clear.")
        return
    
    print(f"\n📋 Found {len(log_files)} log files:")
    print("-" * 60)
    
    total_size = 0
    for log_file in sorted(log_files):
        size = log_file.stat().st_size
        total_size += size
        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} bytes"
        rel_path = log_file.relative_to(project_root)
        print(f"  {rel_path} ({size_str})")
    
    print("-" * 60)
    print(f"Total size: {total_size / 1024 / 1024:.2f} MB")
    print()
    
    if confirm:
        response = input("🗑️  Delete all log files? [y/N]: ").strip().lower()
        if response != 'y':
            print("❌ Cancelled.")
            return
    
    # Delete files
    deleted = 0
    for log_file in log_files:
        try:
            log_file.unlink()
            deleted += 1
            print(f"  ✅ Deleted: {log_file.name}")
        except Exception as e:
            print(f"  ❌ Failed to delete {log_file.name}: {e}")
    
    print()
    print(f"✅ Deleted {deleted}/{len(log_files)} log files.")


def main():
    """Main entry point"""
    # Check for --force flag
    force = "--force" in sys.argv or "-f" in sys.argv
    
    print("="*60)
    print("CLEAR LOGS SCRIPT")
    print("="*60)
    
    clear_logs(confirm=not force)


if __name__ == "__main__":
    main()
