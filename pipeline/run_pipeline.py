#!/usr/bin/env python
"""
Run Pipeline - CLI entry point for the case ingestion pipeline.

Usage:
    # Process a single case
    python -m pipeline.run_pipeline --pdf path/to/case.pdf --csv path/to/metadata.csv --row 21
    
    # Process a batch
    python -m pipeline.run_pipeline --batch --pdf-dir downloads/Supreme_Court_Opinions --csv downloads/Supreme_Court_Opinions/metadata.csv
    
    # Control RAG options
    python -m pipeline.run_pipeline --pdf path/to/case.pdf --chunk-embeddings important --phrase-filter relaxed
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import Config
from pipeline.case_processor import CaseProcessor
from pipeline.db_inserter import DatabaseInserter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_single_case(args):
    """Process a single PDF file."""
    logger.info(f"Processing single case: {args.pdf}")
    
    # Load metadata if provided
    metadata_row = None
    if args.csv and args.row is not None:
        processor = CaseProcessor()
        metadata_map = processor.load_metadata_csv(args.csv)
        
        # Find by row number (1-indexed in the CSV means index in the list)
        csv_rows = list(metadata_map.values())
        if 0 < args.row <= len(csv_rows):
            # Get by case_number key
            keys = list(metadata_map.keys())
            if args.row <= len(keys):
                case_key = keys[args.row - 1]
                metadata_row = metadata_map[case_key]
                logger.info(f"Using metadata for case: {case_key}")
        else:
            logger.warning(f"Row {args.row} not found in CSV, processing without metadata")
    
    # Process the case
    processor = CaseProcessor()
    case = processor.process_case(args.pdf, metadata_row)
    
    if not case.extraction_successful:
        logger.error(f"Extraction failed: {case.error_message}")
        return None
    
    # Insert into database
    db_url = Config.get_database_url()
    inserter = DatabaseInserter.from_url(db_url, enable_rag=args.enable_rag)
    
    # Configure RAG options
    if args.enable_rag:
        inserter.configure_rag(
            chunk_embedding_mode=args.chunk_embeddings,
            phrase_filter_mode=args.phrase_filter
        )
    
    case_id = inserter.insert_case(case)
    
    if case_id:
        logger.info(f"Successfully inserted case with ID: {case_id}")
        print(f"\n✓ Case {case_id} inserted successfully")
        print(f"  Title: {case.metadata.case_title if case.metadata else 'Unknown'}")
        print(f"  Parties: {len(case.parties)}")
        print(f"  Judges: {len(case.judges)}")
        print(f"  Citations: {len(case.citations)}")
        print(f"  Issues: {len(case.issues)}")
        if args.enable_rag:
            print(f"  RAG processing: enabled (chunks={args.chunk_embeddings}, phrases={args.phrase_filter})")
    else:
        logger.error("Insert failed")
        print("\n✗ Insert failed - check logs")
    
    return case_id


def process_batch(args):
    """Process a batch of PDF files."""
    logger.info(f"Processing batch from: {args.pdf_dir}")
    
    processor = CaseProcessor()
    cases = processor.process_batch(
        pdf_dir=args.pdf_dir,
        metadata_csv=args.csv,
        limit=args.limit
    )
    
    # Insert all successful cases
    db_url = Config.get_database_url()
    inserter = DatabaseInserter.from_url(db_url, enable_rag=args.enable_rag)
    
    # Configure RAG options
    if args.enable_rag:
        inserter.configure_rag(
            chunk_embedding_mode=args.chunk_embeddings,
            phrase_filter_mode=args.phrase_filter
        )
    
    successful = [c for c in cases if c.extraction_successful]
    results = inserter.insert_batch(successful)
    
    print(f"\n{'='*50}")
    print(f"Batch Processing Complete")
    print(f"{'='*50}")
    print(f"  Total PDFs: {len(cases)}")
    print(f"  Extracted: {len(successful)}")
    print(f"  Inserted: {results['success']}")
    print(f"  Failed: {results['failed']}")
    if args.enable_rag:
        print(f"  RAG mode: chunks={args.chunk_embeddings}, phrases={args.phrase_filter}")
    
    return results


def verify_case(args):
    """Verify all columns for a specific case."""
    from sqlalchemy import create_engine, text
    
    db_url = Config.get_database_url()
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Get case data
        result = conn.execute(text("""
            SELECT 
                case_id, title, court_level, court, district, county,
                docket_number, source_docket_number, trial_judge,
                appeal_published_date, published, summary,
                source_url, case_info_url,
                overall_case_outcome, appeal_outcome,
                winner_legal_role, winner_personal_role,
                opinion_type, publication_status,
                decision_year, decision_month,
                case_type, source_file, source_file_path,
                court_id, case_type_id, stage_type_id,
                extraction_timestamp, processing_status,
                LENGTH(full_text) as text_length,
                CASE WHEN full_embedding IS NOT NULL THEN 1024 ELSE 0 END as embedding_dim
            FROM cases WHERE case_id = :case_id
        """), {'case_id': args.case_id})
        
        row = result.fetchone()
        
        if not row:
            print(f"Case {args.case_id} not found")
            return
        
        print(f"\n{'='*60}")
        print(f"Case {args.case_id} Verification")
        print(f"{'='*60}")
        
        # Display all columns
        columns = result.keys()
        for col, val in zip(columns, row):
            if val is not None:
                print(f"  ✓ {col}: {val}")
            else:
                print(f"  ○ {col}: NULL")
        
        # Get related entity counts
        counts = {}
        for table, id_col in [
            ('parties', 'case_id'),
            ('attorneys', 'case_id'),
            ('case_judges', 'case_id'),
            ('citation_edges', 'source_case_id'),
            ('statute_citations', 'case_id'),
            ('issues_decisions', 'case_id'),
            ('case_chunks', 'case_id'),
            ('case_sentences', 'chunk_id'),
            ('case_phrases', 'case_id'),
        ]:
            try:
                if table == 'case_sentences':
                    q = text("""
                        SELECT COUNT(*) FROM case_sentences cs
                        JOIN case_chunks cc ON cs.chunk_id = cc.id
                        WHERE cc.case_id = :case_id
                    """)
                else:
                    q = text(f"SELECT COUNT(*) FROM {table} WHERE {id_col} = :case_id")
                count = conn.execute(q, {'case_id': args.case_id}).scalar()
                counts[table] = count
            except:
                counts[table] = "N/A"
        
        print(f"\n{'='*60}")
        print("Related Entities")
        print(f"{'='*60}")
        for table, count in counts.items():
            print(f"  {table}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description='Legal Case Ingestion Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process single case
  python -m pipeline.run_pipeline --pdf downloads/Supreme_Court_Opinions/123456.pdf --csv downloads/Supreme_Court_Opinions/metadata.csv --row 21

  # Process batch (first 10 cases)
  python -m pipeline.run_pipeline --batch --pdf-dir downloads/Supreme_Court_Opinions --limit 10

  # Process with custom RAG settings
  python -m pipeline.run_pipeline --pdf case.pdf --chunk-embeddings important --phrase-filter relaxed

  # Verify case insertion
  python -m pipeline.run_pipeline --verify --case-id 21
        """
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--batch', action='store_true', help='Process batch of PDFs')
    mode_group.add_argument('--verify', action='store_true', help='Verify case data')
    
    # Input arguments
    parser.add_argument('--pdf', type=str, help='Path to single PDF file')
    parser.add_argument('--pdf-dir', type=str, help='Directory with PDF files (for batch)')
    parser.add_argument('--csv', type=str, help='Path to metadata CSV')
    parser.add_argument('--row', type=int, help='Row number in CSV (1-indexed)')
    parser.add_argument('--limit', type=int, help='Limit number of files in batch')
    parser.add_argument('--case-id', type=int, help='Case ID for verification')
    
    # RAG options
    parser.add_argument(
        '--enable-rag', 
        action='store_true', 
        default=True,
        help='Enable RAG processing (default: True)'
    )
    parser.add_argument(
        '--no-rag',
        action='store_true',
        help='Disable RAG processing (insert case only)'
    )
    parser.add_argument(
        '--chunk-embeddings',
        type=str,
        choices=['all', 'important', 'none'],
        default='all',
        help='Chunk embedding mode: all (default), important (ANALYSIS/HOLDING/FACTS only), none'
    )
    parser.add_argument(
        '--phrase-filter',
        type=str,
        choices=['strict', 'relaxed'],
        default='strict',
        help='Phrase filtering mode: strict (legal terms only, default), relaxed (all meaningful phrases)'
    )
    
    args = parser.parse_args()
    
    # Handle --no-rag flag
    if args.no_rag:
        args.enable_rag = False
    
    # Route to appropriate handler
    if args.verify:
        if not args.case_id:
            parser.error("--verify requires --case-id")
        verify_case(args)
    elif args.batch:
        if not args.pdf_dir:
            parser.error("--batch requires --pdf-dir")
        process_batch(args)
    else:
        if not args.pdf:
            parser.error("Single case processing requires --pdf")
        process_single_case(args)


if __name__ == '__main__':
    main()
