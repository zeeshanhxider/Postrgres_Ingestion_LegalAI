"""
Legal Case AI Extraction Service
Reliable AI extraction using proven approaches that work with Ollama and OpenAI.
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import json
import os
import logging

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# Import our models and prompts
from .models import LegalCaseExtraction
from .prompts import SYSTEM_PROMPT, HUMAN_TEMPLATE

# Ensure .env is loaded when this module is imported
load_dotenv()

logger = logging.getLogger(__name__)

def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", HUMAN_TEMPLATE)])


def extract_case_with_openai(case_text: str, case_info: Dict[str, Any]) -> Optional[LegalCaseExtraction]:
    try:
        llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-5"), temperature=1)
        structured_llm = llm.with_structured_output(LegalCaseExtraction, method="json_schema")
        prompt = _build_prompt()
        chain = prompt | structured_llm
        result = chain.invoke({"case_info": case_info, "case_text": case_text})
        if isinstance(result, LegalCaseExtraction):
            return result
        return LegalCaseExtraction.model_validate(result)
    except Exception as e:
        logger.error(f"❌ OpenAI extractor error: {e}")
        return None


def extract_case_with_ollama(case_text: str, case_info: Dict[str, Any]) -> Optional[LegalCaseExtraction]:
    # Try native ollama with structured output and enhanced validation
    try:
        import ollama
        from ollama import Client
        
        # Get configured base URL (supports remote Ollama servers)
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        client = Client(host=ollama_base_url)
        
        prompt = _build_prompt()
        msgs = prompt.format_messages(case_info=case_info, case_text=case_text)
        
        # Enhanced system message that FORCES all fields
        enhanced_system = msgs[0].content + "\n\n🚨 CRITICAL JSON REQUIREMENTS:\nYour response MUST include ALL 7 top-level fields in your JSON:\n1. case (object)\n2. appeals_judges (array - REQUIRED even if empty [])\n3. attorneys (array - REQUIRED even if empty [])\n4. parties (array - REQUIRED even if empty [])\n5. issues_decisions (array - REQUIRED even if empty [])\n6. arguments (array - REQUIRED even if empty [])\n7. precedents (array - REQUIRED even if empty [])\n\nIf ANY field is missing from your JSON, the extraction WILL FAIL. Always include empty arrays [] if no data exists for that category. Pay special attention to appeals_judges and attorneys - they are frequently present in legal documents."
        
        # Native Ollama Python client only accepts format='json', not schema objects
        # We'll include the schema in the system prompt instead
        schema_json = json.dumps(LegalCaseExtraction.model_json_schema(), indent=2)
        system_with_schema = f"{enhanced_system}\n\nIMPORTANT: You must return valid JSON that matches this exact schema:\n{schema_json}"
        
        logger.info(f"[AI] Connecting to Ollama at {ollama_base_url}...")
        
        response = client.chat(
            model=os.getenv("OLLAMA_MODEL", "llama3.3:latest"),
            messages=[
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": msgs[1].content},
            ],
            format="json",  # Native Ollama Python client only accepts 'json' string
            options={"temperature": 0.0},
        )
        
        # Debug: Log what Ollama actually returned
        logger.info(f"🔍 Ollama raw response: {response.message.content[:500]}...")
        
        # Parse with Pydantic validation (like Country.model_validate_json() in Python example)
        result = LegalCaseExtraction.model_validate_json(response.message.content)
        
        # Final validation: Log the actual counts for debugging
        logger.info(f"✅ Native Ollama extraction counts: appeals_judges={len(result.appeals_judges)}, attorneys={len(result.attorneys)}, parties={len(result.parties)}, issues_decisions={len(result.issues_decisions)}, arguments={len(result.arguments)}, precedents={len(result.precedents)}")
        
        return result
        
    except Exception as e:
        logger.warning(f"⚠️  Native Ollama failed, falling back to LangChain: {e}")

    # Fallback to LangChain ChatOllama
    try:
        from langchain_ollama import ChatOllama
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        logger.info(f"[AI] LangChain fallback - connecting to {ollama_base_url}...")
        llm = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.3:latest"), 
            base_url=ollama_base_url,
            temperature=0.0, 
            format="json"
        )
        try:
            structured_llm = llm.with_structured_output(LegalCaseExtraction, method="json_schema")
        except Exception:
            try:
                structured_llm = llm.with_structured_output(LegalCaseExtraction, method="json_mode")
            except Exception:
                structured_llm = llm.with_structured_output(LegalCaseExtraction)
        prompt = _build_prompt()
        chain = prompt | structured_llm
        result = chain.invoke({"case_info": case_info, "case_text": case_text})
        if isinstance(result, LegalCaseExtraction):
            return result
        return LegalCaseExtraction.model_validate(result)
    except Exception as e:
        logger.error(f"❌ LangChain Ollama extractor error: {e}")
        return None


def extract_case_data(case_text: str, case_info: Dict[str, Any]) -> Optional[LegalCaseExtraction]:
    """Main extraction function that prioritizes Ollama if USE_OLLAMA=true"""
    
    # Check if we should use Ollama
    use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
    
    if use_ollama:
        logger.info("Using Ollama for extraction (USE_OLLAMA=true)...")
        result = extract_case_with_ollama(case_text, case_info)
        if result:
            logger.info("Ollama extraction successful")
            return result
        logger.warning("Ollama extraction failed, trying OpenAI...")
    
    # Try OpenAI if available
    if os.getenv("OPENAI_API_KEY"):
        logger.info("Using OpenAI for extraction...")
        result = extract_case_with_openai(case_text, case_info)
        if result:
            logger.info("OpenAI extraction successful")
            return result
        logger.warning("OpenAI extraction failed")
    
    # Final fallback to Ollama if not already tried
    if not use_ollama:
        logger.info("Falling back to Ollama...")
        result = extract_case_with_ollama(case_text, case_info)
        if result:
            logger.info("Fallback Ollama extraction successful")
            return result
    
    logger.error("All extraction methods failed")
    return None
