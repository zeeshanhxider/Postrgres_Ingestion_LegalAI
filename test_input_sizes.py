"""Test Ollama with varying input sizes."""
import requests

url = "https://ollama.legaldb.ai/api/generate"

# Minimal extraction prompt
prompt_template = """Extract the following from this legal case text and return ONLY valid JSON:

TEXT:
{text}

Return JSON with:
- summary (1-2 sentences)
- parties (list of names)
- county

JSON:"""

# Test with increasing text sizes
test_sizes = [1000, 3000, 5000, 8000, 10000]

sample_text = """
IN THE SUPREME COURT OF THE STATE OF WASHINGTON

STATE OF WASHINGTON, Respondent,
v.
MONTREAL LEANTHONY MORGAN SR., Petitioner.

No. 102643-9

MADSEN, J. — Montreal Leanthony Morgan Sr. was convicted of crimes related to the death of Fabian Alvarez.
The State requested $10,480 in restitution for crime victims compensation act (CVCA) benefits paid by the
Department of Labor and Industries. Morgan argued for a reduction due to mitigating factors. The trial court
ordered the full amount. The Court of Appeals affirmed. We granted review to determine whether the trial
court has discretion to reduce restitution for CVCA benefits. We hold that the statute does not allow such
discretion and affirm.

FACTS AND PROCEDURAL HISTORY

Morgan was charged with murder in the first degree, assault in the first degree, and drive-by shooting.
Following a jury trial in King County Superior Court, Morgan was convicted of manslaughter in the first
degree as a lesser included offense of murder, assault in the first degree, and drive-by shooting.

At sentencing, the State requested restitution of $10,480 for CVCA benefits paid to the victim's family.
""" * 20  # Repeat to have enough text

for size in test_sizes:
    text = sample_text[:size]
    prompt = prompt_template.format(text=text)
    
    payload = {
        "model": "qwen2.5:32b-instruct",
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 2000,
            "num_ctx": 16384,
            "temperature": 0.1,
        }
    }
    
    print(f"\n=== Testing with {size} chars input ===")
    print(f"Prompt length: {len(prompt)} chars")
    
    try:
        r = requests.post(url, json=payload, timeout=180)
        j = r.json()
        resp = j.get('response', '')
        print(f"Response length: {len(resp)} chars")
        print(f"Tokens generated: {j.get('eval_count', 0)}")
        print(f"Done reason: {j.get('done_reason', 'N/A')}")
        print(f"Response preview: {resp[:400]}")
        if not resp.rstrip().endswith('}'):
            print("WARNING: Response does not end with }")
    except Exception as e:
        print(f"Error: {e}")
