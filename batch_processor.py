#!/usr/bin/env python3
"""
Legal Case Batch PDF Processor
Complete batch processing with AI extraction and comprehensive RAG capabilities.
Supports both directory-based and CSV metadata-based processing.
"""

import os
import sys
import logging
import csv
from pathlib import Path
from typing import Optional, Dict, Any, List
import argparse
from datetime import datetime
from dateutil import parser as date_parser

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.database import engine
from app.services.case_ingestor import LegalCaseIngestor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('batch_processing.log')
    ]
)

logger = logging.getLogger(__name__)

class BatchProcessor:
    """Legal case batch processor"""
    
    def __init__(self):
        self.engine = engine
        self.ingestor = LegalCaseIngestor(self.engine)
        self.processed_count = 0
        self.failed_count = 0
        self.start_time = None
    
    def process_pdf_file(self, pdf_path: Path) -> bool:
        """
        Process a single PDF file
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            True if successful, False if failed
        """
        try:
            logger.info(f"[FILE] Processing: {pdf_path.name}")
            
            # Read PDF content
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            
            # Prepare metadata
            metadata = {
                'case_number': pdf_path.stem,  # Use filename as case number
                'title': pdf_path.stem.replace('_', ' ').title(),
                'court_level': 'Appeals',  # Default for family law
                'division': 'Unknown',
                'publication': 'Unknown'
            }
            
            # Prepare source file info
            source_file_info = {
                'filename': pdf_path.name,
                'file_path': str(pdf_path.absolute())
            }
            
            # Process with case ingestor (using regex by default)
            result = self.ingestor.ingest_pdf_case(
                pdf_content=pdf_content,
                metadata=metadata,
                source_file_info=source_file_info,
                extraction_mode='regex'  # Fast regex extraction
            )
            
            # Log results
            logger.info(f"[OK] Successfully processed {pdf_path.name}")
            logger.info(f"   Case ID: {result['case_id']}")
            logger.info(f"   Extraction Mode: {result['extraction_mode']}")
            logger.info(f"   Chunks: {result['chunks_created']}")
            logger.info(f"   Words: {result['words_processed']} ({result['unique_words']} unique)")
            logger.info(f"   Phrases: {result['phrases_extracted']}")
            logger.info(f"   Entities: {sum(result['case_stats'].values())}")
            
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] Failed to process {pdf_path.name}: {str(e)}")
            return False
    
    def process_directory(self, pdf_dir: Path, limit: Optional[int] = None) -> None:
        """
        Process all PDF files in a directory
        
        Args:
            pdf_dir: Directory containing PDF files
            limit: Optional limit on number of files to process
        """
        # Find all PDF files
        pdf_files = list(pdf_dir.glob("*.pdf"))
        
        if not pdf_files:
            logger.error(f"No PDF files found in {pdf_dir}")
            return
        
        if limit:
            pdf_files = pdf_files[:limit]
        
        logger.info(f"[>>] Starting legal case batch processing")
        logger.info(f"[DIR] Source Directory: {pdf_dir}")
        logger.info(f"[FILES] Files to process: {len(pdf_files)}")
        logger.info(f"[MODE] Extraction: Regex (fast, free)")
        logger.info(f"[RAG] RAG Features: Full (chunks + words + phrases + embeddings)")
        
        self.start_time = datetime.now()
        
        # Process files
        for i, pdf_path in enumerate(pdf_files, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"[FILE] Processing PDF {i}/{len(pdf_files)}: {pdf_path.name}")
            logger.info(f"{'='*60}")
            
            success = self.process_pdf_file(pdf_path)
            
            if success:
                self.processed_count += 1
            else:
                self.failed_count += 1
            
            # Progress update
            elapsed = datetime.now() - self.start_time
            rate = i / elapsed.total_seconds() * 60 if elapsed.total_seconds() > 0 else 0
            
            logger.info(f"[STATS] Progress: {i}/{len(pdf_files)} files processed")
            logger.info(f"[OK] Success: {self.processed_count}, [FAIL] Failed: {self.failed_count}")
            logger.info(f"[TIME] Rate: {rate:.1f} files/minute")
        
        # Final summary
        self._print_final_summary(len(pdf_files))
    
    def _print_final_summary(self, total_files: int) -> None:
        """Print final processing summary"""
        elapsed = datetime.now() - self.start_time
        
        logger.info(f"\n{'='*60}")
        logger.info(f"[DONE] LEGAL CASE BATCH PROCESSING COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"[STATS] Total Files: {total_files}")
        logger.info(f"[OK] Successfully Processed: {self.processed_count}")
        logger.info(f"[FAIL] Failed: {self.failed_count}")
        logger.info(f"[RATE] Success Rate: {(self.processed_count/total_files*100):.1f}%")
        logger.info(f"[TIME] Total Time: {elapsed}")
        logger.info(f"[RATE] Average Rate: {self.processed_count/elapsed.total_seconds()*60:.1f} files/minute")
        logger.info(f"[LOG] Log File: batch_processing.log")

    def process_pdf_with_metadata(
        self, 
        pdf_path: Path, 
        row_metadata: Dict[str, Any],
        extraction_mode: str = 'regex'
    ) -> bool:
        """
        Process a single PDF file with pre-extracted metadata from CSV.
        
        Args:
            pdf_path: Path to PDF file
            row_metadata: Metadata from CSV row
            extraction_mode: 'regex' (fast), 'ai' (slow), or 'none'
            
        Returns:
            True if successful, False if failed
        """
        try:
            logger.info(f"[FILE] Processing: {pdf_path.name}")
            logger.info(f"   Case: {row_metadata.get('case_number')} - {row_metadata.get('case_title')}")
            
            # Read PDF content
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            
            # Parse file_date to proper date format
            file_date = None
            if row_metadata.get('file_date'):
                try:
                    file_date = date_parser.parse(row_metadata['file_date'])
                except Exception:
                    pass
            
            # Determine publication status from file_contains
            file_contains = row_metadata.get('file_contains', '')
            publication = 'Published'  # Default for court opinions
            if 'Unpublished' in file_contains:
                publication = 'Unpublished'
            
            # Prepare enriched metadata from CSV
            metadata = {
                'case_number': row_metadata.get('case_number', pdf_path.stem),
                'title': row_metadata.get('case_title', pdf_path.stem.replace('_', ' ').title()),
                'court_level': row_metadata.get('opinion_type', 'Unknown'),  # From metadata
                'division': row_metadata.get('division', ''),  # I, II, III from metadata
                'publication': publication,
                'file_date': file_date,
                'year': row_metadata.get('year'),
                'month': row_metadata.get('month'),
                'file_contains': file_contains,  # Majority, Concurring, Dissenting info
                'opinion_type': row_metadata.get('opinion_type', ''),  # Supreme Court, Court of Appeals
                'publication_status': row_metadata.get('publication_status', ''),  # Published, Published in Part
                'case_info_url': row_metadata.get('case_info_url', ''),  # Link to case info
                'pdf_url': row_metadata.get('pdf_url', ''),  # Link to PDF
            }
            
            # Prepare source file info with URLs
            source_file_info = {
                'filename': pdf_path.name,
                'file_path': str(pdf_path.absolute()),
                'source_url': row_metadata.get('pdf_url', ''),
                'case_info_url': row_metadata.get('case_info_url', ''),
            }
            
            # Process with case ingestor
            result = self.ingestor.ingest_pdf_case(
                pdf_content=pdf_content,
                metadata=metadata,
                source_file_info=source_file_info,
                extraction_mode=extraction_mode
            )
            
            # Log results
            logger.info(f"[OK] Successfully processed {row_metadata.get('case_number')}")
            logger.info(f"   Case ID: {result['case_id']}")
            logger.info(f"   Extraction Mode: {result['extraction_mode']}")
            logger.info(f"   Chunks: {result['chunks_created']}")
            logger.info(f"   Words: {result['words_processed']} ({result['unique_words']} unique)")
            logger.info(f"   Phrases: {result['phrases_extracted']}")
            logger.info(f"   Entities: {sum(result['case_stats'].values())}")
            
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] Failed to process {pdf_path.name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _find_pdf_path(self, row: Dict[str, Any], downloads_dir: Path) -> Optional[Path]:
        """
        Find the PDF file path based on CSV row metadata.
        PDFs are organized as: {csv_parent_dir}/{year}/{month}/{filename}
        where csv_parent_dir is the directory containing the metadata.csv
        
        Args:
            row: CSV row with metadata
            downloads_dir: Base downloads directory (passed from command line, usually just 'downloads')
            
        Returns:
            Path to PDF file or None if not found
        """
        year = str(row.get('year', ''))
        month = row.get('month', '')
        filename = row.get('pdf_filename', '')
        
        if not all([year, month, filename]):
            logger.warning(f"Missing path components: year={year}, month={month}, filename={filename}")
            return None
        
        # The actual PDFs are in the same directory as the CSV file, not in downloads_dir
        # We need to use self.csv_base_path which is set from the CSV file location
        # Try exact path: csv_base_path/{year}/{month}/{filename}
        pdf_path = self.csv_base_path / year / month / filename
        if pdf_path.exists():
            return pdf_path
        
        # Try with different month formats (e.g., "January" vs "Jan")
        year_dir = self.csv_base_path / year
        if year_dir.exists():
            for month_dir in year_dir.iterdir():
                if month_dir.is_dir() and month.lower().startswith(month_dir.name.lower()[:3]):
                    alt_path = month_dir / filename
                    if alt_path.exists():
                        return alt_path
        
        # Try finding by case number in filename
        case_number = row.get('case_number', '')
        if case_number and year_dir.exists():
            for month_dir in year_dir.iterdir():
                if month_dir.is_dir():
                    for pdf_file in month_dir.glob("*.pdf"):
                        if case_number.replace(',', '') in pdf_file.name.replace(',', ''):
                            return pdf_file
        
        logger.warning(f"PDF not found: {pdf_path}")
        return None

    def process_from_csv(
        self, 
        csv_path: Path, 
        downloads_dir: Path,
        limit: Optional[int] = None,
        skip_existing: bool = True,
        extraction_mode: str = 'regex'
    ) -> None:
        """
        Process cases from a metadata CSV file.
        
        Args:
            csv_path: Path to metadata.csv
            downloads_dir: Base directory where PDFs are downloaded (e.g., downloads/)
            limit: Optional limit on number of files to process
            skip_existing: Skip cases that are already in the database
        """
        logger.info(f"[CSV] Loading metadata from: {csv_path}")
        
        # Store the base path for PDFs (parent directory of CSV file)
        self.csv_base_path = csv_path.parent
        
        # Read CSV
        rows: List[Dict[str, Any]] = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Only process successfully downloaded files
                if row.get('download_status') == 'Success':
                    rows.append(row)
        
        if not rows:
            logger.error("No successfully downloaded cases found in CSV")
            return
        
        if limit:
            rows = rows[:limit]
        
        logger.info(f"[>>] Starting CSV-based batch processing")
        logger.info(f"[CSV] CSV File: {csv_path}")
        logger.info(f"[DIR] Downloads Directory: {downloads_dir}")
        logger.info(f"[FILES] Cases to process: {len(rows)}")
        logger.info(f"[MODE] Extraction Mode: {extraction_mode.upper()} {'(fast, free)' if extraction_mode == 'regex' else '(LLM-based)'}")
        logger.info(f"[RAG] RAG Features: Full (chunks + words + phrases + embeddings)")
        
        self.start_time = datetime.now()
        skipped_count = 0
        not_found_count = 0
        
        # Process each row
        for i, row in enumerate(rows, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"[FILE] Processing Case {i}/{len(rows)}: {row.get('case_number')} - {row.get('case_title', '')[:50]}")
            logger.info(f"{'='*60}")
            
            # Find PDF file
            pdf_path = self._find_pdf_path(row, downloads_dir)
            
            if not pdf_path:
                logger.warning(f"[SKIP] PDF not found for case {row.get('case_number')}, skipping")
                not_found_count += 1
                continue
            
            # TODO: Add skip_existing check against database here if needed
            
            # Process the PDF with enriched metadata
            success = self.process_pdf_with_metadata(pdf_path, row, extraction_mode)
            
            if success:
                self.processed_count += 1
            else:
                self.failed_count += 1
            
            # Progress update
            elapsed = datetime.now() - self.start_time
            rate = i / elapsed.total_seconds() * 60 if elapsed.total_seconds() > 0 else 0
            
            logger.info(f"[STATS] Progress: {i}/{len(rows)} cases processed")
            logger.info(f"[OK] Success: {self.processed_count}, [FAIL] Failed: {self.failed_count}, [SKIP] Not Found: {not_found_count}")
            logger.info(f"[TIME] Rate: {rate:.1f} cases/minute")
        
        # Final summary
        self._print_csv_summary(len(rows), not_found_count, skipped_count)

    def _print_csv_summary(self, total_cases: int, not_found: int, skipped: int) -> None:
        """Print final CSV processing summary"""
        elapsed = datetime.now() - self.start_time
        
        logger.info(f"\n{'='*60}")
        logger.info(f"[DONE] CSV BATCH PROCESSING COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"[STATS] Total Cases in CSV: {total_cases}")
        logger.info(f"[OK] Successfully Processed: {self.processed_count}")
        logger.info(f"[FAIL] Failed: {self.failed_count}")
        logger.info(f"[SKIP] PDFs Not Found: {not_found}")
        logger.info(f"[SKIP] Skipped (existing): {skipped}")
        logger.info(f"[RATE] Success Rate: {(self.processed_count/(total_cases-not_found-skipped)*100):.1f}%" if (total_cases-not_found-skipped) > 0 else "N/A")
        logger.info(f"[TIME] Total Time: {elapsed}")
        if self.processed_count > 0:
            logger.info(f"[RATE] Average Rate: {self.processed_count/elapsed.total_seconds()*60:.1f} cases/minute")
        logger.info(f"[LOG] Log File: batch_processing.log")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Legal Case PDF Batch Processor')
    
    # Create subcommands for different modes
    subparsers = parser.add_subparsers(dest='mode', help='Processing mode')
    
    # Directory mode (original)
    dir_parser = subparsers.add_parser('directory', help='Process all PDFs in a directory')
    dir_parser.add_argument('pdf_directory', help='Directory containing PDF files')
    dir_parser.add_argument('--limit', type=int, help='Limit number of files to process')
    
    # CSV mode (new)
    csv_parser = subparsers.add_parser('csv', help='Process PDFs based on metadata CSV')
    csv_parser.add_argument('csv_file', help='Path to metadata.csv file')
    csv_parser.add_argument('--downloads-dir', default='downloads', help='Base directory for downloaded PDFs (default: downloads)')
    csv_parser.add_argument('--limit', type=int, help='Limit number of cases to process')
    csv_parser.add_argument('--no-skip-existing', action='store_true', help='Process even if case exists in database')
    csv_parser.add_argument('--extraction-mode', choices=['regex', 'ai'], default='regex',
                           help='Extraction mode: regex (fast, free) or ai (LLM-based, slow). Default: regex')
    
    # Global options
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create processor
    processor = BatchProcessor()
    
    if args.mode == 'directory':
        # Original directory-based processing
        pdf_dir = Path(args.pdf_directory)
        if not pdf_dir.exists():
            logger.error(f"Directory does not exist: {pdf_dir}")
            sys.exit(1)
        if not pdf_dir.is_dir():
            logger.error(f"Path is not a directory: {pdf_dir}")
            sys.exit(1)
        processor.process_directory(pdf_dir, args.limit)
        
    elif args.mode == 'csv':
        # New CSV-based processing
        csv_path = Path(args.csv_file)
        if not csv_path.exists():
            logger.error(f"CSV file does not exist: {csv_path}")
            sys.exit(1)
        
        downloads_dir = Path(args.downloads_dir)
        if not downloads_dir.exists():
            logger.error(f"Downloads directory does not exist: {downloads_dir}")
            sys.exit(1)
        
        processor.process_from_csv(
            csv_path=csv_path,
            downloads_dir=downloads_dir,
            limit=args.limit,
            skip_existing=not args.no_skip_existing,
            extraction_mode=args.extraction_mode
        )
    else:
        # No mode specified, show help
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
