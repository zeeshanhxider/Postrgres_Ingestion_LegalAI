"""
Legal Case Pydantic Models
Proven models designed to work with our database schema and AI extraction.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum
import re

# =============================================================================
# ENUMS - Keep simple and working
# =============================================================================

class CourtLevel(str, Enum):
    APPEALS = "Appeals"
    SUPREME = "Supreme"

class District(str, Enum):
    DIVISION_I = "Division I"
    DIVISION_II = "Division II"
    DIVISION_III = "Division III"
    NA = "N/A"

class PublicationStatus(str, Enum):
    PUBLISHED = "Published"
    UNPUBLISHED = "Unpublished"
    PARTIALLY_PUBLISHED = "Partially Published"
    
    # Also accept lowercase versions
    PUBLISHED_LOWER = "published"
    UNPUBLISHED_LOWER = "unpublished"
    
    # Handle common variations
    PUBLISHED_ONLY = "Published Only"
    UNPUBLISHED_ONLY = "Unpublished Only"
    PARTIALLY_PUBLISHED_ONLY = "Partially Published Only"

class LegalRole(str, Enum):
    APPELLANT = "Appellant"
    RESPONDENT = "Respondent"
    PETITIONER = "Petitioner"
    THIRD_PARTY = "Third Party"
    
    # Also accept lowercase versions
    APPELLANT_LOWER = "appellant"
    RESPONDENT_LOWER = "respondent"
    PETITIONER_LOWER = "petitioner"
    
    # Handle compound roles
    APPELLANT_CROSS_RESPONDENT = "Appellant/Cross Respondent"
    RESPONDENT_CROSS_APPELLANT = "Respondent/Cross Appellant"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class PersonalRole(str, Enum):
    # Family law roles
    HUSBAND = "Husband"
    WIFE = "Wife"
    PARENT = "Parent"
    CHILD = "Child"
    OTHER = "Other"
    ESTATE = "Estate"
    
    # Universal roles for non-divorce cases
    CORPORATION = "Corporation"
    GOVERNMENT = "Government"
    INDIVIDUAL = "Individual"
    
    # Also accept lowercase versions
    HUSBAND_LOWER = "husband"
    WIFE_LOWER = "wife"
    PARENT_LOWER = "parent"
    CHILD_LOWER = "child"
    OTHER_LOWER = "other"
    ESTATE_LOWER = "estate"
    CORPORATION_LOWER = "corporation"
    GOVERNMENT_LOWER = "government"
    INDIVIDUAL_LOWER = "individual"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class JudgeRole(str, Enum):
    AUTHORED_BY = "Authored by"
    CONCURRING = "Concurring"
    DISSENTING = "Dissenting"
    JOINING = "Joining"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class AttorneyType(str, Enum):
    ATTORNEY = "Attorney"
    COUNSEL = "Counsel"
    PUBLIC_DEFENDER = "Public Defender"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class DecisionStage(str, Enum):
    TRIAL = "trial"
    APPEAL = "appeal"
    
    # Also accept capitalized versions
    TRIAL_CAP = "Trial"
    APPEAL_CAP = "Appeal"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class DecisionWinner(str, Enum):
    HUSBAND = "husband"
    WIFE = "wife"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    APPELLANT = "appellant"
    SPLIT = "split"
    REMANDED = "remanded"
    DISMISSED = "dismissed"
    
    # Also accept capitalized versions
    HUSBAND_CAP = "Husband"
    WIFE_CAP = "Wife"
    PETITIONER_CAP = "Petitioner"
    RESPONDENT_CAP = "Respondent"
    APPELLANT_CAP = "Appellant"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class AppealOutcome(str, Enum):
    REVERSED = "reversed"
    AFFIRMED = "affirmed"
    REMANDED = "remanded"
    DISMISSED = "dismissed"
    PARTIAL = "partial"
    
    # Handle compound outcomes
    REMANDED_PARTIAL = "remanded_partial"
    REMANDED_FULL = "remanded_full"
    
    # Also accept capitalized versions
    REVERSED_CAP = "Reversed"
    AFFIRMED_CAP = "Affirmed"
    REMANDED_CAP = "Remanded"
    DISMISSED_CAP = "Dismissed"
    PARTIAL_CAP = "Partial"
    
    # Handle split outcomes
    SPLIT = "split"
    SPLIT_CAP = "Split"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class OverallCaseOutcome(str, Enum):
    AFFIRMED = "affirmed"
    REVERSED = "reversed"
    REMANDED_FULL = "remanded_full"
    REMANDED_PARTIAL = "remanded_partial"
    DISMISSED = "dismissed"
    SPLIT = "split"
    PARTIAL = "partial"
    OTHER = "other"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class ArgumentSide(str, Enum):
    APPELLANT = "Appellant"
    RESPONDENT = "Respondent"
    COURT = "Court"
    
    # Also accept lowercase versions
    APPELLANT_LOWER = "appellant"
    RESPONDENT_LOWER = "respondent"
    COURT_LOWER = "court"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class PrecedentRelationship(str, Enum):
    FOLLOWED = "followed"
    DISTINGUISHED = "distinguished"
    OVERRULED = "overruled"
    CITED = "cited"
    RELIED_UPON = "relied upon"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

# =============================================================================
# WASHINGTON STATE COURT CASE CATEGORIZATION - UNIVERSAL
# =============================================================================

class IssueCategory(str, Enum):
    """Top-level categories for Washington State court cases (all types)"""
    # UNIVERSAL CATEGORIES (Non-Divorce)
    CRIMINAL_LAW = "Criminal Law & Procedure"
    CONSTITUTIONAL_LAW = "Constitutional Law"
    CIVIL_PROCEDURE = "Civil Procedure"
    EVIDENCE = "Evidence"
    CONTRACTS = "Contracts"
    TORTS = "Torts / Personal Injury"
    PROPERTY_LAW = "Property Law"
    EMPLOYMENT_LAW = "Employment Law"
    ESTATE_PROBATE = "Estate & Probate"
    ADMINISTRATIVE_LAW = "Administrative Law"
    BUSINESS_COMMERCIAL = "Business & Commercial"
    INSURANCE_LAW = "Insurance Law"
    ENVIRONMENTAL_LAW = "Environmental Law"
    
    # FAMILY LAW / DIVORCE CATEGORIES
    FAMILY_LAW = "Family Law"
    SPOUSAL_SUPPORT = "Spousal Support / Maintenance"
    CHILD_SUPPORT = "Child Support"
    PARENTING_PLAN = "Parenting Plan / Custody / Visitation"
    PROPERTY_DIVISION = "Property Division / Debt Allocation"
    
    # GENERAL CATEGORIES (applicable to all case types)
    ATTORNEY_FEES = "Attorney Fees & Costs"
    PROCEDURAL_EVIDENTIARY = "Procedural & Evidentiary Issues"
    JURISDICTION_VENUE = "Jurisdiction & Venue"
    ENFORCEMENT_CONTEMPT = "Enforcement & Contempt Orders"
    MODIFICATION_ORDERS = "Modification Orders"
    MISCELLANEOUS = "Miscellaneous / Unclassified"
    
    # Flexible fallbacks
    UNKNOWN = "Unknown"

class SpousalSupportSubcategory(str, Enum):
    """Spousal Support / Maintenance subcategories"""
    DURATION = "Duration (temp vs. permanent)"
    AMOUNT_CALCULATION = "Amount calculation errors"
    IMPUTED_INCOME = "Imputed income disputes"
    STATUTORY_FACTORS = "Failure to consider statutory factors"
    EVIDENCE_INTERPRETATION = "Misinterpretation of evidence"

class ChildSupportSubcategory(str, Enum):
    """Child Support subcategories"""
    INCOME_DETERMINATION = "Income determination / imputation"
    DEVIATIONS = "Deviations from standard calculation"
    EXPENSE_ALLOCATION = "Allocation of expenses"
    RETROACTIVE_SUPPORT = "Retroactive support"
    ARREARS_INTEREST = "Support arrears & interest"

class ParentingPlanSubcategory(str, Enum):
    """Parenting Plan / Custody / Visitation subcategories"""
    RESIDENTIAL_SCHEDULE = "Residential schedule"
    DECISION_MAKING = "Decision-making authority"
    RELOCATION = "Relocation disputes"
    RESTRICTIONS = "Restrictions (DV, SA, etc.)"
    BEST_INTEREST_FACTORS = "Failure to follow best-interest factors"

class PropertyDivisionSubcategory(str, Enum):
    """Property Division / Debt Allocation subcategories"""
    ASSET_VALUATION = "Valuation of assets"
    CHARACTERIZATION = "Characterization (community vs. separate)"
    DIVISION_FAIRNESS = "Division fairness"
    OMITTED_ASSETS = "Omitted assets or debts"
    TAX_CONSEQUENCES = "Tax consequences ignored"

class AttorneyFeesSubcategory(str, Enum):
    """Attorney Fees & Costs subcategories"""
    FEE_AWARDS = "Fee awards"
    SANCTIONS = "Sanctions"
    IMPROPER_BASIS = "Improper basis for award"

class ProceduralEvidentiary(str, Enum):
    """Procedural & Evidentiary Issues subcategories"""
    ABUSE_DISCRETION = "Abuse of discretion"
    FINDINGS_CONCLUSIONS = "Failure to enter findings/conclusions"
    EVIDENTIARY_RULINGS = "Improper evidentiary rulings"
    DUE_PROCESS = "Denial of due process"
    JUDICIAL_BIAS = "Judicial bias"

class JurisdictionVenueSubcategory(str, Enum):
    """Jurisdiction & Venue subcategories"""
    SUBJECT_MATTER = "Subject matter jurisdiction"
    PERSONAL_JURISDICTION = "Personal jurisdiction"
    IMPROPER_VENUE = "Improper venue"

class EnforcementContemptSubcategory(str, Enum):
    """Enforcement & Contempt Orders subcategories"""
    WILLFULNESS_FINDINGS = "Willfulness findings"
    SANCTIONS = "Sanctions"
    PURGE_CONDITIONS = "Purge conditions"

class ModificationOrdersSubcategory(str, Enum):
    """Modification Orders subcategories"""
    SUBSTANTIAL_CHANGE = "Substantial change of circumstances"
    IMPROPER_APPLICATION = "Improper application of statute"
    RETROACTIVE_APPLICATION = "Retroactive application"

class MiscellaneousSubcategory(str, Enum):
    """Miscellaneous / Unclassified subcategories"""
    RARE_ISSUES = "Catch-all rare issues"

# =============================================================================
# LEGAL CASE MODELS
# =============================================================================

class CaseModel(BaseModel):
    """Legal case metadata model"""
    case_file_id: Optional[str] = Field(description="Legal case file number from document (e.g., '73404-1')", default=None)
    title: str = Field(description="Case title without asterisk")
    court_level: CourtLevel = Field(description="Court level - Appeals or Supreme")
    court: str = Field(description="Full court name")
    district: Optional[District] = Field(description="Division", default=District.NA)
    county: Optional[str] = Field(description="County name", default=None)
    docket_number: Optional[str] = Field(description="Appeals court docket number", default=None)
    source_docket_number: Optional[str] = Field(description="Trial court docket number", default=None)
    trial_judge: Optional[str] = Field(description="Trial judge name with title", default=None)
    
    # Date fields - look at document timeline and bottom sections
    filing_date: Optional[str] = Field(description="Filing date YYYY-MM-DD", default=None)
    oral_argument_date: Optional[str] = Field(description="Oral argument date YYYY-MM-DD", default=None)
    
    # Case type classification
    case_type: Optional[str] = Field(description="Case type classification (divorce, marriage, criminal, civil, family, business, etc.)", default=None)
    
    # Trial court timeline
    trial_start_date: Optional[str] = Field(description="Trial court proceedings start date YYYY-MM-DD", default=None)
    trial_end_date: Optional[str] = Field(description="Trial court decision date YYYY-MM-DD", default=None)
    trial_published_date: Optional[str] = Field(description="Trial court decision published date YYYY-MM-DD", default=None)
    
    # Appeal court timeline  
    appeal_start_date: Optional[str] = Field(description="Appeal filing date YYYY-MM-DD", default=None)
    appeal_end_date: Optional[str] = Field(description="Appeal decision date YYYY-MM-DD", default=None)
    appeal_published_date: Optional[str] = Field(description="Appeal decision published date YYYY-MM-DD", default=None)
    
    # Metadata
    published: PublicationStatus = Field(description="Publication status")
    summary: str = Field(description="2-3 sentence case summary")
    overall_case_outcome: Optional[OverallCaseOutcome] = Field(description="Overall case outcome", default=None)
    
    # Case-level winner information (derived from issues)
    winner_legal_role: Optional[DecisionWinner] = Field(description="Overall case winner by legal role", default=None)
    winner_personal_role: Optional[PersonalRole] = Field(description="Overall case winner by personal role", default=None)
    appeal_outcome: Optional[AppealOutcome] = Field(description="Overall appeal outcome", default=None)

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if not v or v.strip() == '':
            raise ValueError("Case title cannot be empty")
        title = re.sub(r'\*', '', v.strip())
        title = re.sub(r'\s+', ' ', title)
        return title.title()

    @field_validator('published')
    @classmethod
    def validate_published(cls, v):
        """Handle any publication status input gracefully without failing"""
        try:
            if not v:
                return PublicationStatus.PUBLISHED  # Default to published
            
            v_clean = str(v).strip()
            if not v_clean:
                return PublicationStatus.PUBLISHED
            
            # Try to match existing enum values first
            for status in PublicationStatus:
                if v_clean.lower() == status.value.lower():
                    return status
            
            # Handle common variations
            v_lower = v_clean.lower()
            if 'published' in v_lower and 'only' in v_lower:
                return PublicationStatus.PUBLISHED
            elif 'unpublished' in v_lower and 'only' in v_lower:
                return PublicationStatus.UNPUBLISHED
            elif 'partially' in v_lower and 'published' in v_lower:
                return PublicationStatus.PARTIALLY_PUBLISHED
            elif 'published' in v_lower:
                return PublicationStatus.PUBLISHED
            elif 'unpublished' in v_lower:
                return PublicationStatus.UNPUBLISHED
            else:
                # Default to published if we can't determine
                return PublicationStatus.PUBLISHED
                
        except Exception:
            # If anything goes wrong, return published instead of failing
            return PublicationStatus.PUBLISHED

class JudgeModel(BaseModel):
    """Appeals court judge model"""
    judge_name: str = Field(description="Judge name without title")
    role: JudgeRole = Field(description="Judge role - Authored by, Concurring, Dissenting")

    @field_validator('judge_name')
    @classmethod
    def validate_judge_name(cls, v):
        if not v or v.strip() == '':
            raise ValueError("Judge name cannot be empty")
        return re.sub(r'\s+', ' ', v.strip()).title()

class AttorneyModel(BaseModel):
    """Legal attorney model"""
    name: str = Field(description="Attorney name")
    firm_name: Optional[str] = Field(description="Law firm name", default=None)
    firm_address: Optional[str] = Field(description="Complete firm address", default=None)
    representing: LegalRole = Field(description="Who they represent - Appellant or Respondent")
    attorney_type: AttorneyType = Field(description="Attorney type", default=AttorneyType.ATTORNEY)

    @field_validator('name')
    @classmethod
    def validate_attorney_name(cls, v):
        if not v or v.strip() == '':
            raise ValueError("Attorney name cannot be empty")
        return re.sub(r'\s+', ' ', v.strip()).title()

    @field_validator('representing')
    @classmethod
    def validate_representing(cls, v):
        """Handle any legal role input gracefully without failing"""
        if not v or v is None:
            return LegalRole.UNKNOWN
        
        try:
            v_clean = str(v).strip()
            if not v_clean:
                return LegalRole.UNKNOWN
            
            # Try to match existing enum values first
            for role in LegalRole:
                if v_clean.lower() == role.value.lower():
                    return role
            
            # Handle compound roles by taking the primary role
            if 'appellant' in v_clean.lower() and 'cross' in v_clean.lower():
                return LegalRole.APPELLANT
            elif 'respondent' in v_clean.lower() and 'cross' in v_clean.lower():
                return LegalRole.RESPONDENT
            
            # Handle descriptive attorney representations
            v_lower = v_clean.lower()
            
            # Check for appellant patterns
            if any(pattern in v_lower for pattern in ['appellant', 'appellants']):
                return LegalRole.APPELLANT
            # Check for respondent patterns  
            elif any(pattern in v_lower for pattern in ['respondent', 'respondents']):
                return LegalRole.RESPONDENT
            # Check for petitioner patterns
            elif any(pattern in v_lower for pattern in ['petitioner', 'petitioners']):
                return LegalRole.PETITIONER
            # Check for third party patterns
            elif any(pattern in v_lower for pattern in ['third party', 'third-party']):
                return LegalRole.THIRD_PARTY
            # Check for guardian ad litem (usually represents a party, default to appellant)
            elif 'guardian ad litem' in v_lower:
                return LegalRole.APPELLANT
            else:
                # Default to unknown if we can't determine
                return LegalRole.UNKNOWN
                
        except Exception:
            # If anything goes wrong, return unknown instead of failing
            return LegalRole.UNKNOWN

class PartyModel(BaseModel):
    """Legal party model with role mapping"""
    name: str = Field(description="Person name")
    legal_role: LegalRole = Field(description="Legal role - Appellant, Respondent, etc.")
    personal_role: Optional[PersonalRole] = Field(description="Personal role - Husband, Wife, etc.", default=None)

    @field_validator('name')
    @classmethod
    def validate_party_name(cls, v):
        if not v or v.strip() == '':
            raise ValueError("Party name cannot be empty")
        return re.sub(r'\s+', ' ', v.strip()).title()

    @field_validator('legal_role')
    @classmethod
    def validate_legal_role(cls, v):
        """Handle compound legal roles like 'Appellant/Cross Respondent'"""
        if not v:
            return v
        
        v_clean = v.strip()
        
        # Handle compound roles by taking the primary role
        if 'Appellant/Cross Respondent' in v_clean or 'appellant/cross respondent' in v_clean.lower():
            return LegalRole.APPELLANT
        elif 'Respondent/Cross Appellant' in v_clean or 'respondent/cross appellant' in v_clean.lower():
            return LegalRole.RESPONDENT
        else:
            # If it's already a valid enum value, return it
            try:
                return LegalRole(v_clean)
            except ValueError:
                # Default to appellant if we can't determine
                return LegalRole.APPELLANT

    @field_validator('personal_role')
    @classmethod
    def validate_personal_role(cls, v):
        """Handle personal role validation gracefully, allowing None for non-family law cases"""
        try:
            # Explicitly handle None values
            if v is None or v == 'None' or v == '':
                return None
            
            # Handle string values
            if isinstance(v, str):
                v_clean = v.strip()
                if not v_clean or v_clean.lower() in ['none', 'null', '']:
                    return None
            else:
                v_clean = str(v)
            
            # Try to match existing enum values first
            for role in PersonalRole:
                if v_clean.lower() == role.value.lower():
                    return role
            
            # Handle common variations
            v_lower = v_clean.lower()
            if 'husband' in v_lower:
                return PersonalRole.HUSBAND
            elif 'wife' in v_lower:
                return PersonalRole.WIFE
            elif 'parent' in v_lower:
                return PersonalRole.PARENT
            elif 'estate' in v_lower:
                return PersonalRole.ESTATE
            else:
                # Default to Other if we can't determine
                return PersonalRole.OTHER
                
        except Exception:
            # If anything goes wrong, return None instead of failing
            return None

class IssueDecisionModel(BaseModel):
    """Washington State divorce appeals issue and decision model with hierarchical categorization"""
    
    # Washington State divorce appeals hierarchy (from ChatGPT conversation)
    category: IssueCategory = Field(description="Top-level category: Spousal Support, Child Support, etc.")
    subcategory: str = Field(description="Mid-level subcategory: Duration, Income determination, etc.")
    rcw_reference: Optional[str] = Field(description="Washington RCW statute reference (e.g., 'RCW 26.09.090')", default=None)
    keywords: Optional[List[str]] = Field(description="Common appeal keywords for this issue", default=None)
    
    # Issue details
    issue_summary: str = Field(description="Specific issue description from the case")
    
    # Decision details
    decision_stage: Optional[DecisionStage] = Field(description="Court stage - trial or appeal", default=None)
    decision_summary: Optional[str] = Field(description="What the court decided on this issue", default=None)
    appeal_outcome: Optional[AppealOutcome] = Field(description="Appeal result for this issue", default=None)
    winner_legal_role: Optional[DecisionWinner] = Field(description="Winner by legal role (appellant/respondent)", default=None)
    winner_personal_role: Optional[PersonalRole] = Field(description="Winner by personal role (husband/wife)", default=None)

    @field_validator('issue_summary')
    @classmethod
    def validate_issue_summary(cls, v):
        if not v or v.strip() == '':
            raise ValueError("Issue summary cannot be empty")
        return re.sub(r'\s+', ' ', v.strip())

    @field_validator('decision_summary')
    @classmethod
    def validate_decision_summary(cls, v):
        if v and v.strip():
            return re.sub(r'\s+', ' ', v.strip())
        return v

    @field_validator('appeal_outcome')
    @classmethod
    def validate_appeal_outcome(cls, v):
        """Handle any appeal outcome input gracefully without failing"""
        try:
            if v is None:
                return None
            
            v_clean = str(v).strip() if v else ""
            if not v_clean:
                return None
            
            # Try to match existing enum values first
            for outcome in AppealOutcome:
                if v_clean.lower() == outcome.value.lower():
                    return outcome
            
            # Handle compound outcomes
            v_lower = v_clean.lower()
            if 'remanded' in v_lower and 'partial' in v_lower:
                return AppealOutcome.REMANDED_PARTIAL
            elif 'remanded' in v_lower and 'full' in v_lower:
                return AppealOutcome.REMANDED_FULL
            elif 'remanded' in v_lower:
                return AppealOutcome.REMANDED
            elif 'affirmed' in v_lower:
                return AppealOutcome.AFFIRMED
            elif 'reversed' in v_lower:
                return AppealOutcome.REVERSED
            elif 'dismissed' in v_lower:
                return AppealOutcome.DISMISSED
            elif 'partial' in v_lower:
                return AppealOutcome.PARTIAL
            elif 'split' in v_lower:
                return AppealOutcome.SPLIT
            else:
                # Default to unknown if we can't determine
                return AppealOutcome.UNKNOWN
                
        except Exception:
            # If anything goes wrong, return None instead of failing
            return None

class ArgumentModel(BaseModel):
    """Legal argument model"""
    side: ArgumentSide = Field(description="Which side made this argument")
    argument_text: str = Field(description="The actual argument text")

    @field_validator('argument_text')
    @classmethod
    def validate_argument_text(cls, v):
        if not v or v.strip() == '':
            raise ValueError("Argument text cannot be empty")
        return re.sub(r'\s+', ' ', v.strip())

class PrecedentModel(BaseModel):
    """Legal precedent model"""
    precedent_case: str = Field(description="Name of precedent case")
    citation: str = Field(description="Legal citation")
    relationship: PrecedentRelationship = Field(description="How precedent was used")
    citation_text: Optional[str] = Field(description="Quoted rule text or relevant excerpt associated with the citation", default=None)

    @field_validator('precedent_case')
    @classmethod
    def validate_precedent_case(cls, v):
        if not v or v.strip() == '':
            raise ValueError("Precedent case name cannot be empty")
        return re.sub(r'\s+', ' ', v.strip())

    @field_validator('citation')
    @classmethod
    def validate_citation(cls, v):
        if not v or v.strip() == '':
            return v
        return re.sub(r'\s+', ' ', v.strip())

class LegalCaseExtraction(BaseModel):
    """Complete legal case extraction with all related entities"""
    case: CaseModel
    appeals_judges: List[JudgeModel] = Field(default_factory=list)
    attorneys: List[AttorneyModel] = Field(default_factory=list)
    parties: List[PartyModel] = Field(default_factory=list)
    issues_decisions: List[IssueDecisionModel] = Field(default_factory=list)
    arguments: List[ArgumentModel] = Field(default_factory=list)
    precedents: List[PrecedentModel] = Field(default_factory=list)
