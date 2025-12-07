"""
Legal Case AI Extraction Service
Reliable AI extraction using proven approaches that work with Ollama and OpenAI.

Enhanced with detailed logging for debugging.
HYBRID APPROACH: Regex pre-extraction + AI for complex fields
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import json
import os
import logging
import time
import traceback
import re

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# Import our models and prompts
from .models import LegalCaseExtraction
from .prompts import SYSTEM_PROMPT, HUMAN_TEMPLATE

# Ensure .env is loaded when this module is imported
load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# REGEX PRE-EXTRACTION - Reliable extraction before AI processing
# =============================================================================

def extract_court_level_regex(text: str) -> str:
    """Reliably extract court level using regex patterns."""
    text_upper = text.upper()
    
    # Check first 5000 chars for court identification
    header_text = text_upper[:5000]
    
    if 'SUPREME COURT OF THE STATE OF WASHINGTON' in header_text:
        return 'Supreme'
    elif 'IN THE COURT OF APPEALS' in header_text or 'COURT OF APPEALS OF THE STATE OF WASHINGTON' in header_text:
        return 'Appeals'
    elif 'SUPREME COURT' in header_text:
        return 'Supreme'
    elif 'COURT OF APPEALS' in header_text:
        return 'Appeals'
    
    return 'Appeals'  # Default


def extract_division_regex(text: str) -> str:
    """Reliably extract division using regex patterns."""
    text_upper = text.upper()
    header_text = text_upper[:5000]
    
    # Look for "DIVISION ONE/TWO/THREE" or "DIVISION I/II/III"
    if 'DIVISION THREE' in header_text or 'DIVISION III' in header_text:
        return 'Division III'
    elif 'DIVISION TWO' in header_text or 'DIVISION II' in header_text:
        return 'Division II'
    elif 'DIVISION ONE' in header_text or 'DIVISION I' in header_text:
        return 'Division I'
    
    # Also check docket number suffix like "39019-5-III"
    docket_match = re.search(r'\d+-\d+-([IVX]+)', text[:5000])
    if docket_match:
        div = docket_match.group(1).upper()
        if div == 'III':
            return 'Division III'
        elif div == 'II':
            return 'Division II'
        elif div == 'I':
            return 'Division I'
    
    return 'N/A'


def extract_publication_status_regex(text: str) -> str:
    """Extract publication status using regex patterns."""
    text_upper = text.upper()
    header_text = text_upper[:5000]
    
    if 'OPINION PUBLISHED IN PART' in header_text or 'PUBLISHED IN PART' in header_text:
        return 'Partially Published'
    elif 'UNPUBLISHED' in header_text:
        return 'Unpublished'
    
    return 'Published'


def extract_case_number_regex(text: str) -> Optional[str]:
    """Extract case/docket number using regex patterns."""
    # Look for "No. 12345-6-I" or "No. 101,045-1" patterns
    patterns = [
        r'No\.\s*(\d+[,\d]*-\d+(?:-[IVX]+)?)',  # "No. 39019-5-III" or "No. 101,045-1"
        r'Case\s*(?:No\.|Number)?\s*[:\s]*(\d+[,\d]*-\d+(?:-[IVX]+)?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text[:5000], re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def extract_parties_regex(text: str) -> List[Tuple[str, str]]:
    """
    Extract party names and roles from case caption using regex.
    Returns list of (name, legal_role) tuples.
    """
    parties = []
    
    # Look for typical case caption patterns in first 3000 chars
    header_text = text[:3000]
    
    # Pattern 1: "NAME, Plaintiff/Appellant, v. NAME, Defendant/Respondent"
    # Pattern 2: "STATE OF WASHINGTON, Respondent, v. NAME, Appellant"
    
    # Split on "v." or "vs." to get plaintiff/appellant side and defendant/respondent side
    v_split = re.split(r'\s+v\.?\s+', header_text, maxsplit=1, flags=re.IGNORECASE)
    
    if len(v_split) >= 2:
        left_side = v_split[0]
        right_side = v_split[1]
        
        # Extract from left side (typically plaintiff/appellant)
        left_parties = _extract_party_from_section(left_side)
        for name, role in left_parties:
            if name and len(name) > 2:
                parties.append((name, role))
        
        # Extract from right side (typically defendant/respondent)
        right_parties = _extract_party_from_section(right_side)
        for name, role in right_parties:
            if name and len(name) > 2:
                parties.append((name, role))
    
    return parties


def _extract_party_from_section(section: str) -> List[Tuple[str, str]]:
    """Extract party name and role from a section of text."""
    parties = []
    
    # Clean up section - take meaningful lines
    lines = section.split('\n')
    clean_text = ' '.join(line.strip() for line in lines if line.strip())
    
    # Detect role
    role = 'Unknown'
    role_lower = clean_text.lower()
    if 'appellant' in role_lower and 'cross' in role_lower and 'respondent' in role_lower:
        role = 'Appellant/Cross Respondent'
    elif 'respondent' in role_lower and 'cross' in role_lower and 'appellant' in role_lower:
        role = 'Respondent/Cross Appellant'
    elif 'appellant' in role_lower:
        role = 'Appellant'
    elif 'respondent' in role_lower:
        role = 'Respondent'
    elif 'plaintiff' in role_lower:
        role = 'Plaintiff'
    elif 'defendant' in role_lower:
        role = 'Defendant'
    elif 'petitioner' in role_lower:
        role = 'Petitioner'
    
    # Extract name - look for uppercase names before role indicators
    # Pattern: "MADELEINE BARLOW, Plaintiff" or "STATE OF WASHINGTON, Respondent"
    name_match = re.search(
        r'([A-Z][A-Z\s\.,\']+(?:,\s*(?:JR\.|SR\.|III|II|IV)?)?)\s*,?\s*(?:Plaintiff|Defendant|Appellant|Respondent|Petitioner)',
        clean_text,
        re.IGNORECASE
    )
    
    if name_match:
        name = name_match.group(1).strip().strip(',').strip()
        # Clean up name
        name = re.sub(r'\s+', ' ', name)
        # Title case for better display
        if name.isupper():
            name = name.title()
        parties.append((name, role))
    else:
        # Try simpler pattern - just uppercase words
        simple_match = re.search(r'^([A-Z][A-Z\s\.\']+)', clean_text)
        if simple_match:
            name = simple_match.group(1).strip()
            if len(name) > 3 and name.upper() != 'IN THE MATTER':
                if name.isupper():
                    name = name.title()
                parties.append((name, role))
    
    return parties


def extract_judges_regex(text: str) -> List[Tuple[str, str]]:
    """
    Extract judge names and roles using regex patterns.
    Returns list of (name, role) tuples.
    """
    judges = []
    seen_names = set()
    
    # Pattern 1: "JOHNSON, J." or "LAWRENCE-BERREY, J."
    j_pattern = re.compile(r'([A-Z][A-Za-z\-]+(?:\s+[A-Z][a-z]+)?),?\s*J\.', re.MULTILINE)
    for match in j_pattern.finditer(text):
        name = match.group(1).strip().title()
        if name not in seen_names and len(name) > 1:
            seen_names.add(name)
            judges.append((name, 'Authored by'))
    
    # Pattern 2: "WE CONCUR:" followed by judge names/signatures
    concur_match = re.search(r'WE CONCUR[:\s]*(.{100,500})', text, re.IGNORECASE | re.DOTALL)
    if concur_match:
        concur_section = concur_match.group(1)
        # Look for judge name patterns
        concur_names = re.findall(r'([A-Z][A-Za-z\-]+(?:\s+[A-Z][a-z]+)?),?\s*(?:J\.|C\.J\.)', concur_section)
        for name in concur_names:
            name = name.strip().title()
            if name not in seen_names and len(name) > 1:
                seen_names.add(name)
                judges.append((name, 'Concurring'))
    
    # Pattern 3: "Authored by [Name]"
    authored_match = re.search(r'Authored by\s+([A-Za-z\s\-\.]+)', text, re.IGNORECASE)
    if authored_match:
        name = authored_match.group(1).strip().title()
        # Clean up - remove trailing role indicators
        name = re.sub(r'\s*,?\s*J\.?\s*$', '', name)
        if name and name not in seen_names:
            seen_names.add(name)
            # Insert at beginning since this is the primary author
            judges.insert(0, (name, 'Authored by'))
    
    return judges


def extract_case_type_regex(text: str) -> str:
    """Determine case type from document content using regex."""
    text_lower = text.lower()
    header_lower = text_lower[:10000]  # First 10000 chars for context
    
    # First check for civil cases where State is DEFENDANT (sued by plaintiff)
    # Pattern: "Plaintiff v. State of Washington" or "v. State of Washington, Defendant"
    if re.search(r'v\.\s*(?:the\s+)?state of washington\s*,?\s*(?:d/b/a|defendant)', header_lower):
        return 'civil'
    # Certified questions from federal courts are civil matters
    if 'certification from' in header_lower or 'certified question' in header_lower:
        return 'civil'
    # Title IX, negligence, duty of care = tort/civil
    if 'title ix' in header_lower or 'duty of care' in header_lower or 'duty to protect' in header_lower:
        return 'tort'
    if 'negligence' in header_lower or 'negligent' in header_lower:
        return 'tort'
    
    # Criminal case patterns - State is PROSECUTOR/RESPONDENT (prosecuting defendant)
    # Pattern: "State of Washington, Respondent v. [Defendant]"
    if re.search(r'state of washington\s*,?\s*respondent\s*,?\s*v\.', header_lower):
        return 'criminal'
    # Pattern: "State of Washington v. [Defendant], Appellant"
    if re.search(r'state of washington\s*,?\s*v\.\s*[^,]+,?\s*appellant', header_lower):
        return 'criminal'
    if 'unlawful possession' in header_lower or 'convicted of' in header_lower:
        return 'criminal'
    if 'criminal' in header_lower and 'conviction' in header_lower:
        return 'criminal'
    if 'felony' in header_lower or 'misdemeanor' in header_lower:
        return 'criminal'
    
    # Estate/Probate patterns
    if 'in the matter of the estate' in header_lower or 'living trust' in header_lower:
        return 'estate'
    if 'probate' in header_lower or 'personal representative' in header_lower:
        return 'estate'
    if 'tedra' in header_lower or 'trust and estate' in header_lower:
        return 'estate'
    
    # Divorce/Family patterns
    if 'in re marriage' in header_lower or 'dissolution' in header_lower:
        return 'divorce'
    if 'child support' in header_lower or 'parenting plan' in header_lower:
        return 'family'
    if 'custody' in header_lower or 'visitation' in header_lower:
        return 'family'
    
    # Civil patterns - general (after checking criminal)
    if 'd/b/a' in header_lower or 'university' in header_lower:
        return 'civil'
    if 'breach of contract' in header_lower or 'breach of fiduciary' in header_lower:
        return 'civil'
    
    # Default
    return 'civil'


def extract_county_regex(text: str) -> Optional[str]:
    """Extract county information using regex patterns."""
    
    # Washington State city-to-county mapping for common cities
    city_to_county = {
        'seattle': 'King',
        'tacoma': 'Pierce',
        'spokane': 'Spokane',
        'vancouver': 'Clark',
        'bellevue': 'King',
        'everett': 'Snohomish',
        'kent': 'King',
        'renton': 'King',
        'spokane valley': 'Spokane',
        'federal way': 'King',
        'yakima': 'Yakima',
        'bellingham': 'Whatcom',
        'kennewick': 'Benton',
        'auburn': 'King',
        'pasco': 'Franklin',
        'marysville': 'Snohomish',
        'lakewood': 'Pierce',
        'redmond': 'King',
        'richland': 'Benton',
        'olympia': 'Thurston',
        'bremerton': 'Kitsap',
        'pullman': 'Whitman',
        'moses lake': 'Grant',
        'longview': 'Cowlitz',
        'wenatchee': 'Chelan',
        'walla walla': 'Walla Walla',
        'ellensburg': 'Kittitas',
        'port angeles': 'Clallam',
        'tri-cities': 'Benton',
        'mount vernon': 'Skagit',
        'anacortes': 'Skagit',
    }
    
    # Look for explicit county references first
    patterns = [
        r'Appeal from\s+(?:the\s+)?([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+County\s+Superior Court',
        r'Appeal from\s+(?:the\s+)?Superior Court\s+(?:of|for)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+County',
        r'([A-Za-z]+)\s+County\s+Superior Court',
        r'Superior Court of\s+([A-Za-z]+)\s+County',
        r'Superior Court for\s+([A-Za-z]+)\s+County',
        r'filed in\s+([A-Za-z]+)\s+County',
        r'tried in\s+([A-Za-z]+)\s+County',
    ]
    
    text_to_search = text[:10000]  # Expand search area
    
    for pattern in patterns:
        match = re.search(pattern, text_to_search, re.IGNORECASE)
        if match:
            county = match.group(1).strip().title()
            if county.lower() not in ['the', 'a', 'an', 'of', 'state', 'washington']:
                return county
    
    # If no explicit county found, try to find city names and map to counties
    text_lower = text_to_search.lower()
    for city, county in city_to_county.items():
        # Look for city name in context that suggests location
        # e.g., "Moses Lake Police Department" or "in Moses Lake"
        city_patterns = [
            rf'{city}\s+police\s+department',
            rf'{city}\s+police',
            rf'in\s+{city}',
            rf'at\s+{city}',
            rf'{city}\s+(?:city|municipal)',
        ]
        for city_pattern in city_patterns:
            if re.search(city_pattern, text_lower):
                return county
    
    return None


def regex_pre_extract(text: str) -> Dict[str, Any]:
    """
    Perform regex pre-extraction to reliably extract key fields.
    These will override AI responses for fields where regex is more reliable.
    """
    return {
        'court_level': extract_court_level_regex(text),
        'district': extract_division_regex(text),
        'published': extract_publication_status_regex(text),
        'case_file_id': extract_case_number_regex(text),
        'case_type': extract_case_type_regex(text),
        'county': extract_county_regex(text),
        'parties_regex': extract_parties_regex(text),
        'judges_regex': extract_judges_regex(text),
    }


def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", HUMAN_TEMPLATE)])


def _normalize_issue_category(category_value: Any) -> str:
    """Normalize issue category value to match IssueCategory enum."""
    if not category_value:
        return "Miscellaneous / Unclassified"
    
    cat_str = str(category_value).strip().lower()
    
    # Map common variations to proper enum values - now includes UNIVERSAL categories
    category_mapping = {
        # ===== UNIVERSAL CATEGORIES (Non-Divorce) =====
        # Criminal Law
        'criminal law & procedure': 'Criminal Law & Procedure',
        'criminal law': 'Criminal Law & Procedure',
        'criminal': 'Criminal Law & Procedure',
        'criminal procedure': 'Criminal Law & Procedure',
        'search & seizure': 'Criminal Law & Procedure',
        'fourth amendment': 'Criminal Law & Procedure',
        'sentencing': 'Criminal Law & Procedure',
        'firearm possession': 'Criminal Law & Procedure',
        'unlawful possession': 'Criminal Law & Procedure',
        
        # Constitutional Law
        'constitutional law': 'Constitutional Law',
        'constitutional': 'Constitutional Law',
        'due process': 'Constitutional Law',
        'equal protection': 'Constitutional Law',
        'first amendment': 'Constitutional Law',
        'civil rights': 'Constitutional Law',
        
        # Civil Procedure
        'civil procedure': 'Civil Procedure',
        'summary judgment': 'Civil Procedure',
        'motion to dismiss': 'Civil Procedure',
        'statute of limitations': 'Civil Procedure',
        'standing': 'Civil Procedure',
        
        # Evidence
        'evidence': 'Evidence',
        'hearsay': 'Evidence',
        'expert testimony': 'Evidence',
        'sufficiency of evidence': 'Evidence',
        'insufficient evidence': 'Evidence',
        
        # Contracts
        'contracts': 'Contracts',
        'contract': 'Contracts',
        'breach of contract': 'Contracts',
        
        # Torts / Personal Injury
        'torts / personal injury': 'Torts / Personal Injury',
        'torts': 'Torts / Personal Injury',
        'tort': 'Torts / Personal Injury',
        'personal injury': 'Torts / Personal Injury',
        'negligence': 'Torts / Personal Injury',
        'civil liability': 'Torts / Personal Injury',
        'title ix': 'Torts / Personal Injury',
        
        # Property Law
        'property law': 'Property Law',
        'property': 'Property Law',
        'real property': 'Property Law',
        
        # Employment Law
        'employment law': 'Employment Law',
        'employment': 'Employment Law',
        'labor': 'Employment Law',
        'workplace': 'Employment Law',
        
        # Estate & Probate
        'estate & probate': 'Estate & Probate',
        'estate': 'Estate & Probate',
        'probate': 'Estate & Probate',
        'trust': 'Estate & Probate',
        'trust administration': 'Estate & Probate',
        'will contest': 'Estate & Probate',
        'inheritance': 'Estate & Probate',
        
        # Administrative Law
        'administrative law': 'Administrative Law',
        'administrative': 'Administrative Law',
        'agency': 'Administrative Law',
        
        # Business & Commercial
        'business & commercial': 'Business & Commercial',
        'business': 'Business & Commercial',
        'commercial': 'Business & Commercial',
        
        # Insurance Law
        'insurance law': 'Insurance Law',
        'insurance': 'Insurance Law',
        
        # ===== FAMILY LAW / DIVORCE CATEGORIES =====
        'family law': 'Family Law',
        'spousal support / maintenance': 'Spousal Support / Maintenance',
        'spousal support': 'Spousal Support / Maintenance',
        'maintenance': 'Spousal Support / Maintenance',
        'alimony': 'Spousal Support / Maintenance',
        
        'child support': 'Child Support',
        
        'parenting plan / custody / visitation': 'Parenting Plan / Custody / Visitation',
        'parenting plan': 'Parenting Plan / Custody / Visitation',
        'custody': 'Parenting Plan / Custody / Visitation',
        'visitation': 'Parenting Plan / Custody / Visitation',
        'child custody': 'Parenting Plan / Custody / Visitation',
        
        'property division / debt allocation': 'Property Division / Debt Allocation',
        'property division': 'Property Division / Debt Allocation',
        'debt allocation': 'Property Division / Debt Allocation',
        'asset division': 'Property Division / Debt Allocation',
        
        # ===== GENERAL CATEGORIES =====
        'attorney fees & costs': 'Attorney Fees & Costs',
        'attorney fees': 'Attorney Fees & Costs',
        'legal fees': 'Attorney Fees & Costs',
        
        'procedural & evidentiary issues': 'Procedural & Evidentiary Issues',
        'procedural': 'Procedural & Evidentiary Issues',
        'evidentiary': 'Procedural & Evidentiary Issues',
        
        'jurisdiction & venue': 'Jurisdiction & Venue',
        'jurisdiction': 'Jurisdiction & Venue',
        'venue': 'Jurisdiction & Venue',
        
        'enforcement & contempt orders': 'Enforcement & Contempt Orders',
        'enforcement': 'Enforcement & Contempt Orders',
        'contempt': 'Enforcement & Contempt Orders',
        
        'modification orders': 'Modification Orders',
        'modification': 'Modification Orders',
        
        'miscellaneous / unclassified': 'Miscellaneous / Unclassified',
        'miscellaneous': 'Miscellaneous / Unclassified',
        'other': 'Miscellaneous / Unclassified',
        'unknown': 'Miscellaneous / Unclassified',
        'general': 'Miscellaneous / Unclassified',
    }
    
    # Check for exact match first
    if cat_str in category_mapping:
        return category_mapping[cat_str]
    
    # Check for partial matches
    for key, value in category_mapping.items():
        if key in cat_str or cat_str in key:
            return value
    
    # Default to miscellaneous
    return 'Miscellaneous / Unclassified'


def _transform_issues(raw_issues: list) -> list:
    """
    Transform raw issue data to match IssueDecisionModel schema.
    
    IssueDecisionModel requires:
    - category: IssueCategory (required)
    - subcategory: str (required)
    - issue_summary: str (required)
    """
    issues_decisions = []
    
    if not raw_issues:
        return issues_decisions
    
    for i in raw_issues:
        if not isinstance(i, dict):
            continue
        
        # Map category field - AI might use different names
        raw_category = (
            i.get('category') or
            i.get('issue_category') or
            i.get('issue') or
            'Miscellaneous / Unclassified'
        )
        # Normalize to match IssueCategory enum
        category = _normalize_issue_category(raw_category)
        
        # Map subcategory field
        subcategory = (
            i.get('subcategory') or
            i.get('issue_subcategory') or
            i.get('sub_category') or
            'General'
        )
        
        # Map issue_summary field - required!
        issue_summary = (
            i.get('issue_summary') or
            i.get('issue_description') or
            i.get('description') or
            i.get('summary') or
            i.get('issue') or
            'Issue not specified'
        )
        
        issue_obj = {
            'category': category,
            'subcategory': subcategory,
            'issue_summary': issue_summary,
            'rcw_reference': i.get('rcw_reference'),
            'keywords': i.get('keywords'),
            'decision_stage': i.get('decision_stage'),
            'decision_summary': i.get('decision_summary') or i.get('court_decision') or i.get('decision'),
            'appeal_outcome': i.get('appeal_outcome') or i.get('outcome'),
            'winner_legal_role': i.get('winner_legal_role'),
            'winner_personal_role': i.get('winner_personal_role'),
        }
        issues_decisions.append(issue_obj)
    
    return issues_decisions


def _normalize_district(district_value: Any) -> str:
    """Normalize district value to match District enum."""
    if not district_value:
        return "N/A"
    
    district_str = str(district_value).strip().upper()
    
    # Map common variations
    district_mapping = {
        'DIVISION I': 'Division I',
        'DIVISION 1': 'Division I',
        'DIV I': 'Division I',
        'DIV. I': 'Division I',
        'I': 'Division I',
        'DIVISION II': 'Division II',
        'DIVISION 2': 'Division II',
        'DIV II': 'Division II',
        'DIV. II': 'Division II',
        'II': 'Division II',
        'DIVISION III': 'Division III',
        'DIVISION 3': 'Division III',
        'DIV III': 'Division III',
        'DIV. III': 'Division III',
        'III': 'Division III',
        'N/A': 'N/A',
        'NA': 'N/A',
        'NONE': 'N/A',
        '': 'N/A',
    }
    
    return district_mapping.get(district_str, 'N/A')


def _normalize_court_level(court_level_value: Any) -> str:
    """Normalize court level value to match CourtLevel enum."""
    if not court_level_value:
        return "Appeals"  # Default
    
    level_str = str(court_level_value).strip().lower()
    
    if 'supreme' in level_str:
        return "Supreme"
    elif 'appeal' in level_str:
        return "Appeals"
    else:
        return "Appeals"  # Default


def _normalize_published(published_value: Any) -> str:
    """Normalize published status to match PublicationStatus enum."""
    if not published_value:
        return "Published"  # Default
    
    pub_str = str(published_value).strip().lower()
    
    if 'unpublished' in pub_str:
        return "Unpublished"
    elif 'partial' in pub_str:
        return "Partially Published"
    else:
        return "Published"


def _normalize_personal_role(role_value: Any) -> Optional[str]:
    """Normalize personal role to match PersonalRole enum. Returns None if not determinable."""
    if not role_value or role_value is None:
        return None
    
    role_str = str(role_value).strip().lower()
    
    # Check if this is actually a role or if the AI put a name here
    role_keywords = ['husband', 'wife', 'parent', 'child', 'estate', 'corporation', 'government', 'individual', 'other', 'unknown']
    if not any(kw in role_str for kw in role_keywords):
        # Likely a name, not a role - return None
        return None
    
    # Map to enum values - now includes universal roles
    if 'husband' in role_str:
        return 'Husband'
    elif 'wife' in role_str:
        return 'Wife'
    elif 'parent' in role_str:
        return 'Parent'
    elif 'child' in role_str:
        return 'Child'
    elif 'estate' in role_str:
        return 'Estate'
    elif 'corporation' in role_str or 'company' in role_str or 'business' in role_str:
        return 'Corporation'
    elif 'government' in role_str or 'state' in role_str:
        return 'Government'
    elif 'individual' in role_str or 'person' in role_str:
        return 'Individual'
    elif 'other' in role_str:
        return 'Other'
    else:
        return None  # Let the validator handle it


def _normalize_trial_judge(trial_judge_value: Any) -> Optional[str]:
    """Normalize trial_judge to a single string (AI sometimes returns a list)."""
    if not trial_judge_value:
        return None
    
    if isinstance(trial_judge_value, list):
        # Take the first non-empty judge name
        for j in trial_judge_value:
            if j and str(j).strip():
                return str(j).strip()
        return None
    
    return str(trial_judge_value).strip() if trial_judge_value else None


def _transform_ollama_response(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform raw Ollama JSON response to match our Pydantic schema.
    Ollama often returns flat structures that need to be nested properly.
    
    Target Schema:
    - LegalCaseExtraction
      - case: CaseModel (required fields: title, court_level, court, published, summary)
      - appeals_judges: List[JudgeModel] (judge_name, role)
      - attorneys: List[AttorneyModel] (name, representing)
      - parties: List[PartyModel] (name, legal_role)
      - issues_decisions: List[IssueDecisionModel] (category, subcategory, issue_summary)
      - arguments: List[ArgumentModel] (side, argument_text)
      - precedents: List[PrecedentModel] (precedent_case, citation, relationship)
    """
    # If already has nested 'case' object with proper required fields, validate and return
    if 'case' in raw_data and isinstance(raw_data['case'], dict):
        case_obj = raw_data['case']
        # Ensure required fields have defaults
        if 'court_level' not in case_obj or not case_obj['court_level']:
            case_obj['court_level'] = _normalize_court_level(case_obj.get('court_level'))
        else:
            case_obj['court_level'] = _normalize_court_level(case_obj['court_level'])
        if 'published' not in case_obj or not case_obj['published']:
            case_obj['published'] = 'Published'
        else:
            case_obj['published'] = _normalize_published(case_obj['published'])
        if 'summary' not in case_obj or not case_obj['summary']:
            case_obj['summary'] = 'Case summary not available'
        if 'district' in case_obj:
            case_obj['district'] = _normalize_district(case_obj['district'])
        # Normalize trial_judge (might be a list)
        if 'trial_judge' in case_obj:
            case_obj['trial_judge'] = _normalize_trial_judge(case_obj['trial_judge'])
        raw_data['case'] = case_obj
        
        # Also ensure issues_decisions have proper fields
        if 'issues_decisions' in raw_data:
            raw_data['issues_decisions'] = _transform_issues(raw_data['issues_decisions'])
        
        # Normalize parties personal_role
        if 'parties' in raw_data and isinstance(raw_data['parties'], list):
            for p in raw_data['parties']:
                if isinstance(p, dict) and 'personal_role' in p:
                    p['personal_role'] = _normalize_personal_role(p['personal_role'])
        
        # Filter out empty precedents
        if 'precedents' in raw_data and isinstance(raw_data['precedents'], list):
            raw_data['precedents'] = [
                p for p in raw_data['precedents']
                if isinstance(p, dict) and p.get('precedent_case', '').strip()
            ]
        
        return raw_data
    
    # Build the nested 'case' object from flat fields
    case_obj = {
        'case_file_id': raw_data.get('case_file_id'),
        'title': raw_data.get('title', 'Unknown Case'),
        'court_level': _normalize_court_level(raw_data.get('court_level')),
        'court': raw_data.get('court', 'Washington Court of Appeals'),
        'district': _normalize_district(raw_data.get('district')),
        'county': raw_data.get('county'),
        'docket_number': raw_data.get('docket_number'),
        'source_docket_number': raw_data.get('source_docket_number'),
        'trial_judge': _normalize_trial_judge(raw_data.get('trial_judge')),
        'filing_date': raw_data.get('filing_date'),
        'oral_argument_date': raw_data.get('oral_argument_date'),
        'case_type': raw_data.get('case_type'),
        'trial_start_date': raw_data.get('trial_start_date'),
        'trial_end_date': raw_data.get('trial_end_date'),
        'trial_published_date': raw_data.get('trial_published_date'),
        'appeal_start_date': raw_data.get('appeal_start_date'),
        'appeal_end_date': raw_data.get('appeal_end_date'),
        'appeal_published_date': raw_data.get('appeal_published_date'),
        'published': _normalize_published(raw_data.get('published')),
        'summary': raw_data.get('summary') or 'Case summary not available',
        'overall_case_outcome': raw_data.get('overall_case_outcome'),
        'winner_legal_role': raw_data.get('winner_legal_role'),
        'winner_personal_role': raw_data.get('winner_personal_role'),
        'appeal_outcome': raw_data.get('appeal_outcome'),
    }
    
    # Transform judges - could be strings or objects
    appeals_judges = []
    raw_judges = raw_data.get('appeals_judges', [])
    for j in raw_judges:
        if isinstance(j, str):
            appeals_judges.append({'judge_name': j, 'role': 'Authored by'})
        elif isinstance(j, dict):
            judge_obj = {
                'judge_name': j.get('judge_name') or j.get('name') or str(j),
                'role': j.get('role', 'Authored by')
            }
            appeals_judges.append(judge_obj)
    
    # Transform attorneys - map field names
    attorneys = []
    raw_attorneys = raw_data.get('attorneys', [])
    for a in raw_attorneys:
        if isinstance(a, dict):
            attorney_obj = {
                'name': a.get('name') or a.get('attorney_name', 'Unknown'),
                'firm_name': a.get('firm_name') or a.get('firm'),
                'firm_address': a.get('firm_address') or a.get('address'),
                'representing': a.get('representing') or a.get('representation') or a.get('role', 'Unknown'),
                'attorney_type': a.get('attorney_type', 'Attorney')
            }
            attorneys.append(attorney_obj)
    
    # Transform parties
    parties = []
    raw_parties = raw_data.get('parties', [])
    for p in raw_parties:
        if isinstance(p, dict):
            party_obj = {
                'name': p.get('name') or p.get('party_name', 'Unknown'),
                'legal_role': p.get('legal_role') or p.get('role', 'Unknown'),
                'personal_role': _normalize_personal_role(p.get('personal_role'))
            }
            parties.append(party_obj)
    
    # Transform issues_decisions using dedicated function
    raw_issues = raw_data.get('issues_decisions', []) or raw_data.get('CATEGORIZED ISSUES WITH DECISIONS', []) or raw_data.get('issues', [])
    issues_decisions = _transform_issues(raw_issues)
    
    # Transform arguments - must match ArgumentModel(side, argument_text)
    arguments = []
    raw_arguments = raw_data.get('arguments', [])
    for a in raw_arguments:
        if isinstance(a, dict):
            # Map to ArgumentModel fields
            side = a.get('side') or a.get('arguing_party') or a.get('party', 'Court')
            arg_text = a.get('argument_text') or a.get('text') or a.get('argument', '')
            if arg_text:  # Only add if we have text
                arg_obj = {
                    'side': side,
                    'argument_text': arg_text
                }
                arguments.append(arg_obj)
    
    # Transform precedents - must match PrecedentModel(precedent_case, citation, relationship)
    # Filter out empty precedents that would fail validation
    precedents = []
    raw_precedents = raw_data.get('precedents', []) or raw_data.get('citations', [])
    for p in raw_precedents:
        if isinstance(p, dict):
            case_name = p.get('precedent_case') or p.get('case_name') or p.get('name', '')
            # Skip empty precedents
            if not case_name or case_name.strip() == '':
                continue
            prec_obj = {
                'precedent_case': case_name,
                'citation': p.get('citation') or p.get('cite', case_name),
                'relationship': p.get('relationship') or p.get('treatment', 'cited'),
                'citation_text': p.get('citation_text') or p.get('relevance') or p.get('description')
            }
            precedents.append(prec_obj)
        elif isinstance(p, str) and p.strip():
            precedents.append({
                'precedent_case': p, 
                'citation': p, 
                'relationship': 'cited'
            })
    
    # Build final structure
    transformed = {
        'case': case_obj,
        'appeals_judges': appeals_judges,
        'attorneys': attorneys,
        'parties': parties,
        'issues_decisions': issues_decisions,
        'arguments': arguments,
        'precedents': precedents
    }
    
    return transformed


