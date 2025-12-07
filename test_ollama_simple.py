"""Simple test of Ollama response length."""
import requests

url = "https://ollama.legaldb.ai/api/generate"

# Test 1: Simple counting task
payload = {
    "model": "qwen2.5:32b-instruct",
    "prompt": "Count from 1 to 200, one number per line.",
    "stream": False,
    "options": {
        "num_predict": 2000,
        "num_ctx": 4096,
    }
}

print("Test 1: Simple counting task")
r = requests.post(url, json=payload, timeout=120)
j = r.json()
print(f"Response length: {len(j.get('response', ''))}")
print(f"Tokens generated: {j.get('eval_count', 0)}")
print(f"Done reason: {j.get('done_reason', 'N/A')}")
print(f"First 200 chars: {j.get('response', '')[:200]}")
print(f"Last 100 chars: {j.get('response', '')[-100:]}")
print()

# Test 2: JSON generation with simple structure
payload2 = {
    "model": "qwen2.5:32b-instruct",
    "prompt": """Generate a JSON object with 10 people, each having: name, age, city, occupation.
Return ONLY valid JSON, no other text.""",
    "stream": False,
    "options": {
        "num_predict": 4000,
        "num_ctx": 8192,
    }
}

print("Test 2: JSON generation")
r2 = requests.post(url, json=payload2, timeout=120)
j2 = r2.json()
print(f"Response length: {len(j2.get('response', ''))}")
print(f"Tokens generated: {j2.get('eval_count', 0)}")
print(f"Done reason: {j2.get('done_reason', 'N/A')}")
resp = j2.get('response', '')
print(f"First 300 chars: {resp[:300]}")
print(f"Last 200 chars: {resp[-200:]}")
