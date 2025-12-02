"""
Data Repair Script: Populate holding_type for Mixed Outcome Cases

This script analyzes cases with partial outcomes (reversed_partial, remanded_partial)
and uses an LLM to determine the specific holding for each legal issue.

Usage:
    python scripts/repair_holding_types.py

Environment Variables Required:
    - DATABASE_URL or individual DB_* variables
    - OPENAI_API_KEY
"""

import os
import sys
import json
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field, ValidationError
from openai import OpenAI
from tqdm import tqdm

# ============================================
# Configuration
# ============================================

# Database config - uses environment variables (matching .env file)
DB_CONFIG = {
    "host": os.getenv("DATABASE_HOST", "localhost"),
    "port": int(os.getenv("DATABASE_PORT", "5433")),
    "database": os.getenv("DATABASE_NAME", "cases_llama3_3"),
    "user": os.getenv("DATABASE_USER", "postgres"),
    "password": os.getenv("DATABASE_PASSWORD", "postgres123"),
}

# OpenAI config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Text processing config
MAX_TEXT_CHARS = 3000  # Last N characters of case text (conclusion/disposition)
BATCH_SIZE = 10  # Process N cases before committing
MAX_WORKERS = 10  # Concurrent LLM requests

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/repair_holding_types_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================
# Pydantic Models for LLM Response Validation
# ============================================

class IssueHolding(BaseModel):
    """Single issue holding from LLM response"""
    issue_id: int
    holding_type: str = Field(..., pattern=r'^(affirmed|reversed|remanded|vacated|harmless_error)$')
    reasoning: Optional[str] = None


class HoldingResponse(BaseModel):
    """Full LLM response - list of issue holdings"""
    holdings: list[IssueHolding]


# ============================================
# System Prompt
# ============================================

SYSTEM_PROMPT = """SYSTEM ROLE:
You are a Senior Appellate Clerk for the Washington State Court of Appeals. Your job is to analyze "Mixed Outcome" opinions and map the specific legal outcome to the specific legal issue.

INPUT DATA:
1. Case Text (Focus on the final "Conclusion" or "Disposition" paragraphs).
2. Known Issues (A list of legal issues we have already extracted for this case).

YOUR TASK:
Determine the 'holding_type' (affirmed, reversed, remanded, vacated, harmless_error) for EACH issue in the `known_issues` list based strictly on the court's final ruling.

STRICT RULES:
1. Map Every Issue: You must return a result for every `issue_id` provided.
2. Output Format: Return ONLY a raw JSON list of objects. No markdown.
   Example: [{"issue_id": 123, "holding_type": "reversed", "reasoning": "..."}]
3. Ambiguity: If the court rejects an argument, it is 'affirmed'. If they find error, it is 'reversed' or 'remanded'."""


def build_user_prompt(case_text: str, issues: list[dict]) -> str:
    """Build the user prompt with case text and issues"""
    issues_json = json.dumps([
        {"issue_id": i["issue_id"], "category": i["category"], "subcategory": i["subcategory"]}
        for i in issues
    ], indent=2)
    
    return f"""INPUT TEMPLATE:
Case Text: \"\"\"{case_text}\"\"\"
Known Issues: {issues_json}

Return ONLY a raw JSON list. No markdown, no explanation."""


# ============================================
# Database Functions
# ============================================

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def ensure_holding_type_column(conn) -> bool:
    """Add holding_type column if it doesn't exist"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'issues_decisions' 
            AND column_name = 'holding_type';
        """)
        if not cur.fetchone():
            logger.info("Adding holding_type column to issues_decisions table...")
            cur.execute("""
                ALTER TABLE issues_decisions 
                ADD COLUMN holding_type CITEXT 
                CHECK (holding_type IN ('affirmed', 'reversed', 'remanded', 'vacated', 'harmless_error'));
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_issues_decisions_holding_type 
                ON issues_decisions(holding_type);
            """)
            conn.commit()
            logger.info("Column added successfully")
            return True
        return False


def fetch_partial_outcome_cases(conn) -> list[dict]:
    """Fetch all cases with partial outcomes"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                c.case_id,
                c.case_file_id,
                c.title,
                c.overall_case_outcome,
                c.full_text
            FROM cases c
            WHERE c.overall_case_outcome ILIKE '%partial%'
            AND c.full_text IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM issues_decisions id 
                WHERE id.case_id = c.case_id 
                AND id.holding_type IS NULL
            )
            ORDER BY c.case_id;
        """)
        return cur.fetchall()


def fetch_issues_for_case(conn, case_id: int) -> list[dict]:
    """Fetch issues for a specific case that need holding_type"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                issue_id,
                category,
                subcategory,
                issue_summary,
                appeal_outcome
            FROM issues_decisions
            WHERE case_id = %s
            AND holding_type IS NULL
            ORDER BY issue_id;
        """, (case_id,))
        return cur.fetchall()


