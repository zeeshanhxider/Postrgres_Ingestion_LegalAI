"""
Regex-based Legal Case Extractor
Fast, cost-free extraction using pattern matching instead of LLM calls.
Extracts: judges, citations, outcomes, dates, parties from Washington State court opinions.

Optimized for Washington State court opinion PDF formatting.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedJudge:
    """Extracted judge information"""
    name: str
    role: str  # 'author', 'concurring', 'dissenting', 'pro_tempore'


@dataclass
class ExtractedCitation:
    """Extracted case citation"""
    volume: str
    reporter: str  # 'Wn.2d', 'Wn. App.', 'Wn. App. 2d'
    page: str
    full_citation: str


@dataclass
class ExtractedStatute:
    """Extracted RCW statute citation"""
    rcw_number: str
    full_text: str


@dataclass
class ExtractedParty:
    """Extracted party information"""
    name: str
    role: str  # 'appellant', 'respondent', 'petitioner', 'cross_appellant', etc.


@dataclass
class RegexExtractionResult:
    """Complete extraction result from regex parsing"""
    # From metadata
    case_number: str = ""
    case_name: str = ""
    decision_date: Optional[datetime] = None
    year: Optional[int] = None
    month: Optional[str] = None
    pdf_url: str = ""
    case_info_url: str = ""
    
    # From PDF regex extraction
    court_level: str = ""  # 'supreme_court', 'court_of_appeals'
    division: Optional[str] = None  # 'division_one', 'division_two', 'division_three'
    publication_status: str = "published"
    filed_date: Optional[datetime] = None
    
    # Outcome
    appeal_outcome: Optional[str] = None  # 'affirmed', 'reversed', 'remanded', 'dismissed'
    outcome_detail: Optional[str] = None  # 'affirmed in part', 'reversed and remanded'
    
    # Extracted entities
    judges: List[ExtractedJudge] = field(default_factory=list)
    parties: List[ExtractedParty] = field(default_factory=list)
    citations: List[ExtractedCitation] = field(default_factory=list)
    statutes: List[ExtractedStatute] = field(default_factory=list)
    
    # County (if found)
    county: Optional[str] = None
    
    # En banc flag
    en_banc: bool = False


class RegexExtractor:
    """
    Fast regex-based extractor for Washington State court opinions.
    Replaces expensive LLM calls with pattern matching.
    
    Key optimizations:
    1. Pre-compiled patterns for performance
    2. Text normalization to handle PDF line-break issues
    3. Single-pass extraction where possible
    4. Targeted text slicing to reduce search space
    """
    
    # Washington State counties (pre-sorted by length for greedy matching)
    WA_COUNTIES = sorted([
        "Adams", "Asotin", "Benton", "Chelan", "Clallam", "Clark", "Columbia",
        "Cowlitz", "Douglas", "Ferry", "Franklin", "Garfield", "Grant", "Grays Harbor",
        "Island", "Jefferson", "King", "Kitsap", "Kittitas", "Klickitat", "Lewis",
        "Lincoln", "Mason", "Okanogan", "Pacific", "Pend Oreille", "Pierce", "San Juan",
        "Skagit", "Skamania", "Snohomish", "Spokane", "Stevens", "Thurston", "Wahkiakum",
        "Walla Walla", "Whatcom", "Whitman", "Yakima"
    ], key=len, reverse=True)
    
    # Month mapping for date parsing
    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for performance"""
        
        # === COURT PATTERNS (search first 2000 chars) ===
        # Handle variations: "SUPREME COURT OF THE STATE OF WASHINGTON" or "SUPREME COURT, STATE OF WASHINGTON"
        self.supreme_court_re = re.compile(
            r'SUPREME\s+COURT[,\s]+(?:OF\s+)?(?:THE\s+)?STATE\s+OF\s+WASHINGTON', re.I)
        self.appeals_court_re = re.compile(
            r'COURT\s+OF\s+APPEALS', re.I)
        self.division_re = re.compile(
            r'DIVISION\s+(ONE|TWO|THREE|I{1,3}|[123])', re.I)
        
        # === DATE PATTERNS ===
        self.filed_date_re = re.compile(
            r'Filed[:\s]+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})', re.I)
        self.date_components_re = re.compile(
            r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})')
        
        # === OUTCOME PATTERNS (search last 5000 chars) ===
        # Ordered by specificity - compound outcomes first
        # Outcome patterns - ordered from most specific to least specific
        # Pattern format: (regex, appeal_outcome, outcome_detail)
        # Note: Washington opinions typically use "We affirm/reverse" or "is affirmed/reversed"
        self.outcome_patterns = [
            # Combined outcomes (most specific first)
            (re.compile(r'affirm(?:ed)?\s+in\s+part[,\s]+(?:and\s+)?revers(?:ed)?\s+in\s+part', re.I), 
             'affirmed', 'affirmed in part, reversed in part'),
            (re.compile(r'revers(?:ed)?\s+in\s+part[,\s]+(?:and\s+)?affirm(?:ed)?\s+in\s+part', re.I), 
             'reversed', 'reversed in part, affirmed in part'),
            (re.compile(r'(?:we\s+)?revers(?:e|ed)\s+(?:and\s+)?remand', re.I), 
             'reversed', 'reversed and remanded'),
            (re.compile(r'(?:we\s+)?affirm(?:ed)?\s+(?:and\s+)?remand', re.I), 
             'affirmed', 'affirmed and remanded'),
            # "We reverse/affirm" patterns (common in WA opinions)
            (re.compile(r'\bwe\s+remand\b', re.I), 'remanded', None),
            (re.compile(r'\bwe\s+affirm\b', re.I), 'affirmed', None),
            (re.compile(r'\bwe\s+reverse\b', re.I), 'reversed', None),
            (re.compile(r'\bwe\s+dismiss\b', re.I), 'dismissed', None),
            # "is hereby affirmed" patterns
            (re.compile(r'\bis\s+(?:hereby\s+)?affirmed\b', re.I), 'affirmed', None),
            (re.compile(r'\bis\s+(?:hereby\s+)?reversed\b', re.I), 'reversed', None),
            (re.compile(r'\bis\s+(?:hereby\s+)?remanded\b', re.I), 'remanded', None),
            (re.compile(r'\bis\s+(?:hereby\s+)?dismissed\b', re.I), 'dismissed', None),
            # Simple past tense forms (least specific)
            (re.compile(r'\baffirmed\b', re.I), 'affirmed', None),
            (re.compile(r'\breversed\b', re.I), 'reversed', None),
            (re.compile(r'\bremanded\b', re.I), 'remanded', None),
            (re.compile(r'\bdismissed\b', re.I), 'dismissed', None),
        ]
        
        # === JUDGE PATTERNS ===
        # Author pattern: "LASTNAME, J.-" handles hyphenated and accented names
        # Note: \w includes unicode letters in Python 3
        self.author_re = re.compile(
            r'([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ]+(?:-[A-ZÁÉÍÓÚÑ]+)*)\s*,\s*(?:C\.?\s*)?J\.?\s*[-–—:]', re.M)
        
        # Concurring: "Lastname, J., concurring" - require word boundary or whitespace before name
        self.concurring_re = re.compile(
            r'(?:^|[\s\(\[])([A-Za-záéíóúñÁÉÍÓÚÑ][a-záéíóúñ]+(?:-[A-Za-záéíóúñÁÉÍÓÚÑ][a-záéíóúñ]+)?)\s*,\s*(?:C\.?\s*)?J\.?(?:\s*P\.?\s*T\.?)?\s*[,.]?\s*concurr', re.I | re.M)
        
        # Dissenting: "Lastname, J., dissenting" - require word boundary or whitespace before name
        self.dissenting_re = re.compile(
            r'(?:^|[\s\(\[])([A-Za-záéíóúñÁÉÍÓÚÑ][a-záéíóúñ]+(?:-[A-Za-záéíóúñÁÉÍÓÚÑ][a-záéíóúñ]+)?)\s*,\s*(?:C\.?\s*)?J\.?(?:\s*P\.?\s*T\.?)?\s*[,.]?\s*dissent', re.I | re.M)
        
        # Pro tempore: "Lastname, J.P.T." - require word boundary or whitespace before name
        self.pro_tem_re = re.compile(
            r'(?:^|[\s\(\[])([A-Za-záéíóúñÁÉÍÓÚÑ][a-záéíóúñ]+(?:-[A-Za-záéíóúñÁÉÍÓÚÑ][a-záéíóúñ]+)?)\s*,\s*J\.?\s*P\.?\s*T\.?', re.I | re.M)
        
        # === CITATION PATTERNS (combined for efficiency) ===
        # Washington citations: 123 Wn.2d 456, 123 Wn. App. 456, etc.
        self.wa_citation_re = re.compile(
            r'(\d{1,3})\s+(Wn\.?\s*(?:App\.?\s*)?2d|Wn\.?\s*App\.?|Wash\.?\s*2d|Wash\.?)\s+(\d{1,4})')
        
        # RCW citations: RCW 49.62.070
        self.rcw_re = re.compile(r'RCW\s+(\d+\.\d+(?:\.\d+)?)', re.I)
        
        # === OTHER PATTERNS ===
        self.en_banc_re = re.compile(r'\bEN\s+BANC\b', re.I)
        self.county_re = re.compile(
            r'Superior\s+Court\s+(?:of|for)\s+(' + '|'.join(self.WA_COUNTIES) + r')\s+County', re.I)
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text to handle PDF line-break issues.
        Fixes cases like "MONTOYA-LE\\nWIS" -> "MONTOYA-LEWIS"
        
        Be careful not to join unrelated words across lines.
        """
        # Fix single uppercase letter before newline followed by uppercase word
        # Pattern: "M\nONTOYA" -> "MONTOYA" (first letter split from rest of word)
        # This commonly happens at page boundaries in PDFs
        text = re.sub(r'([A-ZÁÉÍÓÚÑ])\s*\n\s*([A-ZÁÉÍÓÚÑ]{2,})', r'\1\2', text)
        
        # Fix uppercase words split across lines within a hyphenated name
        # Pattern: "SMITH-LE\nWIS" -> "SMITH-LEWIS" (word continues after hyphen)
        # Must have hyphen before the break to indicate word continuation
        text = re.sub(r'([A-ZÁÉÍÓÚÑ]+)-([A-ZÁÉÍÓÚÑ]{1,3})\s*\n\s*([A-ZÁÉÍÓÚÑ]+)', r'\1-\2\3', text)
        
        # Fix hyphenated words split at the hyphen itself
        # Pattern: "SMITH-\nJONES" -> "SMITH-JONES"  
        text = re.sub(r'([A-Za-záéíóúñÁÉÍÓÚÑ]+)-\s*\n\s*([A-Za-záéíóúñÁÉÍÓÚÑ]+)', r'\1-\2', text)
        
        return text
    
    def extract_from_pdf_text(
        self, 
        full_text: str, 
        metadata: Dict[str, Any]
    ) -> RegexExtractionResult:
        """
        Main extraction method - extracts all available data from PDF text and metadata.
        
        Args:
            full_text: Full text content of the PDF
            metadata: Metadata dict from CSV (case_number, case_title, year, month, etc.)
            
        Returns:
            RegexExtractionResult with all extracted data
        """
        result = RegexExtractionResult()
        
        # Normalize text once for all extractions
        normalized = self._normalize_text(full_text)
        
        # === METADATA (no regex needed) ===
        result.case_number = str(metadata.get('case_number', ''))
        result.case_name = metadata.get('case_title', metadata.get('case_name', ''))
        result.year = metadata.get('year')
        result.month = metadata.get('month')
        result.pdf_url = metadata.get('pdf_url', '')
        result.case_info_url = metadata.get('case_info_url', '')
        
        if metadata.get('file_date'):
            result.decision_date = self._parse_date(metadata['file_date'])
        
        # Determine publication status from metadata
        file_contains = str(metadata.get('file_contains', '')).lower()
        result.publication_status = 'unpublished' if 'unpublished' in file_contains else 'published'
        
        # === HEADER EXTRACTION (first 3000 chars) ===
        header = normalized[:3000]
        
        # Court level
        if self.supreme_court_re.search(header):
            result.court_level = 'supreme_court'
        elif self.appeals_court_re.search(header):
            result.court_level = 'court_of_appeals'
        else:
            result.court_level = 'unknown'
        
        # Division
        div_match = self.division_re.search(header)
        if div_match:
            div = div_match.group(1).upper()
            result.division = {
                'ONE': 'division_one', '1': 'division_one', 'I': 'division_one',
                'TWO': 'division_two', '2': 'division_two', 'II': 'division_two',
                'THREE': 'division_three', '3': 'division_three', 'III': 'division_three',
            }.get(div)
        
        # Filed date
        filed_match = self.filed_date_re.search(header)
        if filed_match:
            result.filed_date = self._parse_date(filed_match.group(1))
            if not result.decision_date:
                result.decision_date = result.filed_date
        
        # En banc
        result.en_banc = bool(self.en_banc_re.search(header))
        
        # === JUDGE EXTRACTION ===
        result.judges = self._extract_judges(normalized, header)
        
        # === PARTY EXTRACTION (from case title) ===
        result.parties = self._extract_parties(result.case_name, header)
        
        # === OUTCOME (last 5000 chars) ===
        footer = normalized[-5000:] if len(normalized) > 5000 else normalized
        result.appeal_outcome, result.outcome_detail = self._extract_outcome(footer)
        
        # === CITATIONS (full text, single pass) ===
        result.citations = self._extract_citations(normalized)
        result.statutes = self._extract_statutes(normalized)
        
        # === COUNTY ===
        county_match = self.county_re.search(normalized)
        if county_match:
            result.county = county_match.group(1).title()
        
        logger.info(f"Regex extraction: {result.case_number} - "
                   f"{len(result.judges)} judges, {len(result.citations)} citations, "
                   f"{len(result.statutes)} RCWs, outcome={result.appeal_outcome}")
        
        return result
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string efficiently"""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Try common formats first
        for fmt in ("%b. %d, %Y", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Fallback: extract components with regex
        match = self.date_components_re.search(date_str)
        if match:
            month_str, day, year = match.groups()
            month = self.MONTH_MAP.get(month_str.lower()[:3])
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass
        return None
    
    def _extract_judges(self, normalized: str, header: str) -> List[ExtractedJudge]:
        """Extract judges with roles"""
        judges = []
        seen = set()
        
        # 1. Find author from header (UPPERCASE, J.-)
        author_matches = self.author_re.findall(header)
        for name in author_matches:
            # Convert to title case, handle hyphenated names
            name_title = '-'.join(p.title() for p in name.split('-'))
            # Must be at least 3 chars per part (avoid partial matches)
            if all(len(p) >= 3 for p in name_title.split('-')):
                if name_title not in seen:
                    judges.append(ExtractedJudge(name=name_title, role='author'))
                    seen.add(name_title)
                    break
        
        # 2. Find concurring judges (full text)
        for match in self.concurring_re.finditer(normalized):
            name = match.group(1).title()
            if len(name) >= 3 and name not in seen:
                judges.append(ExtractedJudge(name=name, role='concurring'))
                seen.add(name)
        
        # 3. Find dissenting judges (full text)
        for match in self.dissenting_re.finditer(normalized):
            name = match.group(1).title()
            if len(name) >= 3 and name not in seen:
                judges.append(ExtractedJudge(name=name, role='dissenting'))
                seen.add(name)
        
        # 4. Check for pro tempore (update existing or add new)
        for match in self.pro_tem_re.finditer(normalized):
            name = match.group(1).title()
            if len(name) >= 3:
                # Check if already in list
                existing = next((j for j in judges if j.name == name), None)
                if existing:
                    if 'pro_tempore' not in existing.role:
                        existing.role += '_pro_tempore'
                elif name not in seen:
                    judges.append(ExtractedJudge(name=name, role='pro_tempore'))
                    seen.add(name)
        
        return judges
    
    def _extract_parties(self, case_title: str, header: str) -> List[ExtractedParty]:
        """Extract parties from case title"""
        if not case_title:
            return []
        
        # Split by " v. " or " vs. " or " v "
        parts = re.split(r'\s+v\.?\s+', case_title, maxsplit=1, flags=re.I)
        
        if len(parts) != 2:
            return [ExtractedParty(name=case_title.strip(), role='petitioner')]
        
        party1 = parts[0].strip()
        party2 = parts[1].strip()
        
        # Determine roles from header text
        header_lower = header.lower()
        
        if 'petitioner' in header_lower:
            return [
                ExtractedParty(name=party1, role='petitioner'),
                ExtractedParty(name=party2, role='respondent')
            ]
        elif 'appellant' in header_lower:
            return [
                ExtractedParty(name=party1, role='appellant'),
                ExtractedParty(name=party2, role='respondent')
            ]
        else:
            # Default to appellant/respondent
            return [
                ExtractedParty(name=party1, role='appellant'),
                ExtractedParty(name=party2, role='respondent')
            ]
    
    def _extract_outcome(self, footer: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract appeal outcome from footer text"""
        for pattern, outcome, detail in self.outcome_patterns:
            if pattern.search(footer):
                return outcome, detail
        return None, None
    
    def _extract_citations(self, text: str) -> List[ExtractedCitation]:
        """Extract Washington case citations in single pass"""
        citations = []
        seen = set()
        
        for match in self.wa_citation_re.finditer(text):
            volume, reporter, page = match.groups()
            # Normalize reporter format
            reporter_norm = reporter.replace(' ', '').replace('.', '')
            if 'App2d' in reporter_norm:
                reporter_clean = 'Wn. App. 2d'
            elif 'App' in reporter_norm:
                reporter_clean = 'Wn. App.'
            elif 'Wn2d' in reporter_norm or 'Wash2d' in reporter_norm:
                reporter_clean = 'Wn.2d'
            elif 'Wash' in reporter_norm:
                reporter_clean = 'Wash.'
            else:
                reporter_clean = 'Wn.2d'
            
            full = f"{volume} {reporter_clean} {page}"
            if full not in seen:
                citations.append(ExtractedCitation(
                    volume=volume, reporter=reporter_clean, 
                    page=page, full_citation=full
                ))
                seen.add(full)
        
        return citations
    
    def _extract_statutes(self, text: str) -> List[ExtractedStatute]:
        """Extract RCW statutes"""
        statutes = []
        seen = set()
        
        for match in self.rcw_re.finditer(text):
            rcw = match.group(1).rstrip('.')
            if rcw not in seen:
                statutes.append(ExtractedStatute(rcw_number=rcw, full_text=f"RCW {rcw}"))
                seen.add(rcw)
        
        return statutes


# Convenience function
def extract_case_data_regex(full_text: str, metadata: Dict[str, Any]) -> RegexExtractionResult:
    """
    Extract case data using regex (fast, free).
    Drop-in replacement for AI extraction.
    """
    extractor = RegexExtractor()
    return extractor.extract_from_pdf_text(full_text, metadata)
