#!/usr/bin/env python3
"""
Main runner for Legal Case Ingestion Pipeline
Batch process PDFs and insert into database.
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

from pipeline.config import PipelineConfig
from pipeline.pdf_extractor import PDFExtractor
from pipeline.llm_extractor import LLMExtractor
from pipeline.case_processor import CaseProcessor
from pipeline.db_inserter import DatabaseInserter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'pipeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Legal Case Ingestion Pipeline - Process court opinion PDFs'
    )
    parser.add_argument(
        'source',
        help='Path to PDF file or directory containing PDFs'
    )
    parser.add_argument(
        '--metadata',
        help='Path to metadata CSV file (optional)',
        default=None
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of files to process',
        default=None
    )
    parser.add_argument(
        '--no-db',
        action='store_true',
        help='Skip database insertion (extraction only)'
    )
    parser.add_argument(
        '--model',
        help='Ollama model to use (default: from env or llama3.1:8b)',
        default=None
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--chunk-embedding',
        choices=['all', 'important', 'none'],
        default='all',
        help='Chunk embedding mode: all (default), important (ANALYSIS/FACTS/HOLDING only), none'
    )
    parser.add_argument(
        '--phrase-filter',
        choices=['strict', 'relaxed'],
        default='strict',
        help='Phrase filtering mode: strict (legal terms only) or relaxed (all meaningful)'
    )
    parser.add_argument(
        '--no-rag',
        action='store_true',
        help='Skip RAG processing (chunks, sentences, words, phrases)'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    config = PipelineConfig.from_env()
    if args.model:
        config.ollama_model = args.model
    
    logger.info("="*60)
    logger.info("LEGAL CASE INGESTION PIPELINE")
    logger.info("="*60)
    logger.info(f"Source: {args.source}")
    logger.info(f"Metadata: {args.metadata or 'None'}")
    logger.info(f"Limit: {args.limit or 'None'}")
    logger.info(f"Model: {config.ollama_model}")
    logger.info(f"Database: {'Disabled' if args.no_db else 'Enabled'}")
    
    # Initialize components
    pdf_extractor = PDFExtractor(config.llama_cloud_api_key)
    llm_extractor = LLMExtractor(
        model=config.ollama_model,
        base_url=config.ollama_base_url,
        timeout=config.llm_timeout
    )
    
    # Test Ollama connection
    if not llm_extractor.test_connection():
        logger.error("Failed to connect to Ollama. Is it running?")
        sys.exit(1)
    
    processor = CaseProcessor(pdf_extractor, llm_extractor)
    
    # Initialize database inserter if needed
    inserter = None
    if not args.no_db:
        inserter = DatabaseInserter.from_url(
            config.database_url,
            enable_rag=not args.no_rag
        )
        
        # Configure RAG options if RAG is enabled
        if not args.no_rag:
            inserter.configure_rag(
                chunk_embedding_mode=args.chunk_embedding,
                phrase_filter_mode=args.phrase_filter
            )
            logger.info(f"RAG: chunks={args.chunk_embedding}, phrases={args.phrase_filter}")
        else:
            logger.info("RAG: Disabled")
        
        logger.info(f"Database connected. Current cases: {inserter.get_case_count()}")
    
    source_path = Path(args.source)
    
    # Process single file or directory
    if source_path.is_file():
        # Single file
        logger.info(f"\nProcessing single file: {source_path.name}")
        
        # Try to find metadata
        metadata_row = None
        if args.metadata:
            metadata_map = processor.load_metadata_csv(args.metadata)
            for case_num, row in metadata_map.items():
                if case_num in source_path.name:
                    metadata_row = row
                    break
        
        case = processor.process_case(str(source_path), metadata_row)
        
        if case.extraction_successful:
            logger.info(f"✓ Extraction successful")
            logger.info(f"  Summary: {case.summary[:200]}..." if case.summary else "")
            logger.info(f"  Parties: {len(case.parties)}, Judges: {len(case.judges)}, Issues: {len(case.issues)}")
            
            if inserter:
                case_id = inserter.insert_case(case)
                if case_id:
                    logger.info(f"✓ Inserted as case_id: {case_id}")
                else:
                    logger.error("✗ Database insertion failed")
        else:
            logger.error(f"✗ Extraction failed: {case.error_message}")
    
    elif source_path.is_dir():
        # Directory batch processing
        logger.info(f"\nBatch processing directory: {source_path}")
        
        cases = processor.process_batch(
            str(source_path),
            metadata_csv=args.metadata,
            limit=args.limit
        )
        
        # Insert into database
        if inserter and cases:
            successful_cases = [c for c in cases if c.extraction_successful]
            logger.info(f"\nInserting {len(successful_cases)} cases into database...")
            
            results = inserter.insert_batch(successful_cases)
            logger.info(f"Database: {results['success']} inserted, {results['failed']} failed")
    
    else:
        logger.error(f"Source not found: {source_path}")
        sys.exit(1)
    
    logger.info("\n" + "="*60)
    logger.info("PIPELINE COMPLETE")
    logger.info("="*60)


if __name__ == "__main__":
    main()
