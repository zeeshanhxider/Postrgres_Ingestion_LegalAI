#!/usr/bin/env python3
"""
Real PDF Ingestion Test
Tests hybrid extraction on actual PDFs from each court category:
1. Supreme Court
2. Court of Appeals Published
3. Court of Appeals Partially Published
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Set up Ollama
os.environ['OLLAMA_BASE_URL'] = 'https://ollama.legaldb.ai'
os.environ['OLLAMA_MODEL'] = 'qwen:32b'
os.environ['AI_PROVIDER'] = 'ollama'

# Configure logging to file
log_file = 'logs/real_pdf_test.log'
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='w')
    ]
)
logger = logging.getLogger(__name__)

# Test PDFs - one from each category
test_pdfs = [
    {
        'path': Path('downloads/Supreme_Court_Opinions/2024/January/101,045-1_Barlow v. State.pdf'),
        'category': 'Supreme Court',
        'metadata': {
            'case_number': '101,045-1',
            'title': 'Barlow v. State',
            'court_level': 'Supreme Court',
            'division': '',
            'publication': 'Published',
            'publication_status': 'Published'
        }
    },
    {
        'path': Path('downloads/Court_of_Appeals_Published/2024/January/83404-5_I.pdf'),
        'category': 'Court of Appeals Published',
        'metadata': {
            'case_number': '83404-5-I',
            'title': 'Case 83404-5-I',
            'court_level': 'Court of Appeals',
            'division': 'I',
            'publication': 'Published',
            'publication_status': 'Published'
        }
    },
    {
        'path': Path('downloads/Court_of_Appeals_Published_in_Part/2024/January/39019-5_III.pdf'),
        'category': 'Court of Appeals Partially Published',
        'metadata': {
            'case_number': '39019-5-III',
            'title': 'Case 39019-5-III',
            'court_level': 'Court of Appeals',
            'division': 'III',
            'publication': 'Partially Published',
            'publication_status': 'Published in Part'
        }
    }
]

def main():
    print('=' * 80)
    print('REAL PDF INGESTION TEST - 3 Categories')
    print('=' * 80)
    
    from app.database import engine
    from app.services.case_ingestor import LegalCaseIngestor
    
    ingestor = LegalCaseIngestor(engine)
    
    results = []
    
    for test in test_pdfs:
        print()
        print('=' * 80)
        print(f"Category: {test['category']}")
        print(f"File: {test['path'].name}")
        print('=' * 80)
        
        pdf_path = test['path']
        if not pdf_path.exists():
            print(f'ERROR: PDF not found: {pdf_path}')
            results.append({'category': test['category'], 'status': 'NOT_FOUND'})
            continue
        
        # Read PDF
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        source_file_info = {
            'filename': pdf_path.name,
            'file_path': str(pdf_path.absolute())
        }
        
        try:
            result = ingestor.ingest_pdf_case(
                pdf_content=pdf_content,
                metadata=test['metadata'],
                source_file_info=source_file_info,
                extraction_mode='hybrid'
            )
            
            print("SUCCESS!")
            print(f"  Case ID: {result['case_id']}")
            print(f"  Extraction Mode: {result['extraction_mode']}")
            print(f"  Chunks Created: {result['chunks_created']}")
            print(f"  Words Processed: {result['words_processed']}")
            print(f"  Case Stats: {result['case_stats']}")
            
            results.append({
                'category': test['category'],
                'status': 'SUCCESS',
                'case_id': result['case_id'],
                'stats': result['case_stats']
            })
            
        except Exception as e:
            print(f'FAILED: {e}')
            import traceback
            traceback.print_exc()
            results.append({'category': test['category'], 'status': 'FAILED', 'error': str(e)})
    
    # Summary
    print()
    print('=' * 80)
    print('SUMMARY')
    print('=' * 80)
    for r in results:
        status = r['status']
        category = r['category']
        if status == 'SUCCESS':
            print(f"  [OK] {category}: Case ID {r['case_id']}")
        else:
            print(f"  [FAIL] {category}: {status}")
    
    print()
    print(f'Log file: {log_file}')
    print('=' * 80)

if __name__ == '__main__':
    main()