def update_issue_holding(conn, issue_id: int, holding_type: str, reasoning: str = None):
    """Update a single issue with its holding type"""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE issues_decisions
            SET holding_type = %s
            WHERE issue_id = %s;
        """, (holding_type, issue_id))


# ============================================
# LLM Functions
# ============================================

def get_truncated_text(full_text: str) -> str:
    """Get the last N characters of the case text (conclusion/disposition)"""
    if not full_text:
        return ""
    if len(full_text) <= MAX_TEXT_CHARS:
        return full_text
    return "..." + full_text[-MAX_TEXT_CHARS:]


def analyze_holdings_with_llm(client: OpenAI, case_text: str, issues: list[dict]) -> list[dict]:
    """Call LLM to analyze holdings for each issue"""
    truncated_text = get_truncated_text(case_text)
    user_prompt = build_user_prompt(truncated_text, issues)
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # Low temperature for consistency
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        
        # Parse JSON response
        try:
            parsed = json.loads(content)
            
            # Handle various response formats
            if isinstance(parsed, list):
                holdings = parsed
            elif isinstance(parsed, dict):
                # Check for common wrapper keys
                if "holdings" in parsed:
                    holdings = parsed["holdings"]
                elif "results" in parsed:
                    holdings = parsed["results"]
                elif "issues" in parsed:
                    holdings = parsed["issues"]
                else:
                    # Might be a dict with issue_ids as keys, or the holding is the whole dict
                    # Check if it looks like a single holding
                    if "issue_id" in parsed and "holding_type" in parsed:
                        holdings = [parsed]
                    else:
                        # Dict with string keys mapping to holdings
                        holdings = [v for v in parsed.values() if isinstance(v, dict)]
            else:
                holdings = []
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"Raw content: {content[:500]}")
            return []
        
        # Validate each holding
        validated = []
        for h in holdings:
            if not isinstance(h, dict):
                continue
            try:
                holding = IssueHolding(**h)
                validated.append(holding.model_dump())
            except ValidationError as e:
                logger.warning(f"Validation error for holding: {e}")
                # Try to salvage with defaults
                if "issue_id" in h and isinstance(h["issue_id"], int):
                    ht = h.get("holding_type", "affirmed")
                    if ht not in ('affirmed', 'reversed', 'remanded', 'vacated', 'harmless_error'):
                        ht = 'affirmed'
                    validated.append({
                        "issue_id": h["issue_id"],
                        "holding_type": ht,
                        "reasoning": h.get("reasoning")
                    })
        
        return validated
        
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return []


# ============================================
# Main Processing
# ============================================

def process_case(client: OpenAI, case: dict, issues: list[dict]) -> tuple[int, list[dict], list[int]]:
    """
    Process a single case - analyze holdings with LLM.
    Returns (case_id, holdings_list, failed_issue_ids)
    Note: Does NOT update DB - just returns results for batch update.
    """
    case_id = case["case_id"]
    
    if not issues:
        return case_id, [], []
    
    # Analyze with LLM
    holdings = analyze_holdings_with_llm(client, case["full_text"], issues)
    
    if not holdings:
        logger.warning(f"Case {case_id}: No holdings returned from LLM")
        return case_id, [], [i["issue_id"] for i in issues]
    
    # Create lookup for quick access
    holdings_lookup = {h["issue_id"]: h for h in holdings}
    
    results = []
    failed = []
    
    for issue in issues:
        issue_id = issue["issue_id"]
        if issue_id in holdings_lookup:
            results.append(holdings_lookup[issue_id])
        else:
            logger.warning(f"Case {case_id}: Issue {issue_id} not in LLM response")
            failed.append(issue_id)
    
    return case_id, results, failed


def process_case_wrapper(args):
    """Wrapper for ThreadPoolExecutor"""
    client, case, issues = args
    try:
        return process_case(client, case, issues)
    except Exception as e:
        logger.error(f"Error processing case {case['case_id']}: {e}")
        return case["case_id"], [], [i["issue_id"] for i in issues]


def main():
    """Main entry point"""
    # Validate environment
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Create logs directory if needed
    os.makedirs("logs", exist_ok=True)
    
    # Initialize OpenAI client
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Connect to database
    logger.info("Connecting to database...")
    conn = get_db_connection()
    
    try:
        # Ensure column exists
        ensure_holding_type_column(conn)
        
        # Fetch cases to process
        logger.info("Fetching cases with partial outcomes...")
        cases = fetch_partial_outcome_cases(conn)
        logger.info(f"Found {len(cases)} cases to process")
        
        if not cases:
            logger.info("No cases need processing. Exiting.")
            return
        
        # Pre-fetch all issues for all cases
        logger.info("Pre-fetching issues for all cases...")
        case_issues = {}
        for case in cases:
            issues = fetch_issues_for_case(conn, case["case_id"])
            if issues:
                case_issues[case["case_id"]] = issues
        
        # Filter to only cases with issues
        cases_to_process = [c for c in cases if c["case_id"] in case_issues]
        logger.info(f"Cases with pending issues: {len(cases_to_process)}")
        
        # Process cases in parallel
        total_updated = 0
        total_errors = 0
        
        # Prepare work items
        work_items = [(client, case, case_issues[case["case_id"]]) for case in cases_to_process]
        
        logger.info(f"Processing {len(work_items)} cases with {MAX_WORKERS} concurrent workers...")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_case_wrapper, item): item[1]["case_id"] for item in work_items}
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="Processing cases"):
                case_id = futures[future]
                try:
                    result_case_id, holdings, failed = future.result()
                    
                    # Update database with results
                    for holding in holdings:
                        try:
                            update_issue_holding(
                                conn,
                                holding["issue_id"],
                                holding["holding_type"],
                                holding.get("reasoning")
                            )
                            total_updated += 1
                        except Exception as e:
                            logger.error(f"Failed to update issue {holding['issue_id']}: {e}")
                            total_errors += 1
                    
                    total_errors += len(failed)
                    
                except Exception as e:
                    logger.error(f"Future failed for case {case_id}: {e}")
                    total_errors += 1
            
            # Commit all changes
            conn.commit()
        
        # Summary
        logger.info("=" * 50)
        logger.info("PROCESSING COMPLETE")
        logger.info(f"Cases processed: {len(cases_to_process)}")
        logger.info(f"Issues updated: {total_updated}")
        logger.info(f"Errors: {total_errors}")
        logger.info("=" * 50)
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
