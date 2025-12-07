#!/usr/bin/env python3
"""Debug LLM extraction for Supreme Court case."""
import logging
import requests
import json

# Suppress PDF noise
logging.getLogger('pdfminer').setLevel(logging.WARNING)
for name in ['pdfminer.converter', 'pdfminer.pdfpage', 'pdfminer.pdfinterp', 'pdfminer.psparser', 'pdfminer.pdfdocument']:
    logging.getLogger(name).setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

from pipeline.pdf_extractor import PDFExtractor
from pipeline.llm_extractor import LLMExtractor, EXTRACTION_PROMPT, SYSTEM_PROMPT

pdf = PDFExtractor()
llm = LLMExtractor()

# Extract text
text, pages = pdf.extract_text('downloads/Supreme_Court_Opinions/2025/January/102,643-9_State v. Morgan.pdf')
print(f'Extracted {len(text)} chars')

# Make raw LLM call to see full response
# Try much smaller text to see if model can complete
truncated = text[:10000] if len(text) > 10000 else text
print(f"Using {len(truncated)} chars of text")
prompt = EXTRACTION_PROMPT.format(text=truncated)

payload = {
    "model": llm.model,
    "prompt": prompt,
    "system": SYSTEM_PROMPT,
    "stream": False,
    "options": {
        "temperature": 0.1, 
        "num_predict": 16384,
        "num_ctx": 32768,  # Try setting context window explicitly
    }
}

print("Calling Ollama...")
resp = requests.post(f"{llm.base_url}/api/generate", json=payload, timeout=600)
print(f"HTTP Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.status_code}")
    print(resp.text)
else:
    data = resp.json()
    raw = data.get("response", "")
    
    print(f"\n=== FULL OLLAMA RESPONSE ===")
    print(f"Response length: {len(raw)} chars")
    print(f"Done: {data.get('done')}")
    print(f"Done reason: {data.get('done_reason', 'N/A')}")
    print(f"Eval count (tokens generated): {data.get('eval_count', 'N/A')}")
    print(f"Total duration: {data.get('total_duration', 'N/A')}")
    
    print(f"\n=== Response content ===")
    print(raw[:3000] if len(raw) > 3000 else raw)
    
    if raw.strip().endswith("}"):
        print("\n[OK] Response ends with }")
    else:
        print(f"\n[PROBLEM] Response ends with: '{raw[-100:]}'")
