"""
Switch between Ollama and OpenAI embedding providers
"""

import os
import sys
from dotenv import load_dotenv

def update_env_file(use_ollama: bool):
    """
    Update the .env file to switch between Ollama and OpenAI
    
    Args:
        use_ollama: True for Ollama, False for OpenAI
    """
    env_file = ".env"
    
    if not os.path.exists(env_file):
        print(f"❌ Error: {env_file} not found")
        return
    
    # Read the file
    with open(env_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Update the USE_OLLAMA line
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith('USE_OLLAMA='):
            lines[i] = f'USE_OLLAMA={str(use_ollama).lower()}\n'
            updated = True
            break
    
    if not updated:
        print("❌ Error: USE_OLLAMA not found in .env file")
        return
    
    # Write back
    with open(env_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    # Reload environment variables from .env
    load_dotenv(override=True)
    
    provider = "Ollama" if use_ollama else "OpenAI"
    print(f"✅ Switched to {provider} embeddings")
    print(f"\nCurrent configuration:")
    print(f"  Provider: {provider}")
    
    if use_ollama:
        print(f"  Model: {os.getenv('OLLAMA_EMBED_MODEL', 'mxbai-embed-large')}")
        print(f"  URL: {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
        print(f"\n⚠️  Make sure Ollama is running and accessible")
    else:
        print(f"  Model: text-embedding-3-large")
        print(f"  Dimensions: 1024")
        api_key = os.getenv('OPENAI_API_KEY', '')
        if api_key:
            print(f"  API Key: {api_key[:20]}...{api_key[-4:]}")
        else:
            print(f"  ❌ Warning: OPENAI_API_KEY not set in .env")

def main():
    if len(sys.argv) != 2 or sys.argv[1].lower() not in ['ollama', 'openai']:
        print("Usage: python switch_embedding_provider.py [ollama|openai]")
        print("\nExamples:")
        print("  python switch_embedding_provider.py ollama")
        print("  python switch_embedding_provider.py openai")
        sys.exit(1)
    
    use_ollama = sys.argv[1].lower() == 'ollama'
    update_env_file(use_ollama)

if __name__ == "__main__":
    main()
