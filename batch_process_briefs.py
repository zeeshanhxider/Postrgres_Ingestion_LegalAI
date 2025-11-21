"""
Batch Brief Processor
Processes briefs from downloaded-briefs folder structure
Similar to batch_processor.py but adapted for briefs
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from sqlalchemy import create_engine

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.database import Database
from app.services.brief_ingestor import BriefIngestor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BriefBatchProcessor:
    """
    Batch processor for ingesting briefs from downloaded-briefs folder
    
    Expected structure:
    downloaded-briefs/
        2024-briefs/
            83895-4/
                762508_appellants_reply_brief_934.pdf
                ...
            69423-5/
                ...
        2023-briefs/
            ...
    """
    
    def __init__(self, db_connection_string: str):
        """Initialize batch processor with database connection"""
        self.db = Database(db_connection_string)
        self.brief_ingestor = BriefIngestor(self.db.engine)
        
        self.processed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.failed_files = []
    
    def process_briefs_directory(self, briefs_dir: str, year_filter: int = None):
        """
        Process all briefs in the directory
        
        Args:
            briefs_dir: Path to downloaded-briefs folder
            year_filter: Optional year to filter (e.g., 2024)
        """
        logger.info(f"🚀 Starting batch brief processing from: {briefs_dir}")
        logger.info(f"Year filter: {year_filter if year_filter else 'All years'}")
        
        start_time = datetime.now()
        briefs_path = Path(briefs_dir)
        
        if not briefs_path.exists():
            logger.error(f"❌ Briefs directory not found: {briefs_dir}")
            return
        
        # Find all year folders
        year_folders = []
        for item in briefs_path.iterdir():
            if item.is_dir() and item.name.endswith('-briefs'):
                year = int(item.name.split('-')[0])
                
                # Apply year filter if specified
                if year_filter and year != year_filter:
                    logger.info(f"⏭️ Skipping {item.name} (year filter: {year_filter})")
                    continue
                
                year_folders.append((year, item))
        
        if not year_folders:
            logger.warning(f"⚠️ No year folders found matching filter")
            return
        
        logger.info(f"📁 Found {len(year_folders)} year folders to process")
        
        # Process each year folder
        for year, year_folder in sorted(year_folders):
            logger.info(f"\n{'='*80}")
            logger.info(f"📅 Processing year: {year}")
            logger.info(f"{'='*80}\n")
            
            self._process_year_folder(year_folder, year)
        
        # Summary statistics
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 BATCH PROCESSING SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"✅ Successfully processed: {self.processed_count} briefs")
        logger.info(f"❌ Failed: {self.failed_count} briefs")
        logger.info(f"⏭️ Skipped: {self.skipped_count} briefs")
        logger.info(f"⏱️ Total duration: {duration:.2f} seconds")
        
        if self.processed_count > 0:
            avg_time = duration / self.processed_count
            logger.info(f"⏱️ Average time per brief: {avg_time:.2f} seconds")
        
        if self.failed_files:
            logger.info(f"\n❌ Failed files:")
            for file_path, error in self.failed_files:
                logger.info(f"   - {file_path}: {error}")
        
        logger.info(f"{'='*80}\n")
    
    def _process_year_folder(self, year_folder: Path, year: int):
        """Process all case folders in a year folder"""
        case_folders = [item for item in year_folder.iterdir() if item.is_dir()]
        
        logger.info(f"📂 Found {len(case_folders)} case folders in {year_folder.name}")
        
        for i, case_folder in enumerate(case_folders, 1):
            logger.info(f"\n[{i}/{len(case_folders)}] Processing case folder: {case_folder.name}")
            self._process_case_folder(case_folder, year)
    
    def _process_case_folder(self, case_folder: Path, year: int):
        """Process all PDF files in a case folder"""
        pdf_files = list(case_folder.glob("*.pdf"))
        
        if not pdf_files:
            logger.info(f"⚠️ No PDF files found in {case_folder.name}")
            self.skipped_count += 1
            return
        
        logger.info(f"📄 Found {len(pdf_files)} PDF files")
        
        for pdf_file in pdf_files:
            self._process_brief_file(pdf_file, year)
    
    def _process_brief_file(self, pdf_file: Path, year: int):
        """Process a single brief PDF file"""
        try:
            # Check if already processed
            if self._is_already_processed(pdf_file):
                logger.info(f"⏭️ Skipping already processed: {pdf_file.name}")
                self.skipped_count += 1
                return
            
            logger.info(f"\n{'─'*60}")
            logger.info(f"📝 Processing: {pdf_file.name}")
            logger.info(f"{'─'*60}")
            
            # Ingest brief
            result = self.brief_ingestor.ingest_pdf_brief(str(pdf_file), year=year)
            
            # Log results
            logger.info(f"\n✅ Brief processed successfully!")
            logger.info(f"   Brief ID: {result['brief_id']}")
            logger.info(f"   Case linked: {result['case_linked']} (case_id: {result.get('case_id', 'N/A')})")
            logger.info(f"   Chunks created: {result['chunks_created']}")
            logger.info(f"   Sentences: {result['sentences_processed']}")
            logger.info(f"   Words indexed: {result['words_indexed']}")
            logger.info(f"   Phrases: {result['phrases_extracted']}")
            logger.info(f"   TOA citations: {result['toa_citations']}")
            
            self.processed_count += 1
            
        except Exception as e:
            logger.error(f"❌ Failed to process {pdf_file.name}: {str(e)}")
            self.failed_count += 1
            self.failed_files.append((str(pdf_file), str(e)))
    
    def _is_already_processed(self, pdf_file: Path) -> bool:
        """Check if brief was already processed"""
        with self.db.connect() as conn:
            from sqlalchemy import text
            
            query = text("""
                SELECT brief_id FROM briefs
                WHERE source_file = :source_file
                LIMIT 1
            """)
            
            result = conn.execute(query, {'source_file': pdf_file.name})
            return result.fetchone() is not None


def main():
    """Main entry point for batch processing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch process briefs from downloaded-briefs folder')
    parser.add_argument('--briefs-dir', type=str, default='downloaded-briefs',
                      help='Path to briefs directory (default: downloaded-briefs)')
    parser.add_argument('--year', type=int, default=None,
                      help='Filter by year (e.g., 2024)')
    parser.add_argument('--db-url', type=str,
                      default=os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/cases_llama3.3'),
                      help='Database connection URL')
    parser.add_argument('--case-folder', type=str, default=None,
                      help='Process only specific case folder (e.g., 83895-4)')
    
    args = parser.parse_args()
    
    # Initialize processor
    processor = BriefBatchProcessor(args.db_url)
    
    # Process specific case folder or entire directory
    if args.case_folder:
        # Find the case folder
        briefs_path = Path(args.briefs_dir)
        case_path = None
        
        for year_folder in briefs_path.iterdir():
            if year_folder.is_dir() and year_folder.name.endswith('-briefs'):
                potential_path = year_folder / args.case_folder
                if potential_path.exists():
                    case_path = potential_path
                    year = int(year_folder.name.split('-')[0])
                    break
        
        if case_path:
            logger.info(f"🎯 Processing single case folder: {args.case_folder}")
            processor._process_case_folder(case_path, year)
            
            # Print summary
            logger.info(f"\n{'='*80}")
            logger.info(f"✅ Processed: {processor.processed_count} briefs")
            logger.info(f"❌ Failed: {processor.failed_count} briefs")
            logger.info(f"{'='*80}")
        else:
            logger.error(f"❌ Case folder not found: {args.case_folder}")
    else:
        # Process entire directory
        processor.process_briefs_directory(args.briefs_dir, year_filter=args.year)


if __name__ == "__main__":
    main()
