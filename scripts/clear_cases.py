#!/usr/bin/env python3
"""
Clear all case-related data from the database.
This script clears cases and related tables while preserving briefs data.

Usage:
    python scripts/clear_cases.py
    python scripts/clear_cases.py --dry-run  # Show what would be deleted without deleting
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database import engine


# Tables to clear (in order - respects foreign key constraints)
# Junction/child tables first, then parent tables
CASE_TABLES = [
    # Junction tables (depend on cases)
    "case_judges",
    "case_chunks", 
    "case_phrases",
    "case_sentences",
    "statute_citations",
    "citation_edges",
    "issue_chunks",
    "issues_decisions",
    "word_occurrence",
    "embeddings",
    # Parent tables
    "parties",
    "judges",
    "cases",
]

# Tables to NEVER touch (briefs-related)
PROTECTED_TABLES = [
    "briefs",
    "brief_arguments",
    "brief_chunks",
    "brief_citations",
    "brief_phrases",
    "brief_sentences",
    "brief_word_occurrence",
    "arguments",
    "attorneys",
]


def get_table_counts(conn) -> dict:
    """Get row counts for all case-related tables."""
    counts = {}
    for table in CASE_TABLES:
        try:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = result.scalar()
        except Exception as e:
            counts[table] = f"ERROR: {e}"
    return counts


def clear_cases(dry_run: bool = False):
    """Clear all case-related data from the database."""
    
    with engine.connect() as conn:
        # Show current state
        print("=" * 60)
        print("CURRENT TABLE COUNTS (case-related)")
        print("=" * 60)
        
        counts = get_table_counts(conn)
        total_rows = 0
        for table, count in counts.items():
            if isinstance(count, int):
                total_rows += count
                print(f"  {table}: {count:,}")
            else:
                print(f"  {table}: {count}")
        
        print(f"\nTotal rows to delete: {total_rows:,}")
        print("-" * 60)
        
        if dry_run:
            print("\n[DRY RUN] No changes made. Run without --dry-run to delete.")
            return
        
        if total_rows == 0:
            print("\nDatabase is already clean. Nothing to delete.")
            return
        
        # Confirm deletion
        print("\n⚠️  This will DELETE all case data (briefs will be preserved).")
        confirm = input("Type 'yes' to confirm: ")
        
        if confirm.lower() != 'yes':
            print("Aborted.")
            return
        
        # Clear tables in order
        print("\nClearing tables...")
        # Commit any existing transaction first
        conn.commit()
        
        try:
            for table in CASE_TABLES:
                try:
                    conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    print(f"  [OK] {table} cleared")
                except Exception as e:
                    print(f"  [FAIL] {table}: {e}")
            
            conn.commit()
            print("\n" + "=" * 60)
            print("[SUCCESS] All case data cleared successfully!")
            print("=" * 60)
            
            # Verify
            print("\nVerifying...")
            counts = get_table_counts(conn)
            all_clear = all(c == 0 for c in counts.values() if isinstance(c, int))
            
            if all_clear:
                print("[OK] All tables confirmed empty.")
            else:
                print("[WARN] Some tables still have data:")
                for table, count in counts.items():
                    if isinstance(count, int) and count > 0:
                        print(f"  {table}: {count}")
                        
        except Exception as e:
            conn.rollback()
            print(f"\n[ERROR] {e}")
            print("Transaction rolled back.")
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Clear all case-related data from the database (preserves briefs)"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    
    args = parser.parse_args()
    clear_cases(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
