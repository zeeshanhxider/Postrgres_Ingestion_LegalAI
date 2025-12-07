"""
Hybrid Legal Case Extractor
Combines metadata (CSV), regex (fast patterns), and AI (LLM) extraction for comprehensive data population.

Strategy:
1. METADATA: Primary source for case identifiers, URLs, dates, court_level (from opinion_type), publication status
2. REGEX: Fast extraction of structural patterns (citations, statutes, parties, division, en_banc flag)
3. AI: Complex understanding (judges, county, outcomes, summary, issues/decisions, arguments, attorneys, precedents, trial info)

This ensures ALL columns are populated by using each method for what it does best.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

from .regex_extractor import (
    RegexExtractor, 
    RegexExtractionResult,
    ExtractedJudge,
    ExtractedParty,
    ExtractedCitation,
    ExtractedStatute
)
from .ai_extractor import extract_case_data
from .models import (
    LegalCaseExtraction,
    CaseModel,
    PartyModel,
    AttorneyModel,
    JudgeModel,
    IssueDecisionModel,
    ArgumentModel,
    PrecedentModel,
    LegalRole,
    PersonalRole,
    JudgeRole,
    AppealOutcome,
    OverallCaseOutcome,
    CourtLevel,
    District,
    PublicationStatus
)

logger = logging.getLogger(__name__)


@dataclass
class HybridExtractionResult:
    """
    Combined result from hybrid extraction (metadata + regex + AI).
    
    This model contains ALL fields needed to populate the complete database schema.
    Each field is tagged with its source for transparency.
    """
    
    # === CASE IDENTIFICATION (from metadata) ===
    case_file_id: str = ""  # From metadata.case_number
    title: str = ""  # From metadata.case_title
    opinion_type: Optional[str] = None  # From metadata.opinion_type
    publication_status: Optional[str] = None  # From metadata.publication_status
    decision_year: Optional[int] = None  # From metadata.year
    decision_month: Optional[str] = None  # From metadata.month
    source_url: Optional[str] = None  # From metadata.pdf_url
    case_info_url: Optional[str] = None  # From metadata.case_info_url
    appeal_published_date: Optional[datetime] = None  # From metadata.file_date
    published: bool = True  # From metadata.file_contains
    
    # === COURT INFO (metadata primary) ===
    court_level: str = "unknown"  # From metadata.opinion_type
    court: Optional[str] = None  # From AI (full court name)
    district: Optional[str] = None  # From metadata.division or regex fallback
    docket_number: Optional[str] = None  # Composite: case_number-division
    county: Optional[str] = None  # From AI
    
    # === TRIAL COURT INFO (AI only) ===
    source_docket_number: Optional[str] = None  # From AI
    trial_judge: Optional[str] = None  # From AI
    trial_start_date: Optional[datetime] = None  # From AI
    trial_end_date: Optional[datetime] = None  # From AI
    trial_published_date: Optional[datetime] = None  # From AI
    
    # === APPEAL INFO (AI + regex) ===
    appeal_start_date: Optional[datetime] = None  # From AI
    appeal_end_date: Optional[datetime] = None  # From AI
    oral_argument_date: Optional[datetime] = None  # From AI
    
    # === OUTCOMES (AI only) ===
    appeal_outcome: Optional[str] = None  # From AI (affirmed/reversed/etc)
    overall_case_outcome: Optional[str] = None  # From AI
    outcome_detail: Optional[str] = None  # From AI (e.g., "affirmed in part")
    
    # === WINNER INFO (AI only) ===
    winner_legal_role: Optional[str] = None  # From AI
    winner_personal_role: Optional[str] = None  # From AI
    
    # === CONTENT (AI only) ===
    summary: Optional[str] = None  # From AI
    case_type: Optional[str] = None  # From AI
    
    # === EXTRACTED ENTITIES ===
    # Judges: AI only
    judges: List[ExtractedJudge] = field(default_factory=list)
    
    # Parties: Regex extracts names/legal roles, AI adds personal roles
    parties: List[ExtractedParty] = field(default_factory=list)
    parties_with_personal_roles: List[PartyModel] = field(default_factory=list)  # From AI
    
    # Attorneys: AI only (not extracted by regex)
    attorneys: List[AttorneyModel] = field(default_factory=list)
    
    # Citations: Regex extracts case citations
    citations: List[ExtractedCitation] = field(default_factory=list)
    
    # Statutes: Regex extracts RCW references
    statutes: List[ExtractedStatute] = field(default_factory=list)
    
    # Issues/Decisions: AI only
    issues_decisions: List[IssueDecisionModel] = field(default_factory=list)
    
    # Arguments: AI only
    arguments: List[ArgumentModel] = field(default_factory=list)
    
    # Precedents: AI extracts with relationship context
    precedents: List[PrecedentModel] = field(default_factory=list)
    
    # === FLAGS ===
    en_banc: bool = False  # From regex
    ai_extraction_successful: bool = False  # Whether AI extraction succeeded
    regex_extraction_successful: bool = False  # Whether regex extraction succeeded
    
    # === SOURCE TRACKING ===
    extraction_sources: Dict[str, str] = field(default_factory=dict)


class HybridExtractor:
    """
    Hybrid extractor that combines metadata, regex, and AI extraction.
    
    Uses each method for what it does best:
    - Metadata: Case identifiers, URLs, dates (guaranteed accuracy)
    - Regex: Structural patterns (fast, free, reliable)
    - AI: Complex understanding (expensive but comprehensive)
    """
    
    def __init__(self):
        self.regex_extractor = RegexExtractor()
    
    def extract(
        self,
        full_text: str,
        metadata: Dict[str, Any],
        enable_ai: bool = True,
        ai_timeout: int = 120
    ) -> HybridExtractionResult:
        """
        Perform hybrid extraction combining all three methods.
        
        Args:
            full_text: Full PDF text content
            metadata: CSV metadata dict
            enable_ai: Whether to run AI extraction (can be disabled for speed)
            ai_timeout: Timeout for AI extraction in seconds
            
        Returns:
            HybridExtractionResult with all available data
        """
        result = HybridExtractionResult()
        result.extraction_sources = {}
        
        # === PHASE 1: METADATA EXTRACTION (always runs) ===
        logger.info("[HYBRID] Phase 1: Extracting from metadata...")
        self._extract_from_metadata(result, metadata)
        
        # === PHASE 2: REGEX EXTRACTION (always runs) ===
        logger.info("[HYBRID] Phase 2: Running regex extraction...")
        try:
            regex_result = self.regex_extractor.extract_from_pdf_text(full_text, metadata)
            self._merge_regex_results(result, regex_result)
            result.regex_extraction_successful = True
            logger.info(f"[HYBRID] Regex: {len(result.judges)} judges, {len(result.citations)} citations, "
                       f"{len(result.statutes)} statutes")
        except Exception as e:
            logger.warning(f"[HYBRID] Regex extraction failed: {e}")
            result.regex_extraction_successful = False
        
        # === PHASE 3: AI EXTRACTION (optional, enriches data) ===
        if enable_ai:
            logger.info("[HYBRID] Phase 3: Running AI extraction...")
            try:
                case_info = {
                    'case_number': metadata.get('case_number', 'Unknown'),
                    'title': metadata.get('title', metadata.get('case_title', 'Unknown')),
                    'court_level': result.court_level,
                    'division': result.district,
                    'publication': result.publication_status,
                    'court_info_raw': metadata.get('court_info_raw', '')
                }
                
                ai_result = extract_case_data(full_text, case_info)
                
                if ai_result:
                    self._merge_ai_results(result, ai_result)
                    result.ai_extraction_successful = True
                    logger.info(f"[HYBRID] AI: {len(result.attorneys)} attorneys, "
                               f"{len(result.issues_decisions)} issues, "
                               f"{len(result.arguments)} arguments")
                else:
                    logger.warning("[HYBRID] AI extraction returned None")
                    result.ai_extraction_successful = False
                    
            except Exception as e:
                logger.warning(f"[HYBRID] AI extraction failed: {e}")
                result.ai_extraction_successful = False
        else:
            logger.info("[HYBRID] Phase 3: AI extraction skipped (disabled)")
        
        # === PHASE 4: MERGE AND DEDUPLICATE ===
        logger.info("[HYBRID] Phase 4: Merging and deduplicating...")
        self._finalize_results(result)
        
        logger.info(f"[HYBRID] Extraction complete: "
                   f"regex={result.regex_extraction_successful}, "
                   f"ai={result.ai_extraction_successful}")
        
        return result
    
    def _extract_from_metadata(self, result: HybridExtractionResult, metadata: Dict[str, Any]) -> None:
        """Extract all available fields from metadata (CSV)"""
        
        # Case identification
        result.case_file_id = str(metadata.get('case_number', ''))
        result.title = metadata.get('case_title', metadata.get('title', ''))
        result.opinion_type = metadata.get('opinion_type')
        result.publication_status = metadata.get('publication_status')
        result.source_url = metadata.get('pdf_url')
        result.case_info_url = metadata.get('case_info_url')
        
        # Year/month
        year = metadata.get('year')
        if year:
            try:
                result.decision_year = int(year)
            except (ValueError, TypeError):
                pass
        result.decision_month = metadata.get('month')
        
        # Parse file_date
        file_date = metadata.get('file_date')
        if file_date:
            result.appeal_published_date = self._parse_date(file_date)
        
        # Publication status from file_contains
        file_contains = str(metadata.get('file_contains', '')).lower()
        result.published = 'unpublished' not in file_contains
        
        # Court level from opinion_type
        opinion_type = str(metadata.get('opinion_type', '')).lower()
        if 'supreme' in opinion_type:
            result.court_level = 'supreme_court'
        elif 'appeals' in opinion_type or 'court of appeals' in opinion_type:
            result.court_level = 'court_of_appeals'
        else:
            result.court_level = 'unknown'
        
        # Division from metadata
        division = str(metadata.get('division', '')).strip()
        division_suffix = None
        if division in ('I', '1'):
            result.district = 'Division I'
            division_suffix = 'I'
        elif division in ('II', '2'):
            result.district = 'Division II'
            division_suffix = 'II'
        elif division in ('III', '3'):
            result.district = 'Division III'
            division_suffix = 'III'
        elif division:
            result.district = f'Division {division}'
            division_suffix = division
        
        # Build composite docket_number
        if division_suffix:
            result.docket_number = f"{result.case_file_id}-{division_suffix}"
        else:
            result.docket_number = result.case_file_id
        
        # Track sources
        result.extraction_sources['case_file_id'] = 'metadata'
        result.extraction_sources['title'] = 'metadata'
        result.extraction_sources['source_url'] = 'metadata'
        result.extraction_sources['appeal_published_date'] = 'metadata'
        result.extraction_sources['published'] = 'metadata'
        result.extraction_sources['court_level'] = 'metadata'
        result.extraction_sources['district'] = 'metadata'
    
    def _merge_regex_results(self, result: HybridExtractionResult, regex_result: RegexExtractionResult) -> None:
        """Merge regex extraction results into hybrid result"""
        
        # NOTE: court_level comes from metadata (opinion_type) only - no regex fallback
        # NOTE: judges, county, appeal_outcome, outcome_detail are extracted by AI only
        
        # Division (regex fallback only if metadata didn't provide it)
        if not result.district and regex_result.division:
            division_map = {
                'division_one': 'Division I',
                'division_two': 'Division II',
                'division_three': 'Division III'
            }
            result.district = division_map.get(regex_result.division)
            result.extraction_sources['district'] = 'regex'
        
        # En banc flag (regex)
        result.en_banc = regex_result.en_banc
        
        # Entities from regex (only parties, citations, statutes - NOT judges)
        result.parties = regex_result.parties
        result.citations = regex_result.citations
        result.statutes = regex_result.statutes
        
        result.extraction_sources['parties'] = 'regex'
        result.extraction_sources['citations'] = 'regex'
        result.extraction_sources['statutes'] = 'regex'
    
    def _merge_ai_results(self, result: HybridExtractionResult, ai_result: LegalCaseExtraction) -> None:
        """Merge AI extraction results, enriching existing data"""
        
        case_data = ai_result.case
        
        # === COUNTY (AI only) ===
        if case_data.county:
            result.county = case_data.county
            result.extraction_sources['county'] = 'ai'
        
        # === APPEAL OUTCOME (AI only) ===
        if case_data.appeal_outcome:
            result.appeal_outcome = case_data.appeal_outcome.value
            result.extraction_sources['appeal_outcome'] = 'ai'
        if case_data.overall_case_outcome:
            result.overall_case_outcome = case_data.overall_case_outcome.value
            result.extraction_sources['overall_case_outcome'] = 'ai'
        
        # === JUDGES (AI only - not regex) ===
        for ai_judge in ai_result.appeals_judges:
            role_map = {
                'Authored by': 'author',
                'Concurring': 'concurring',
                'Dissenting': 'dissenting',
                'Joining': 'panelist'
            }
            result.judges.append(ExtractedJudge(
                name=ai_judge.judge_name,
                role=role_map.get(ai_judge.role.value, 'author')
            ))
        result.extraction_sources['judges'] = 'ai'
        
        # === TRIAL COURT INFO (AI only) ===
        result.source_docket_number = case_data.source_docket_number
        result.trial_judge = case_data.trial_judge
        result.trial_start_date = self._parse_date(case_data.trial_start_date)
        result.trial_end_date = self._parse_date(case_data.trial_end_date)
        result.trial_published_date = self._parse_date(case_data.trial_published_date)
        
        result.extraction_sources['source_docket_number'] = 'ai'
        result.extraction_sources['trial_judge'] = 'ai'
        result.extraction_sources['trial_dates'] = 'ai'
        
        # === APPEAL DATES (AI fills in what metadata didn't provide) ===
        if not result.appeal_start_date:
            result.appeal_start_date = self._parse_date(case_data.appeal_start_date)
        if not result.appeal_end_date:
            result.appeal_end_date = self._parse_date(case_data.appeal_end_date)
        if not result.appeal_published_date:
            result.appeal_published_date = self._parse_date(case_data.appeal_published_date)
        if not result.oral_argument_date:
            result.oral_argument_date = self._parse_date(case_data.oral_argument_date)
        
        result.extraction_sources['appeal_dates'] = 'ai'
        
        # === FULL COURT NAME (AI) ===
        if case_data.court:
            result.court = case_data.court
            result.extraction_sources['court'] = 'ai'
        
        # === WINNER INFO (AI only) ===
        if case_data.winner_legal_role:
            result.winner_legal_role = case_data.winner_legal_role.value
            result.extraction_sources['winner_legal_role'] = 'ai'
        if case_data.winner_personal_role:
            result.winner_personal_role = case_data.winner_personal_role.value
            result.extraction_sources['winner_personal_role'] = 'ai'
        
        # === CONTENT (AI only) ===
        result.summary = case_data.summary
        result.case_type = getattr(case_data, 'case_type', 'divorce')
        result.extraction_sources['summary'] = 'ai'
        result.extraction_sources['case_type'] = 'ai'
        
        # === ENTITIES FROM AI ===
        
        # Attorneys (AI only - regex doesn't extract these)
        result.attorneys = ai_result.attorneys
        result.extraction_sources['attorneys'] = 'ai'
        
        # Parties with personal roles (AI enriches regex parties)
        result.parties_with_personal_roles = ai_result.parties
        result.extraction_sources['parties_personal_roles'] = 'ai'
        
        # Issues/Decisions (AI only)
        result.issues_decisions = ai_result.issues_decisions
        result.extraction_sources['issues_decisions'] = 'ai'
        
        # Arguments (AI only)
        result.arguments = ai_result.arguments
        result.extraction_sources['arguments'] = 'ai'
        
        # Precedents with relationship context (AI enriches regex citations)
        result.precedents = ai_result.precedents
        result.extraction_sources['precedents'] = 'ai'
    
    def _finalize_results(self, result: HybridExtractionResult) -> None:
        """Finalize and deduplicate merged results"""
        
        # Deduplicate judges by name
        seen_judges = set()
        unique_judges = []
        for judge in result.judges:
            if judge.name.lower() not in seen_judges:
                unique_judges.append(judge)
                seen_judges.add(judge.name.lower())
        result.judges = unique_judges
        
        # Deduplicate citations
        seen_citations = set()
        unique_citations = []
        for citation in result.citations:
            if citation.full_citation not in seen_citations:
                unique_citations.append(citation)
                seen_citations.add(citation.full_citation)
        result.citations = unique_citations
        
        # Deduplicate statutes
        seen_statutes = set()
        unique_statutes = []
        for statute in result.statutes:
            if statute.rcw_number not in seen_statutes:
                unique_statutes.append(statute)
                seen_statutes.add(statute.rcw_number)
        result.statutes = unique_statutes
    
    def _parse_date(self, date_input) -> Optional[datetime]:
        """Parse date from various formats"""
        if not date_input:
            return None
        
        if isinstance(date_input, datetime):
            return date_input
        
        # Try pandas Timestamp
        try:
            import pandas as pd
            if isinstance(date_input, pd.Timestamp):
                return date_input.to_pydatetime()
        except ImportError:
            pass
        
        # Handle string
        date_str = str(date_input)
        formats = [
            '%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y',
            '%B %d, %Y', '%b %d, %Y', '%b. %d, %Y'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None


def extract_hybrid(
    full_text: str,
    metadata: Dict[str, Any],
    enable_ai: bool = True
) -> HybridExtractionResult:
    """
    Convenience function for hybrid extraction.
    
    Args:
        full_text: Full PDF text content
        metadata: CSV metadata dict
        enable_ai: Whether to run AI extraction
        
    Returns:
        HybridExtractionResult with all available data
    """
    extractor = HybridExtractor()
    return extractor.extract(full_text, metadata, enable_ai=enable_ai)