def _apply_regex_overrides(transformed_data: Dict[str, Any], regex_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply regex pre-extraction results to override/supplement AI extracted data.
    Regex is more reliable for structured fields like court_level, district, case_type.
    """
    if not transformed_data.get('case'):
        return transformed_data
    
    case_obj = transformed_data['case']
    
    # Override court_level - regex is very reliable for this
    if regex_data.get('court_level'):
        case_obj['court_level'] = regex_data['court_level']
        logger.info(f"[Regex Override] court_level = {regex_data['court_level']}")
    
    # Override district - regex is reliable
    if regex_data.get('district') and regex_data['district'] != 'N/A':
        case_obj['district'] = regex_data['district']
        logger.info(f"[Regex Override] district = {regex_data['district']}")
    
    # Override publication status - regex is reliable  
    if regex_data.get('published'):
        case_obj['published'] = regex_data['published']
        logger.info(f"[Regex Override] published = {regex_data['published']}")
    
    # Override case_file_id if found by regex
    if regex_data.get('case_file_id'):
        case_obj['case_file_id'] = regex_data['case_file_id']
        logger.info(f"[Regex Override] case_file_id = {regex_data['case_file_id']}")
    
    # Override case_type - regex is more reliable than AI for this
    if regex_data.get('case_type'):
        case_obj['case_type'] = regex_data['case_type']
        logger.info(f"[Regex Override] case_type = {regex_data['case_type']}")
    
    # Override county if found
    if regex_data.get('county'):
        case_obj['county'] = regex_data['county']
        logger.info(f"[Regex Override] county = {regex_data['county']}")
    
    # Set court based on court_level and district
    court_level = case_obj.get('court_level', 'Appeals')
    district = case_obj.get('district', 'N/A')
    if court_level == 'Supreme':
        case_obj['court'] = 'Washington State Supreme Court'
    elif district != 'N/A':
        case_obj['court'] = f'Washington Court of Appeals {district}'
    else:
        case_obj['court'] = 'Washington Court of Appeals'
    
    # === PARTIES ===
    # If AI returned placeholder/fake names (like "John Doe", "Jane Smith"), use regex-extracted parties
    regex_parties = regex_data.get('parties_regex', [])
    ai_parties = transformed_data.get('parties', [])
    
    # Check for placeholder names in AI parties
    placeholder_names = ['john doe', 'jane doe', 'john smith', 'jane smith', 'unknown', 'n/a']
    has_placeholder = any(
        isinstance(p, dict) and p.get('name', '').lower() in placeholder_names
        for p in ai_parties
    )
    
    if regex_parties and (not ai_parties or has_placeholder):
        logger.info(f"[Regex Override] Using regex-extracted parties (AI had placeholders)")
        transformed_data['parties'] = [
            {
                'name': name,
                'legal_role': role,
                'personal_role': None  # Will be determined by AI or left null
            }
            for name, role in regex_parties
        ]
    
    # === JUDGES ===
    # If AI returned empty or placeholder judges, use regex-extracted judges
    regex_judges = regex_data.get('judges_regex', [])
    ai_judges = transformed_data.get('appeals_judges', [])
    
    if regex_judges and not ai_judges:
        logger.info(f"[Regex Override] Using regex-extracted judges (AI returned none)")
        transformed_data['appeals_judges'] = [
            {
                'judge_name': name,
                'role': role
            }
            for name, role in regex_judges
        ]
    elif regex_judges and ai_judges:
        # Supplement AI judges with regex judges (merge unique names)
        ai_judge_names = {j.get('judge_name', '').lower() for j in ai_judges}
        for name, role in regex_judges:
            if name.lower() not in ai_judge_names:
                logger.info(f"[Regex Supplement] Adding judge: {name} ({role})")
                transformed_data['appeals_judges'].append({
                    'judge_name': name,
                    'role': role
                })
    
    transformed_data['case'] = case_obj
    return transformed_data


def _log_extraction_result(result: LegalCaseExtraction, source: str, duration: float):
    """Log detailed extraction results"""
    try:
        logger.info(f"{'='*60}")
        logger.info(f"[AI] {source} EXTRACTION SUCCESSFUL")
        logger.info(f"{'='*60}")
        logger.info(f"[AI] Duration: {duration:.2f} seconds")
        logger.info(f"[AI] Extracted Data Summary:")
        logger.info(f"   - Case Title: {result.case.title[:50]}..." if result.case.title else "   - Case Title: None")
        logger.info(f"   - County: {result.case.county}")
        logger.info(f"   - Appeal Outcome: {result.case.appeal_outcome}")
        logger.info(f"   - Overall Outcome: {result.case.overall_case_outcome}")
        logger.info(f"   - Appeals Judges: {len(result.appeals_judges)}")
        for j in result.appeals_judges:
            logger.info(f"      - {j.judge_name} ({j.role.value if hasattr(j.role, 'value') else j.role})")
        logger.info(f"   - Attorneys: {len(result.attorneys)}")
        for a in result.attorneys:
            # AttorneyModel uses 'name' not 'attorney_name'
            logger.info(f"      - {a.name} (representing: {a.representing})")
        logger.info(f"   - Parties: {len(result.parties)}")
        for p in result.parties:
            # PartyModel uses 'name' not 'party_name'
            role_str = p.legal_role.value if hasattr(p.legal_role, 'value') else str(p.legal_role)
            logger.info(f"      - {p.name} ({role_str})")
        logger.info(f"   - Issues/Decisions: {len(result.issues_decisions)}")
        for i in result.issues_decisions:
            # IssueDecisionModel uses 'category' not 'issue_category'
            category_str = i.category.value if hasattr(i.category, 'value') else str(i.category)
            logger.info(f"      - {category_str}: {i.appeal_outcome}")
        logger.info(f"   - Arguments: {len(result.arguments)}")
        logger.info(f"   - Precedents: {len(result.precedents)}")
        logger.info(f"{'='*60}")
    except Exception as e:
        logger.error(f"[AI] Error logging extraction result: {e}")
        logger.debug(f"[AI] Traceback: {traceback.format_exc()}")


def extract_case_with_openai(case_text: str, case_info: Dict[str, Any]) -> Optional[LegalCaseExtraction]:
    """Extract case data using OpenAI API"""
    start_time = time.time()
    model = os.getenv("OPENAI_MODEL", "gpt-4")
    
    logger.info(f"[OpenAI] Starting extraction with model: {model}")
    logger.info(f"[OpenAI] Case info: {json.dumps(case_info, indent=2)}")
    logger.info(f"[OpenAI] Text length: {len(case_text)} characters")
    
    try:
        llm = ChatOpenAI(model=model, temperature=0)
        structured_llm = llm.with_structured_output(LegalCaseExtraction, method="json_schema")
        prompt = _build_prompt()
        chain = prompt | structured_llm
        
        logger.info("[OpenAI] Sending request to OpenAI API...")
        result = chain.invoke({"case_info": case_info, "case_text": case_text})
        
        if isinstance(result, LegalCaseExtraction):
            duration = time.time() - start_time
            _log_extraction_result(result, "OpenAI", duration)
            return result
        
        validated = LegalCaseExtraction.model_validate(result)
        duration = time.time() - start_time
        _log_extraction_result(validated, "OpenAI", duration)
        return validated
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ OpenAI extraction failed after {duration:.2f}s")
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Error message: {str(e)}")
        logger.debug(f"❌ Full traceback:\n{traceback.format_exc()}")
        return None


def extract_case_with_ollama(case_text: str, case_info: Dict[str, Any]) -> Optional[LegalCaseExtraction]:
    """Extract case data using Ollama (local or remote) with regex hybrid approach"""
    start_time = time.time()
    
    # Get configuration
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.3:latest")
    
    logger.info(f"{'='*60}")
    logger.info(f"[Ollama] STARTING HYBRID AI+REGEX EXTRACTION")
    logger.info(f"{'='*60}")
    logger.info(f"[Ollama] Server URL: {ollama_base_url}")
    logger.info(f"[Ollama] Model: {ollama_model}")
    logger.info(f"[Ollama] Case: {case_info.get('case_number', 'Unknown')}")
    logger.info(f"[Ollama] Text length: {len(case_text)} characters ({len(case_text.split())} words)")
    
    # === REGEX PRE-EXTRACTION (Reliable structured data) ===
    logger.info(f"[Regex] Running regex pre-extraction for reliable fields...")
    regex_data = regex_pre_extract(case_text)
    logger.info(f"[Regex] Pre-extracted: court_level={regex_data.get('court_level')}, "
                f"district={regex_data.get('district')}, case_type={regex_data.get('case_type')}")
    logger.info(f"[Regex] Pre-extracted: parties={len(regex_data.get('parties_regex', []))}, "
                f"judges={len(regex_data.get('judges_regex', []))}")
    
    # === TRY 1: Native Ollama Client ===
    logger.info(f"[Ollama] Attempt 1: Native ollama Python client")
    
    try:
        import ollama
        from ollama import Client
        
        logger.info(f"[Ollama] Creating client for {ollama_base_url}...")
        client = Client(host=ollama_base_url)
        
        # Test connection first
        logger.info(f"[Ollama] Testing connection...")
        try:
            models = client.list()
            available_models = [m.get('name', m.get('model', 'unknown')) for m in models.get('models', [])]
            logger.info(f"[Ollama] Connected! Available models: {available_models}")
        except Exception as conn_error:
            logger.warning(f"[Ollama] Connection test failed: {conn_error}")
            raise conn_error
        
        prompt = _build_prompt()
        msgs = prompt.format_messages(case_info=case_info, case_text=case_text)
        
        # Enhanced system message
        enhanced_system = msgs[0].content + "\n\n🚨 CRITICAL JSON REQUIREMENTS:\nYour response MUST include ALL 7 top-level fields in your JSON:\n1. case (object)\n2. appeals_judges (array - REQUIRED even if empty [])\n3. attorneys (array - REQUIRED even if empty [])\n4. parties (array - REQUIRED even if empty [])\n5. issues_decisions (array - REQUIRED even if empty [])\n6. arguments (array - REQUIRED even if empty [])\n7. precedents (array - REQUIRED even if empty [])\n\nIf ANY field is missing from your JSON, the extraction WILL FAIL. Always include empty arrays [] if no data exists for that category."
        
        # Add schema to prompt
        schema_json = json.dumps(LegalCaseExtraction.model_json_schema(), indent=2)
        system_with_schema = f"{enhanced_system}\n\nIMPORTANT: You must return valid JSON that matches this exact schema:\n{schema_json}"
        
        logger.info(f"[Ollama] Sending chat request to model {ollama_model}...")
        logger.info(f"[Ollama] System prompt length: {len(system_with_schema)} chars")
        logger.info(f"[Ollama] User prompt length: {len(msgs[1].content)} chars")
        
        request_start = time.time()
        response = client.chat(
            model=ollama_model,
            messages=[
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": msgs[1].content},
            ],
            format="json",
            options={"temperature": 0.0},
        )
        request_duration = time.time() - request_start
        
        logger.info(f"[Ollama] Response received in {request_duration:.2f}s")
        logger.info(f"[Ollama] Response length: {len(response.message.content)} chars")
        
        # Log first part of response for debugging
        response_preview = response.message.content[:1000]
        logger.debug(f"[Ollama] Response preview:\n{response_preview}...")
        
        # Parse JSON and transform to match schema
        logger.info(f"[Ollama] Parsing JSON response...")
        raw_data = json.loads(response.message.content)
        
        # Transform flat response to nested schema format
        logger.info(f"[Ollama] Transforming response to match Pydantic schema...")
        transformed_data = _transform_ollama_response(raw_data)
        
        # === APPLY REGEX OVERRIDES (Hybrid approach) ===
        logger.info(f"[Regex] Applying regex overrides to AI results...")
        transformed_data = _apply_regex_overrides(transformed_data, regex_data)
        
        # Validate with Pydantic
        logger.info(f"[Ollama] Validating transformed data with Pydantic...")
        result = LegalCaseExtraction.model_validate(transformed_data)
        
        duration = time.time() - start_time
        _log_extraction_result(result, "Hybrid Native Ollama + Regex", duration)
        return result
        
    except ImportError as e:
        logger.warning(f"[Ollama] ollama package not installed: {e}")
    except Exception as e:
        duration = time.time() - start_time
        logger.warning(f"⚠️  [Ollama] Native client failed after {duration:.2f}s")
        logger.warning(f"⚠️  [Ollama] Error type: {type(e).__name__}")
        logger.warning(f"⚠️  [Ollama] Error message: {str(e)}")
        logger.debug(f"⚠️  [Ollama] Full traceback:\n{traceback.format_exc()}")

    # === TRY 2: LangChain ChatOllama Fallback ===
    logger.info(f"[Ollama] Attempt 2: LangChain ChatOllama fallback")
    
    try:
        from langchain_ollama import ChatOllama
        
        logger.info(f"[Ollama] Creating LangChain ChatOllama for {ollama_base_url}...")
        llm = ChatOllama(
            model=ollama_model, 
            base_url=ollama_base_url,
            temperature=0.0, 
            format="json"
        )
        
        # Try different structured output methods
        structured_llm = None
        for method in ["json_schema", "json_mode", None]:
            try:
                if method:
                    logger.info(f"[Ollama] Trying with_structured_output(method='{method}')...")
                    structured_llm = llm.with_structured_output(LegalCaseExtraction, method=method)
                else:
                    logger.info(f"[Ollama] Trying with_structured_output() without method...")
                    structured_llm = llm.with_structured_output(LegalCaseExtraction)
                logger.info(f"[Ollama] Structured output method '{method}' worked!")
                break
            except Exception as method_error:
                logger.debug(f"[Ollama] Method '{method}' failed: {method_error}")
                continue
        
        if not structured_llm:
            raise Exception("All structured output methods failed")
        
        prompt = _build_prompt()
        chain = prompt | structured_llm
        
        logger.info(f"[Ollama] Invoking LangChain chain...")
        request_start = time.time()
        result = chain.invoke({"case_info": case_info, "case_text": case_text})
        request_duration = time.time() - request_start
        logger.info(f"[Ollama] LangChain response received in {request_duration:.2f}s")
        
        if isinstance(result, LegalCaseExtraction):
            duration = time.time() - start_time
            _log_extraction_result(result, "LangChain Ollama", duration)
            return result
        
        validated = LegalCaseExtraction.model_validate(result)
        duration = time.time() - start_time
        _log_extraction_result(validated, "LangChain Ollama", duration)
        return validated
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ [Ollama] LangChain fallback also failed after {duration:.2f}s")
        logger.error(f"❌ [Ollama] Error type: {type(e).__name__}")
        logger.error(f"❌ [Ollama] Error message: {str(e)}")
        logger.debug(f"❌ [Ollama] Full traceback:\n{traceback.format_exc()}")
        return None


def extract_case_data(case_text: str, case_info: Dict[str, Any]) -> Optional[LegalCaseExtraction]:
    """
    Main extraction function that prioritizes Ollama if USE_OLLAMA=true.
    
    Extraction priority:
    1. If USE_OLLAMA=true: Try Ollama first, then OpenAI
    2. If USE_OLLAMA=false: Try OpenAI first, then Ollama
    """
    start_time = time.time()
    
    logger.info(f"\n{'#'*80}")
    logger.info(f"# AI EXTRACTION STARTED")
    logger.info(f"# Case: {case_info.get('case_number', 'Unknown')}")
    logger.info(f"# Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'#'*80}\n")
    
    # Log environment configuration
    use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
    logger.info(f"[Config] USE_OLLAMA={use_ollama}")
    logger.info(f"[Config] OLLAMA_BASE_URL={os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
    logger.info(f"[Config] OLLAMA_MODEL={os.getenv('OLLAMA_MODEL', 'llama3.3:latest')}")
    logger.info(f"[Config] OPENAI_API_KEY={'[SET]' if os.getenv('OPENAI_API_KEY') else '[NOT SET]'}")
    logger.info(f"[Config] OPENAI_MODEL={os.getenv('OPENAI_MODEL', 'gpt-4')}")
    
    result = None
    
    if use_ollama:
        logger.info("\n[Strategy] Primary: Ollama, Fallback: OpenAI")
        
        # Try Ollama first
        result = extract_case_with_ollama(case_text, case_info)
        if result:
            total_duration = time.time() - start_time
            logger.info(f"\n✅ EXTRACTION COMPLETE (Ollama) - Total time: {total_duration:.2f}s")
            return result
        
        # Fallback to OpenAI
        logger.warning("\n[Strategy] Ollama failed, trying OpenAI fallback...")
        if os.getenv("OPENAI_API_KEY"):
            result = extract_case_with_openai(case_text, case_info)
            if result:
                total_duration = time.time() - start_time
                logger.info(f"\n✅ EXTRACTION COMPLETE (OpenAI fallback) - Total time: {total_duration:.2f}s")
                return result
        else:
            logger.warning("[Strategy] OpenAI API key not set, cannot use fallback")
    else:
        logger.info("\n[Strategy] Primary: OpenAI, Fallback: Ollama")
        
        # Try OpenAI first
        if os.getenv("OPENAI_API_KEY"):
            result = extract_case_with_openai(case_text, case_info)
            if result:
                total_duration = time.time() - start_time
                logger.info(f"\n✅ EXTRACTION COMPLETE (OpenAI) - Total time: {total_duration:.2f}s")
                return result
        else:
            logger.warning("[Strategy] OpenAI API key not set, skipping...")
        
        # Fallback to Ollama
        logger.warning("\n[Strategy] OpenAI failed/unavailable, trying Ollama fallback...")
        result = extract_case_with_ollama(case_text, case_info)
        if result:
            total_duration = time.time() - start_time
            logger.info(f"\n✅ EXTRACTION COMPLETE (Ollama fallback) - Total time: {total_duration:.2f}s")
            return result
    
    total_duration = time.time() - start_time
    logger.error(f"\n❌ ALL EXTRACTION METHODS FAILED - Total time: {total_duration:.2f}s")
    logger.error(f"{'#'*80}\n")
    return None
