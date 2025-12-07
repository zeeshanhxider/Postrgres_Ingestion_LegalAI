"""
Data Models for the Legal Case Pipeline
Simple, clean dataclasses - no complex Pydantic validation.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, date


@dataclass
class CaseMetadata:
    """
    Metadata from CSV - these fields are populated directly without extraction.
    Maps to columns from: metadata.csv
    """
    # Direct from CSV
    opinion_type: str = ""              # "Supreme Court" or "Court of Appeals"
    publication_status: str = ""        # "Published", "Published in Part"
    year: Optional[int] = None
    month: str = ""
    file_date: Optional[date] = None    # Parsed from "Jan. 16, 2025"
    case_number: str = ""               # "102,586-6"
    division: str = ""                  # "I", "II", "III" or empty for Supreme Court
    case_title: str = ""                # "Pub. Util. Dist. No. 1 of Snohomish County v. State"
    file_contains: str = ""             # "Majority Opinion", "Maj., and Con. Opinions"
    case_info_url: str = ""
    pdf_url: str = ""
    pdf_filename: str = ""
    download_status: str = ""
    scraped_at: Optional[datetime] = None
    
    # Derived from metadata
    court_level: str = ""               # Derived: "Supreme Court" or "Court of Appeals" from opinion_type
    

@dataclass
class Party:
    """A party involved in the case."""
    name: str
    role: str                           # "Appellant", "Respondent", "Petitioner", etc.
    party_type: Optional[str] = None    # "Individual", "Corporation", "Government", etc.


@dataclass
class Attorney:
    """An attorney representing a party."""
    name: str
    representing: str                   # Which party they represent
    firm_name: Optional[str] = None
    firm_address: Optional[str] = None


@dataclass
class Judge:
    """A judge on the case."""
    name: str
    role: str                           # "Author", "Concurring", "Dissenting"


@dataclass 
class Citation:
    """A case citation referenced in the opinion."""
    full_citation: str                  # "123 Wn.2d 456"
    case_name: Optional[str] = None     # "State v. Smith"
    relationship: Optional[str] = None  # "followed", "distinguished", "overruled"


@dataclass
class Statute:
    """A statute (RCW) cited in the opinion."""
    citation: str                       # "RCW 49.62.070"
    title: Optional[str] = None         # Optional description


@dataclass
class Issue:
    """A legal issue addressed in the case."""
    category: str                       # "Criminal Law", "Civil Procedure", etc.
    subcategory: str                    # "Search & Seizure", "Summary Judgment", etc.
    summary: str                        # Brief description of the issue
    outcome: Optional[str] = None       # "affirmed", "reversed", etc.
    winner: Optional[str] = None        # "Appellant", "Respondent"


@dataclass
class ExtractedCase:
    """
    Complete extracted case data.
    Combines metadata (from CSV) + LLM extraction (from PDF text).
    """
    # === FROM METADATA (CSV) - Direct population ===
    metadata: CaseMetadata = field(default_factory=CaseMetadata)
    
    # === FROM LLM EXTRACTION ===
    # Case overview
    summary: str = ""                   # AI-generated summary
    case_type: str = ""                 # "criminal", "civil", "family", etc.
    
    # Court info (LLM extracts these from PDF)
    county: Optional[str] = None        # "King", "Pierce", etc.
    trial_court: Optional[str] = None   # "King County Superior Court"
    trial_judge: Optional[str] = None   # Name of trial court judge
    source_docket_number: Optional[str] = None  # Lower court case number
    
    # Outcome
    appeal_outcome: Optional[str] = None    # "affirmed", "reversed", "remanded"
    outcome_detail: Optional[str] = None    # "affirmed in part, reversed in part"
    winner_legal_role: Optional[str] = None     # "Plaintiff", "Defendant", "Appellant", "Respondent"
    winner_personal_role: Optional[str] = None  # "Employee", "Employer", "Landlord", etc.
    
    # Entities (all from LLM)
    parties: List[Party] = field(default_factory=list)
    attorneys: List[Attorney] = field(default_factory=list)
    judges: List[Judge] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    statutes: List[Statute] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    
    # Full text (from PDF)
    full_text: str = ""
    page_count: int = 0
    source_file_path: Optional[str] = None  # Absolute path to PDF file
    
    # Embedding
    full_embedding: Optional[List[float]] = None  # 1024-dim vector for RAG
    
    # Processing info
    extraction_timestamp: Optional[datetime] = None
    llm_model: str = ""
    extraction_successful: bool = False
    error_message: Optional[str] = None
