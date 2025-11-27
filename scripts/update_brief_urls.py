"""
Update briefs table with source URLs from expanded_matched CSVs.

The CSVs have: case_number, document_type, case_id, pdf_url
The briefs table has source_file like: 685074_Respondent's.pdf

Matching logic:
1. Primary: Match case_id from source_file prefix + brief_type
2. Fallback: Match case_id from source_file prefix to any URL in CSV with same case_id
3. Edge case: For special brief types (Amended, Cross-Appellant), find URL containing source_file pattern
"""

import os
import csv
import re
import psycopg2
from pathlib import Path
from urllib.parse import unquote

# Database connection
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "cases_llama3_3",
    "user": "postgres",
    "password": "postgres123"
}

CSV_DIR = Path("output_csvs/expanded_matched")

def extract_case_id_from_source_file(source_file: str) -> str:
    """Extract the numeric case_id prefix from source_file."""
    # Pattern: 685074_Respondent's.pdf -> 685074
    match = re.match(r'^(\d+)', source_file)
    return match.group(1) if match else None

def map_csv_doc_type_to_brief_type(doc_type: str) -> str:
    """Map CSV document_type to brief_type used in database."""
    doc_type_lower = doc_type.lower().strip()
    if 'reply' in doc_type_lower:
        return 'Reply'
    elif 'respondent' in doc_type_lower:
        return 'Response'
    elif 'appellant' in doc_type_lower:
        return 'Opening'
    return None

def normalize_source_file_for_url_match(source_file: str) -> str:
    """
    Convert source_file to pattern that would appear in URL.
    697471_Amended_Appellant's.pdf -> "697471 Amended Appellant's" or "697471%20Amended%20Appellant"
    """
    # Remove .pdf extension
    name = source_file.replace('.pdf', '').replace('.PDF', '')
    # Replace underscores with spaces (URLs use %20 for spaces)
    name = name.replace('_', ' ')
    return name.lower()

def load_all_urls_from_csvs():
    """
    Load all URLs from CSV files into multiple lookup structures:
    1. url_lookup: (case_id, brief_type) -> url (primary matching)
    2. url_by_case_id: case_id -> [(doc_type, url), ...] (fallback for edge cases)
    """
    url_lookup = {}
    url_by_case_id = {}
    
    for csv_file in CSV_DIR.glob("*_expanded.csv"):
        print(f"Loading {csv_file.name}...")
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                case_id = row.get('case_id', '').strip()
                doc_type = row.get('document_type', '').strip()
                pdf_url = row.get('pdf_url', '').strip()
                
                if case_id and doc_type and pdf_url:
                    # Store in case_id lookup for fallback matching
                    if case_id not in url_by_case_id:
                        url_by_case_id[case_id] = []
                    url_by_case_id[case_id].append((doc_type, pdf_url))
                    
                    # Primary lookup by brief_type
                    brief_type = map_csv_doc_type_to_brief_type(doc_type)
                    if brief_type:
                        key = (case_id, brief_type)
                        if key not in url_lookup:
                            url_lookup[key] = pdf_url
    
    print(f"Loaded {len(url_lookup)} primary URL mappings")
    print(f"Loaded {len(url_by_case_id)} case_id entries for fallback matching")
    return url_lookup, url_by_case_id

def find_best_url_match(source_file: str, case_id: str, brief_type: str, 
                        url_lookup: dict, url_by_case_id: dict) -> str:
    """
    Find the best URL match for a brief using multiple strategies.
    """
    # Strategy 1: Direct lookup by (case_id, brief_type)
    key = (case_id, brief_type)
    if key in url_lookup:
        return url_lookup[key]
    
    # Strategy 2: Check all URLs for this case_id and find one matching source_file pattern
    if case_id in url_by_case_id:
        source_pattern = normalize_source_file_for_url_match(source_file)
        
        for doc_type, url in url_by_case_id[case_id]:
            # Decode URL and normalize for comparison
            decoded_url = unquote(url).lower()
            
            # Check if key parts of source_file appear in URL
            # e.g., "amended appellant's" should match URL containing "Amended%20Appellant"
            source_words = source_pattern.split()
            
            # For Amended briefs
            if 'amended' in source_pattern and 'amended' in decoded_url:
                if 'appellant' in source_pattern and 'appellant' in decoded_url:
                    return url
                    
            # For Cross-Appellant briefs
            if 'cross-appellant' in source_pattern or 'cross_appellant' in source_pattern:
                if 'cross-appellant' in decoded_url or 'cross appellant' in decoded_url:
                    return url
            
            # For Respondent Cross-Appellant
            if 'respondent' in source_pattern and 'cross' in source_pattern:
                if 'respondent' in decoded_url and 'cross' in decoded_url:
                    return url
            
            # Generic: check if most words from source appear in URL
            matches = sum(1 for word in source_words if len(word) > 3 and word in decoded_url)
            if matches >= len(source_words) - 1 and matches >= 2:
                return url
    
    # Strategy 3: Any URL with this case_id (last resort)
    if case_id in url_by_case_id and url_by_case_id[case_id]:
        # Return first URL as fallback
        return url_by_case_id[case_id][0][1]
    
    return None

def update_briefs_with_urls():
    """Update briefs table with source URLs."""
    url_lookup, url_by_case_id = load_all_urls_from_csvs()
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Get all briefs
    cur.execute("SELECT brief_id, source_file, brief_type, source_url FROM briefs")
    briefs = cur.fetchall()
    
    updated = 0
    not_found = 0
    already_set = 0
    
    for brief_id, source_file, brief_type, existing_url in briefs:
        if existing_url:
            already_set += 1
            continue
            
        # Extract case_id from source_file
        case_id = extract_case_id_from_source_file(source_file)
        if not case_id:
            print(f"  Could not extract case_id from: {source_file}")
            not_found += 1
            continue
        
        # Find best URL match using multiple strategies
        url = find_best_url_match(source_file, case_id, brief_type, url_lookup, url_by_case_id)
        
        if url:
            cur.execute(
                "UPDATE briefs SET source_url = %s WHERE brief_id = %s",
                (url, brief_id)
            )
            updated += 1
            if updated % 20 == 0:
                print(f"  Updated {updated} briefs...")
        else:
            print(f"  No URL found for: {source_file} (case_id={case_id}, type={brief_type})")
            not_found += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"\n=== Summary ===")
    print(f"Updated: {updated}")
    print(f"Already set: {already_set}")
    print(f"Not found: {not_found}")
    print(f"Total briefs: {len(briefs)}")

if __name__ == "__main__":
    update_briefs_with_urls()
