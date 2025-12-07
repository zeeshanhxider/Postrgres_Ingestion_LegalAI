#!/usr/bin/env python3
"""
Test Hybrid Extraction on Sample Cases
Tests one case from each category:
1. Supreme Court
2. Court of Appeals - Published
3. Court of Appeals - Published in Part
"""

import os
import sys
import logging
import pandas as pd
from pathlib import Path
from sqlalchemy import text

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
        logging.FileHandler('hybrid_test.log')
    ]
)

logger = logging.getLogger(__name__)


def clear_database():
    """Clear all case-related data from the database"""
    logger.info("="*80)
    logger.info("CLEARING DATABASE")
    logger.info("="*80)
    
    tables_to_clear = [
        'arguments',
        'citation_edges',
        'statute_citations',
        'issues_decisions',
        'attorneys',
        'parties',
        'case_judges',
        'case_phrases',
        'word_occurrence',
        'case_sentences',
        'case_chunks',
        'documents',
        'cases'
    ]
    
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            
            for table in tables_to_clear:
                try:
                    result = conn.execute(text(f"DELETE FROM {table}"))
                    logger.info(f"[OK] Cleared table: {table} ({result.rowcount} rows)")
                except Exception as e:
                    logger.warning(f"[WARN] Could not clear {table}: {e}")
            
            # Reset sequences
            try:
                conn.execute(text("ALTER SEQUENCE cases_case_id_seq RESTART WITH 1"))
                logger.info("[OK] Reset case_id sequence")
            except Exception as e:
                logger.warning(f"[WARN] Could not reset sequence: {e}")
            
            trans.commit()
            logger.info("[OK] Database cleared successfully\n")
            
    except Exception as e:
        logger.error(f"[FAIL] Failed to clear database: {e}")
        raise


def find_sample_cases_from_folders(
    supreme_csv: Path,
    appeals_pub_csv: Path, 
    appeals_pub_part_csv: Path,
    downloads_dir: Path
):
    """
    Find one representative case from each court category by reading separate metadata files.
    
    Returns:
        List of (category_name, row_metadata, pdf_path) tuples
    """
    logger.info("="*80)
    logger.info("FINDING SAMPLE CASES FROM EACH COURT FOLDER")
    logger.info("="*80)
    
    samples = []
    
    # Map CSV to court type info: (csv_path, folder_name, category_label, opinion_type, publication_status)
    court_mappings = [
        (supreme_csv, "Supreme_Court_Opinions", "Supreme Court", "Supreme Court", "Published"),
        (appeals_pub_csv, "Court_of_Appeals_Published", "Court of Appeals - Published", "Court of Appeals", "Published"),
        (appeals_pub_part_csv, "Court_of_Appeals_Published_in_Part", "Court of Appeals - Published in Part", "Court of Appeals", "Published in Part")
    ]
    
    for i, (csv_path, folder_name, category_label, opinion_type, publication_status) in enumerate(court_mappings, 1):
        logger.info(f"\n[{i}] Processing {category_label}")
        logger.info(f"    CSV: {csv_path}")
        
        df = pd.read_csv(csv_path)
        
        # Filter for successfully downloaded PDFs (case-sensitive: "Success")
        successful = df[df['download_status'] == 'Success']
        
        if successful.empty:
            logger.warning(f"    [SKIP] No successful downloads found")
            continue
        
        # Take first successful case
        row = successful.iloc[0].to_dict()
        
        # Add derived fields
        row['opinion_type'] = opinion_type
        row['publication_status'] = publication_status
        
        # Construct PDF path: downloads/{folder_name}/{year}/{month}/{pdf_filename}
        year = str(row['year'])
        month = str(row['month'])
        pdf_filename = row['pdf_filename']
        
        pdf_path = downloads_dir / folder_name / year / month / pdf_filename
        
        if not pdf_path.exists():
            logger.warning(f"    [SKIP] PDF not found: {pdf_path}")
            continue
        
        samples.append((category_label, row, pdf_path))
        logger.info(f"    ✓ {row['case_number']} - {row['case_title']}")
        logger.info(f"    PDF: {pdf_path}")
    
    logger.info(f"\n[OK] Found {len(samples)} sample cases\n")
    return samples


