"""
Case Processor - Orchestrates the extraction pipeline
Combines metadata (CSV) + PDF extraction + LLM extraction
"""

import csv
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dateutil import parser as date_parser

from .models import CaseMetadata, ExtractedCase
from .pdf_extractor import PDFExtractor
from .llm_extractor import LLMExtractor

logger = logging.getLogger(__name__)


class CaseProcessor:
    """
    Main processor that orchestrates the full extraction pipeline.
    
    Pipeline:
    1. Load metadata from CSV
    2. Extract text from PDF using LlamaParse
    3. Extract structured data using LLM (Ollama)
    4. Combine metadata + LLM extraction
    """
    
    def __init__(
        self,
        pdf_extractor: Optional[PDFExtractor] = None,
        llm_extractor: Optional[LLMExtractor] = None
    ):
        """
        Initialize the case processor.
        
        Args:
            pdf_extractor: PDFExtractor instance (created if not provided)
            llm_extractor: LLMExtractor instance (created if not provided)
        """
        self.pdf_extractor = pdf_extractor or PDFExtractor()
        self.llm_extractor = llm_extractor or LLMExtractor()
    
    def load_metadata_csv(self, csv_path: str) -> Dict[str, Dict[str, Any]]:
        """
        Load metadata CSV and index by case_number.
        
        Args:
            csv_path: Path to metadata.csv
            
        Returns:
            Dictionary mapping case_number -> row data
        """
        metadata_map = {}
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                case_number = row.get('case_number', '').strip()
                if case_number:
                    metadata_map[case_number] = row
        
        logger.info(f"Loaded {len(metadata_map)} cases from metadata CSV")
        return metadata_map
    
    def parse_metadata_row(self, row: Dict[str, Any]) -> CaseMetadata:
        """
        Parse a CSV row into CaseMetadata dataclass.
        
        Args:
            row: Dictionary from CSV row
            
        Returns:
            CaseMetadata object
        """
        metadata = CaseMetadata()
        
        # Direct string fields
        metadata.opinion_type = row.get('opinion_type', '').strip()
        metadata.publication_status = row.get('publication_status', '').strip()
        metadata.month = row.get('month', '').strip()
        metadata.case_number = row.get('case_number', '').strip()
        metadata.division = row.get('division', '').strip()
        metadata.case_title = row.get('case_title', '').strip()
        metadata.file_contains = row.get('file_contains', '').strip()
        metadata.case_info_url = row.get('case_info_url', '').strip()
        metadata.pdf_url = row.get('pdf_url', '').strip()
        metadata.pdf_filename = row.get('pdf_filename', '').strip()
        metadata.download_status = row.get('download_status', '').strip()
        
        # Parse year
        year_str = row.get('year', '').strip()
        if year_str:
            try:
                metadata.year = int(year_str)
            except ValueError:
                pass
        
        # Parse file_date (e.g., "Jan. 16, 2025")
        file_date_str = row.get('file_date', '').strip()
        if file_date_str:
            try:
                parsed = date_parser.parse(file_date_str)
                metadata.file_date = parsed.date()
            except:
                pass
        
        # Parse scraped_at timestamp
        scraped_at_str = row.get('scraped_at', '').strip()
        if scraped_at_str:
            try:
                metadata.scraped_at = date_parser.parse(scraped_at_str)
            except:
                pass
        
        # Derive court_level from opinion_type (keep human-readable)
        opinion_type_lower = metadata.opinion_type.lower()
        if 'supreme' in opinion_type_lower:
            metadata.court_level = 'Supreme Court'
        elif 'appeals' in opinion_type_lower or 'appellate' in opinion_type_lower:
            metadata.court_level = 'Court of Appeals'
        else:
            metadata.court_level = metadata.opinion_type or 'Unknown'
        
        return metadata
    
    def process_case(
        self,
        pdf_path: str,
        metadata_row: Optional[Dict[str, Any]] = None
    ) -> ExtractedCase:
        """
        Process a single case PDF with optional metadata.
        
        Args:
            pdf_path: Path to the PDF file
            metadata_row: Optional metadata from CSV
            
        Returns:
            ExtractedCase with all extracted data
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Processing case: {pdf_path.name}")
        
        # Initialize result
        case = ExtractedCase()
        
        try:
            # Step 1: Parse metadata if provided
            if metadata_row:
                case.metadata = self.parse_metadata_row(metadata_row)
                logger.info(f"  Metadata: {case.metadata.case_number} - {case.metadata.case_title}")
            
            # Step 2: Extract text from PDF
            logger.info("  Extracting PDF text...")
            full_text, page_count = self.pdf_extractor.extract_text(str(pdf_path))
            case.full_text = full_text
            case.page_count = page_count
            logger.info(f"  Extracted {len(full_text)} chars from {page_count} pages")
            
            if not full_text or len(full_text.strip()) < 100:
                raise ValueError("PDF text extraction returned insufficient content")
            
            # Step 3: Extract structured data using LLM
            logger.info("  Running LLM extraction...")
            llm_result = self.llm_extractor.extract(full_text)
            
            # Step 4: Build case from LLM result
            llm_case = self.llm_extractor.build_extracted_case(llm_result)
            
            # Merge LLM extraction into our case
            case.summary = llm_case.summary
            case.case_type = llm_case.case_type
            case.county = llm_case.county
            case.trial_court = llm_case.trial_court
            case.trial_judge = llm_case.trial_judge
            case.source_docket_number = llm_case.source_docket_number
            case.appeal_outcome = llm_case.appeal_outcome
            case.outcome_detail = llm_case.outcome_detail
            case.winner_legal_role = llm_case.winner_legal_role
            case.winner_personal_role = llm_case.winner_personal_role
            case.parties = llm_case.parties
            case.attorneys = llm_case.attorneys
            case.judges = llm_case.judges
            case.citations = llm_case.citations
            case.statutes = llm_case.statutes
            case.issues = llm_case.issues
            case.extraction_timestamp = datetime.now()
            case.llm_model = llm_case.llm_model
            case.extraction_successful = llm_case.extraction_successful
            case.error_message = llm_case.error_message
            
            # Store source file path
            case.source_file_path = str(pdf_path.resolve())
            
            logger.info(f"  Extraction complete: {len(case.parties)} parties, "
                       f"{len(case.judges)} judges, {len(case.issues)} issues")
            
            return case
            
        except Exception as e:
            logger.error(f"  Processing failed: {e}")
            case.extraction_successful = False
            case.error_message = str(e)
            case.extraction_timestamp = datetime.now()
            return case
    
    def process_batch(
        self,
        pdf_dir: str,
        metadata_csv: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[ExtractedCase]:
        """
        Process a batch of PDF files.
        
        Args:
            pdf_dir: Directory containing PDF files
            metadata_csv: Path to metadata CSV (optional)
            limit: Maximum number of files to process
            
        Returns:
            List of ExtractedCase objects
        """
        pdf_dir = Path(pdf_dir)
        
        # Load metadata if provided
        metadata_map = {}
        if metadata_csv:
            metadata_map = self.load_metadata_csv(metadata_csv)
        
        # Find all PDFs (recursively)
        pdf_files = list(pdf_dir.rglob("*.pdf"))
        
        if limit:
            pdf_files = pdf_files[:limit]
        
        logger.info(f"Processing {len(pdf_files)} PDF files from {pdf_dir}")
        
        results = []
        for i, pdf_path in enumerate(pdf_files, 1):
            logger.info(f"\n[{i}/{len(pdf_files)}] Processing: {pdf_path.name}")
            
            # Try to find matching metadata
            metadata_row = None
            if metadata_map:
                # Try to match by filename or case number
                for case_num, row in metadata_map.items():
                    if case_num in pdf_path.name or row.get('pdf_filename', '') == pdf_path.name:
                        metadata_row = row
                        break
            
            # Process the case
            case = self.process_case(str(pdf_path), metadata_row)
            results.append(case)
            
            # Log progress
            if case.extraction_successful:
                logger.info(f"  ✓ Success")
            else:
                logger.warning(f"  ✗ Failed: {case.error_message}")
        
        # Summary
        successful = sum(1 for c in results if c.extraction_successful)
        logger.info(f"\nBatch complete: {successful}/{len(results)} successful")
        
        return results
