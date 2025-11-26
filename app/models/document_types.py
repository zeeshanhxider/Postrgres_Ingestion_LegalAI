from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


# ============================================================================
# Enums for constrained values
# ============================================================================

class DocumentRole(str, Enum):
    """Document authority source - separates Authority from Argument from Fact"""
    COURT = "court"           # Rulings - the logic source
    PARTY = "party"           # Briefs - the arguments
    EVIDENCE = "evidence"     # Transcripts, exhibits - the facts
    ADMINISTRATIVE = "administrative"  # Docket sheets, procedural docs


class DocumentCategory(str, Enum):
    """UI grouping for frontend display"""
    COURT_DECISIONS = "Court Decisions"
    PARTY_BRIEFS = "Party Briefs"
    EVIDENCE = "Evidence"
    ADMINISTRATIVE = "Administrative"


class ProcessingStrategy(str, Enum):
    """Backend routing - tells which pipeline/table to use"""
    CASE_OUTCOME = "case_outcome"       # Extract winners, populate cases outcome fields
    BRIEF_EXTRACTION = "brief_extraction"  # Populate briefs table with filing_party, responds_to
    EVIDENCE_INDEXING = "evidence_indexing"  # Chunk and vector embed, skip briefs table
    TEXT_ONLY = "text_only"             # Basic indexing only


class DocumentTypeSlug(str, Enum):
    """V1 Supported document type slugs"""
    # Rulings (Court)
    APPELLATE_OPINION = "appellate_opinion"
    TRIAL_COURT_ORDER = "trial_court_order"
    FINAL_JUDGMENT = "final_judgment"
    # Briefs (Party)
    OPENING_BRIEF = "opening_brief"
    RESPONDENT_BRIEF = "respondent_brief"
    REPLY_BRIEF = "reply_brief"
    # Evidence
    TRANSCRIPT = "transcript"
    EXHIBIT = "exhibit"


# ============================================================================
# Pydantic Models
# ============================================================================

class DocumentTypeBase(BaseModel):
    """Base document type with all required fields for the Traffic Cop system"""
    document_type: str = Field(..., description="Machine-readable document type slug (e.g., 'appellate_opinion')")
    description: Optional[str] = Field(None, description="Human-readable description of the document type")
    role: DocumentRole = Field(..., description="Document authority source: court, party, evidence, administrative")
    category: DocumentCategory = Field(..., description="UI grouping label for frontend display")
    has_decision: bool = Field(False, description="Whether this document declares a winner (True for opinions/orders)")
    is_adversarial: bool = Field(False, description="Whether document is biased/argumentative (True for briefs)")
    processing_strategy: ProcessingStrategy = Field(..., description="Backend routing: which pipeline to use")
    display_order: int = Field(100, description="Sort order for UI display within category")


class DocumentTypeCreate(DocumentTypeBase):
    """Schema for creating a new document type"""
    pass


class DocumentTypeUpdate(BaseModel):
    """Schema for updating an existing document type - all fields optional"""
    document_type: Optional[str] = None
    description: Optional[str] = None
    role: Optional[DocumentRole] = None
    category: Optional[DocumentCategory] = None
    has_decision: Optional[bool] = None
    is_adversarial: Optional[bool] = None
    processing_strategy: Optional[ProcessingStrategy] = None
    display_order: Optional[int] = None


class DocumentType(DocumentTypeBase):
    """Full document type with database-generated fields"""
    document_type_id: int = Field(..., description="Unique document type identifier")
    created_at: datetime = Field(..., description="Record creation timestamp")

    class Config:
        from_attributes = True


class DocumentTypeResponse(DocumentType):
    """Response schema for API endpoints"""
    pass


# ============================================================================
# Helper functions for processing strategy routing
# ============================================================================

def get_processing_strategy(doc_type_slug: str) -> ProcessingStrategy:
    """
    Get the processing strategy for a given document type slug.
    Used by the ingestion pipeline to route documents to the correct processor.
    """
    strategy_map = {
        # Court decisions -> extract outcomes
        "appellate_opinion": ProcessingStrategy.CASE_OUTCOME,
        "trial_court_order": ProcessingStrategy.CASE_OUTCOME,
        "final_judgment": ProcessingStrategy.CASE_OUTCOME,
        # Party briefs -> populate briefs table
        "opening_brief": ProcessingStrategy.BRIEF_EXTRACTION,
        "respondent_brief": ProcessingStrategy.BRIEF_EXTRACTION,
        "reply_brief": ProcessingStrategy.BRIEF_EXTRACTION,
        # Evidence -> chunk and embed only
        "transcript": ProcessingStrategy.EVIDENCE_INDEXING,
        "exhibit": ProcessingStrategy.EVIDENCE_INDEXING,
    }
    return strategy_map.get(doc_type_slug, ProcessingStrategy.TEXT_ONLY)


def is_brief_type(doc_type_slug: str) -> bool:
    """Check if a document type should populate the briefs table"""
    return doc_type_slug in ("opening_brief", "respondent_brief", "reply_brief")


def is_court_decision(doc_type_slug: str) -> bool:
    """Check if a document type is a court decision with outcomes"""
    return doc_type_slug in ("appellate_opinion", "trial_court_order", "final_judgment")


def is_evidence(doc_type_slug: str) -> bool:
    """Check if a document type is evidence (neutral facts)"""
    return doc_type_slug in ("transcript", "exhibit")