def test_case(category: str, row_metadata: dict, pdf_path: Path, ingestor: LegalCaseIngestor):
    """Test hybrid extraction on a single case"""
    logger.info("="*80)
    logger.info(f"TESTING: {category}")
    logger.info("="*80)
    logger.info(f"Case Number: {row_metadata['case_number']}")
    logger.info(f"Title: {row_metadata['case_title']}")
    logger.info(f"PDF: {pdf_path.name}")
    logger.info("")
    
    try:
        # Read PDF
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        # Prepare metadata
        metadata = {
            'case_number': row_metadata.get('case_number', ''),
            'case_title': row_metadata.get('case_title', ''),
            'title': row_metadata.get('case_title', ''),
            'court_level': row_metadata.get('opinion_type', 'Unknown'),
            'division': row_metadata.get('division', ''),
            'publication': row_metadata.get('publication_status', ''),
            'file_date': row_metadata.get('file_date'),
            'year': row_metadata.get('year'),
            'month': row_metadata.get('month'),
            'file_contains': row_metadata.get('file_contains', ''),
            'opinion_type': row_metadata.get('opinion_type', ''),
            'publication_status': row_metadata.get('publication_status', ''),
            'case_info_url': row_metadata.get('case_info_url', ''),
            'pdf_url': row_metadata.get('pdf_url', ''),
        }
        
        # Prepare source file info
        source_file_info = {
            'filename': pdf_path.name,
            'file_path': str(pdf_path.absolute()),
            'source_url': row_metadata.get('pdf_url', ''),
        }
        
        # Run hybrid extraction
        logger.info("[HYBRID] Starting hybrid extraction...")
        result = ingestor.ingest_pdf_case(
            pdf_content=pdf_content,
            metadata=metadata,
            source_file_info=source_file_info,
            extraction_mode='hybrid'
        )
        
        # Print results
        logger.info("")
        logger.info("="*80)
        logger.info(f"RESULTS: {category}")
        logger.info("="*80)
        logger.info(f"Case ID: {result['case_id']}")
        logger.info(f"Extraction Mode: {result['extraction_mode']}")
        logger.info("")
        logger.info("ENTITIES EXTRACTED:")
        logger.info(f"  Parties: {result['case_stats']['parties']}")
        logger.info(f"  Attorneys: {result['case_stats']['attorneys']}")
        logger.info(f"  Judges: {result['case_stats']['judges']}")
        logger.info(f"  Issues: {result['case_stats']['issues']}")
        logger.info(f"  Arguments: {result['case_stats']['arguments']}")
        logger.info(f"  Citations: {result['case_stats']['citations']}")
        logger.info("")
        logger.info("RAG INDEXING:")
        logger.info(f"  Chunks: {result['chunks_created']}")
        logger.info(f"  Sentences: {result.get('sentences_processed', 0)}")
        logger.info(f"  Words: {result['words_processed']} ({result['unique_words']} unique)")
        logger.info(f"  Phrases: {result['phrases_extracted']}")
        logger.info("")
        
        # Query case details
        with engine.connect() as conn:
            case_query = text("""
                SELECT case_file_id, title, court_level, district, county,
                       docket_number, source_docket_number, trial_judge,
                       appeal_outcome, overall_case_outcome, summary,
                       winner_legal_role, winner_personal_role,
                       opinion_type, publication_status, decision_year, decision_month
                FROM cases WHERE case_id = :case_id
            """)
            case_row = conn.execute(case_query, {'case_id': result['case_id']}).fetchone()
            
            logger.info("CASE DETAILS (SAMPLE COLUMNS):")
            logger.info(f"  case_file_id: {case_row.case_file_id}")
            logger.info(f"  court_level: {case_row.court_level}")
            logger.info(f"  district: {case_row.district}")
            logger.info(f"  county: {case_row.county}")
            logger.info(f"  docket_number: {case_row.docket_number}")
            logger.info(f"  source_docket_number: {case_row.source_docket_number}")
            logger.info(f"  trial_judge: {case_row.trial_judge}")
            logger.info(f"  appeal_outcome: {case_row.appeal_outcome}")
            logger.info(f"  winner_legal_role: {case_row.winner_legal_role}")
            logger.info(f"  opinion_type: {case_row.opinion_type}")
            logger.info(f"  publication_status: {case_row.publication_status}")
            logger.info(f"  decision_year: {case_row.decision_year}")
            logger.info(f"  summary: {case_row.summary[:100] if case_row.summary else 'None'}...")
        
        logger.info("")
        logger.info(f"[OK] {category} - SUCCESS")
        logger.info("")
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] {category} - FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """Main test function"""
    # Configuration - use the three separate metadata files
    downloads_dir = Path("downloads")
    
    supreme_csv = downloads_dir / "Supreme_Court_Opinions" / "metadata.csv"
    appeals_pub_csv = downloads_dir / "Court_of_Appeals_Published" / "metadata.csv"
    appeals_pub_part_csv = downloads_dir / "Court_of_Appeals_Published_in_Part" / "metadata.csv"
    
    # Verify all exist
    for csv_path, name in [(supreme_csv, "Supreme Court"), (appeals_pub_csv, "Court of Appeals Published"), (appeals_pub_part_csv, "Court of Appeals Published in Part")]:
        if not csv_path.exists():
            logger.error(f"{name} metadata not found: {csv_path}")
            sys.exit(1)
    
    # Clear database
    clear_database()
    
    # Find sample cases from each category
    samples = find_sample_cases_from_folders(supreme_csv, appeals_pub_csv, appeals_pub_part_csv, downloads_dir)
    
    if not samples:
        logger.error("No sample cases found!")
        sys.exit(1)
    
    # Initialize ingestor
    ingestor = LegalCaseIngestor(engine)
    
    # Test each sample
    results = []
    for category, row_metadata, pdf_path in samples:
        success = test_case(category, row_metadata, pdf_path, ingestor)
        results.append((category, success))
    
    # Final summary
    logger.info("="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    for category, success in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"{status} - {category}")
    
    success_count = sum(1 for _, s in results if s)
    logger.info("")
    logger.info(f"Total: {success_count}/{len(results)} tests passed")
    logger.info("="*80)


if __name__ == "__main__":
    main()
