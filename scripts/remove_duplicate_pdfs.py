"""
Remove duplicate PDF files from downloaded-briefs folder.

This script identifies and removes duplicate PDFs based on file content (hash).
When duplicates are found, it keeps the file with the shortest name and removes the others.

Example duplicates:
- 860721_Appellant_Reply_1901.pdf (REMOVE)
- 860721_Appellant_Reply_2751.pdf (REMOVE)
- 860721_Appellant_Reply.pdf (KEEP - shortest name)
"""

import os
import hashlib
from pathlib import Path
from collections import defaultdict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Error hashing {file_path}: {e}")
        return None


def find_and_remove_duplicates(briefs_dir: str, dry_run: bool = True):
    """
    Find and remove duplicate PDF files
    
    Args:
        briefs_dir: Path to downloaded-briefs folder
        dry_run: If True, only report what would be deleted without actually deleting
    """
    briefs_path = Path(briefs_dir)
    
    if not briefs_path.exists():
        logger.error(f"Directory not found: {briefs_dir}")
        return
    
    logger.info(f"{'DRY RUN - ' if dry_run else ''}Scanning for duplicate PDFs in: {briefs_dir}")
    logger.info("="*80)
    
    # Dictionary to store: hash -> list of file paths
    hash_to_files = defaultdict(list)
    
    total_files = 0
    total_duplicates = 0
    total_size_saved = 0
    
    # Scan all PDF files
    logger.info("Step 1: Scanning all PDF files and calculating hashes...")
    for year_folder in briefs_path.iterdir():
        if not year_folder.is_dir() or not year_folder.name.endswith('-briefs'):
            continue
            
        logger.info(f"Scanning {year_folder.name}...")
        
        for case_folder in year_folder.iterdir():
            if not case_folder.is_dir():
                continue
                
            for pdf_file in case_folder.glob("*.pdf"):
                total_files += 1
                file_hash = calculate_file_hash(pdf_file)
                
                if file_hash:
                    hash_to_files[file_hash].append(pdf_file)
                
                if total_files % 100 == 0:
                    logger.info(f"  Processed {total_files} files...")
    
    logger.info(f"\nStep 2: Analyzing duplicates...")
    logger.info(f"Total PDF files scanned: {total_files}")
    logger.info(f"Unique files (by content): {len(hash_to_files)}")
    
    # Find and remove duplicates
    logger.info(f"\nStep 3: {'Identifying' if dry_run else 'Removing'} duplicate files...")
    logger.info("="*80)
    
    for file_hash, files in hash_to_files.items():
        if len(files) > 1:
            # Sort by filename length (keep shortest) and then alphabetically
            files.sort(key=lambda f: (len(f.name), f.name))
            
            keep_file = files[0]
            duplicate_files = files[1:]
            
            logger.info(f"\n🔍 Found {len(duplicate_files)} duplicate(s):")
            logger.info(f"   ✅ KEEP: {keep_file}")
            
            for dup_file in duplicate_files:
                file_size = dup_file.stat().st_size
                total_duplicates += 1
                total_size_saved += file_size
                
                if dry_run:
                    logger.info(f"   ❌ WOULD DELETE: {dup_file} ({file_size / 1024:.1f} KB)")
                else:
                    try:
                        dup_file.unlink()
                        logger.info(f"   ❌ DELETED: {dup_file} ({file_size / 1024:.1f} KB)")
                    except Exception as e:
                        logger.error(f"   ⚠️  ERROR deleting {dup_file}: {e}")
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("📊 SUMMARY")
    logger.info("="*80)
    logger.info(f"Total files scanned: {total_files}")
    logger.info(f"Unique files: {len(hash_to_files)}")
    logger.info(f"Duplicate files {'identified' if dry_run else 'removed'}: {total_duplicates}")
    logger.info(f"Space {'that would be saved' if dry_run else 'saved'}: {total_size_saved / (1024*1024):.2f} MB")
    
    if dry_run:
        logger.info("\n⚠️  This was a DRY RUN - no files were deleted")
        logger.info("To actually delete duplicates, run with dry_run=False")
    else:
        logger.info("\n✅ Duplicate removal complete!")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Remove duplicate PDF files from downloaded-briefs')
    parser.add_argument('--briefs-dir', type=str, default='downloaded-briefs',
                      help='Path to briefs directory (default: downloaded-briefs)')
    parser.add_argument('--execute', action='store_true',
                      help='Actually delete duplicates (default is dry-run only)')
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if not dry_run:
        logger.warning("\n⚠️  WARNING: You are about to DELETE duplicate files!")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Aborted by user")
            return
    
    find_and_remove_duplicates(args.briefs_dir, dry_run=dry_run)


if __name__ == "__main__":
    main()
