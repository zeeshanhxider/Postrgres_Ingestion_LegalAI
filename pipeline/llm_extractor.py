"""
LLM-based Extraction using Ollama
Extracts structured legal case data from PDF text using local LLM.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .models import (
    ExtractedCase, Party, Attorney, Judge, 
    Citation, Statute, Issue
)

logger = logging.getLogger(__name__)

# System prompt for legal case extraction
SYSTEM_PROMPT = """You are an expert legal document analyzer for Washington State case law. Extract structured data from the provided court opinion into valid JSON format.

CRITICAL RULES:
1. Extract ONLY information explicitly stated in the document text.
2. If information is not found, use null.
3. Do not Hallucinate or guess relationships (e.g., do not guess which party "won" if it is a complex split decision).
4. Escape all double quotes within strings to ensure the output is parseable JSON.
5. Do not include markdown formatting (```json) in your response; return raw JSON only."""

EXTRACTION_PROMPT = """Analyze this Washington State court opinion and extract the following deep-level case details.

CASE TEXT:
{text}

Extract this JSON structure:
{{
    "summary": "Comprehensive 5-6 sentence summary covering the core points of the case. This must include: 1) The key background facts (what happened?), 2) The procedural history (how did it get to this court?), 3) The primary legal issues raised, 4) The court's reasoning on those issues, and 5) The final disposition.",
    "case_category": "Criminal|Civil|Family|Administrative|Juvenile|Real Property|Tort|Contract|Constitutional|Employment|Other",
    "originating_court": {{
        "county": "County where the case originated (e.g., 'King', 'Spokane')",
        "court_name": "Full name of lower court (e.g., 'King County Superior Court')",
        "trial_judge": "Name of the trial court judge if mentioned",
        "source_docket_number": "Lower court case number if mentioned"
    }},
    "outcome": {{
        "disposition": "Affirmed|Reversed|Remanded|Dismissed|Affirmed in part/Reversed in part|Other",
        "details": "Specific details (e.g., 'Conviction affirmed, but remanded for resentencing due to offender score error')",
        "prevailing_party": "Appellant|Respondent|Petitioner|Plaintiff|Defendant|Split/Remanded|Neither"
    }},
    "parties_parsed": [
        {{
            "name": "Full party name (e.g., 'Justin Dean Vanhollebeke')",
            "appellate_role": "Appellant|Respondent|Petitioner|Cross-Appellant",
            "trial_role": "Plaintiff|Defendant|State|Intervenor|null",
            "type": "Individual|Government|Corporation|Organization|Union"
        }}
    ],
    "legal_representation": [
        {{
            "attorney_name": "Name of attorney",
            "representing": "Name of party they represent",
            "firm_or_agency": "Law firm, Prosecutor's Office, or Agency name"
        }}
    ],
    "judicial_panel": [
        {{
            "judge_name": "Last name of appellate judge",
            "role": "Author|Concurring|Dissenting|Signatory (e.g., 'WE CONCUR')"
        }}
    ],
    "legal_analysis": {{
        "key_statutes_cited": [
            "List of specific RCWs cited (e.g., 'RCW 9.94A.525', 'RCW 42.17A.765')"
        ],
        "major_issues": [
            {{
                "question": "Brief summary of the legal question (e.g., 'Was the warrantless search of the borrowed truck lawful?')",
                "ruling": "How the court answered (e.g., 'Yes, the owner's consent overrode the borrower's objection.')"
            }}
        ]
    }}
}}"""


class LLMExtractor:
    """
    Extract structured legal case data using Ollama LLM.
    """
    
    def __init__(
        self,
        model: str = None,
        base_url: str = None,
        timeout: int = 120
    ):
        """
        Initialize the LLM extractor.
        
        Args:
            model: Ollama model name (default: from OLLAMA_MODEL env or 'llama3.1:8b')
            base_url: Ollama server URL (default: from OLLAMA_BASE_URL env or 'http://localhost:11434')
            timeout: Request timeout in seconds
        """
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = timeout
        
        logger.info(f"LLM Extractor initialized with model: {self.model}")
    
    def extract(self, text: str, max_chars: int = 30000) -> Dict[str, Any]:
        """
        Extract structured data from case text using LLM.
        
        Args:
            text: Full text of the legal document
            max_chars: Maximum characters to send to LLM (truncate if longer)
            
        Returns:
            Dictionary with extracted data
        """
        # Truncate text if too long (keep beginning and end for context)
        if len(text) > max_chars:
            half = max_chars // 2
            text = text[:half] + "\n\n[...middle content truncated...]\n\n" + text[-half:]
            logger.info(f"Text truncated to {max_chars} chars")
        
        # Build the prompt
        prompt = EXTRACTION_PROMPT.format(text=text)
        
        try:
            # Call Ollama
            response = self._call_ollama(prompt)
            
            # Parse JSON response
            extracted = self._parse_json_response(response)
            
            return extracted
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {"error": str(e)}
    
    def _call_ollama(self, prompt: str) -> str:
        """
        Make a request to Ollama API.
        
        Args:
            prompt: The prompt to send
            
        Returns:
            Response text from the model
        """
        import requests
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": 0.1,      # Low temperature for consistent extraction
                "num_predict": 16384,    # Allow much longer responses for complex case JSON
                "num_ctx": 32768,        # Large context window - required for long legal documents
            }
        }
        
        logger.info(f"Calling Ollama ({self.model})...")
        
        response = requests.post(
            url,
            json=payload,
            timeout=self.timeout
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Ollama request failed: {response.status_code} - {response.text}")
        
        result = response.json()
        return result.get("response", "")
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response, handling common issues.
        
        Args:
            response: Raw response from LLM
            
        Returns:
            Parsed dictionary
        """
        # Clean up response
        text = response.strip()
        
        # Debug: log first 500 chars of raw response
        logger.debug(f"Raw LLM response (first 500 chars): {text[:500]}")
        
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        # Find JSON object boundaries
        start = text.find("{")
        end = text.rfind("}") + 1
        
        if start == -1:
            logger.warning(f"No JSON object found in response. Response preview: {text[:300]}...")
            return {}
        
        # Check if JSON was truncated (no closing brace)
        if end == 0:
            logger.warning(f"JSON response appears truncated (no closing brace). Attempting regex extraction...")
            return self._fix_and_parse_json(text[start:])
        
        json_str = text[start:end]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            # Try to fix common issues
            return self._fix_and_parse_json(json_str)
    
    def _fix_and_parse_json(self, json_str: str) -> Dict[str, Any]:
        """
        Attempt to fix common JSON issues from LLM output.
        Uses multiple strategies to recover malformed JSON.
        """
        import re
        
        original = json_str
        
        # Strategy 1: Fix trailing commas
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        try:
            return json.loads(json_str)
        except:
            pass
        
        # Strategy 2: Fix single quotes
        json_str = original.replace("'", '"')
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        try:
            return json.loads(json_str)
        except:
            pass
        
        # Strategy 3: Fix unescaped quotes in strings
        # Replace \" patterns that might be broken
        json_str = original
        json_str = re.sub(r'(?<!\\)"(?=[^:,\[\]{}]*"[^:,\[\]{}]*":)', r'\\"', json_str)
        
        try:
            return json.loads(json_str)
        except:
            pass
        
        # Strategy 4: Try to extract just the top-level keys we need
        result = {}
        try:
            # Extract summary
            summary_match = re.search(r'"summary"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', original)
            if summary_match:
                result['summary'] = summary_match.group(1).replace('\\"', '"')
            
            # Extract case_type
            case_type_match = re.search(r'"case_type"\s*:\s*"([^"]*)"', original)
            if case_type_match:
                result['case_type'] = case_type_match.group(1)
            
            # Extract county
            county_match = re.search(r'"county"\s*:\s*"([^"]*)"', original)
            if county_match:
                result['county'] = county_match.group(1)
            
            # Extract trial_judge
            trial_judge_match = re.search(r'"trial_judge"\s*:\s*"([^"]*)"', original)
            if trial_judge_match:
                result['trial_judge'] = trial_judge_match.group(1)
            
            # Extract source_docket_number
            source_docket_match = re.search(r'"source_docket_number"\s*:\s*"([^"]*)"', original)
            if source_docket_match:
                result['source_docket_number'] = source_docket_match.group(1)
            
            # Extract appeal_outcome
            appeal_outcome_match = re.search(r'"appeal_outcome"\s*:\s*"([^"]*)"', original)
            if appeal_outcome_match:
                result['appeal_outcome'] = appeal_outcome_match.group(1)
            
            # Extract winner fields
            winner_legal_match = re.search(r'"winner_legal_role"\s*:\s*"([^"]*)"', original)
            if winner_legal_match:
                result['winner_legal_role'] = winner_legal_match.group(1)
            
            winner_personal_match = re.search(r'"winner_personal_role"\s*:\s*"([^"]*)"', original)
            if winner_personal_match:
                result['winner_personal_role'] = winner_personal_match.group(1)
            
            # Try to extract arrays using a more robust approach
            # Find parties_parsed array (or parties for legacy)
            parties_match = re.search(r'"parties_parsed"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if not parties_match:
                parties_match = re.search(r'"parties"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if parties_match:
                try:
                    parties_json = '[' + parties_match.group(1) + ']'
                    parties_json = re.sub(r',\s*]', ']', parties_json)
                    result['parties_parsed'] = json.loads(parties_json)
                except:
                    pass
            
            # Find judicial_panel array (or judges for legacy)
            judges_match = re.search(r'"judicial_panel"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if not judges_match:
                judges_match = re.search(r'"judges"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if judges_match:
                try:
                    judges_json = '[' + judges_match.group(1) + ']'
                    judges_json = re.sub(r',\s*]', ']', judges_json)
                    result['judicial_panel'] = json.loads(judges_json)
                except:
                    pass
            
            # Find legal_representation array
            legal_rep_match = re.search(r'"legal_representation"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if legal_rep_match:
                try:
                    legal_rep_json = '[' + legal_rep_match.group(1) + ']'
                    legal_rep_json = re.sub(r',\s*]', ']', legal_rep_json)
                    result['legal_representation'] = json.loads(legal_rep_json)
                except:
                    pass
            
            # Find citations array
            citations_match = re.search(r'"citations"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if citations_match:
                try:
                    citations_json = '[' + citations_match.group(1) + ']'
                    citations_json = re.sub(r',\s*]', ']', citations_json)
                    result['citations'] = json.loads(citations_json)
                except:
                    pass
            
            # Find statutes array
            statutes_match = re.search(r'"statutes"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if statutes_match:
                try:
                    statutes_json = '[' + statutes_match.group(1) + ']'
                    statutes_json = re.sub(r',\s*]', ']', statutes_json)
                    result['statutes'] = json.loads(statutes_json)
                except:
                    pass
            
            # Find issues array
            issues_match = re.search(r'"issues"\s*:\s*\[(.*?)\]', original, re.DOTALL)
            if issues_match:
                try:
                    issues_json = '[' + issues_match.group(1) + ']'
                    issues_json = re.sub(r',\s*]', ']', issues_json)
                    result['issues'] = json.loads(issues_json)
                except:
                    pass
            
            if result:
                logger.info(f"Recovered {len(result)} fields from malformed JSON")
                return result
                
        except Exception as e:
            logger.error(f"JSON recovery also failed: {e}")
        
        logger.error("Could not parse JSON even after fixes")
        return {}
    
    def build_extracted_case(self, llm_result: Dict[str, Any]) -> ExtractedCase:
        """
        Convert LLM extraction result to ExtractedCase dataclass.
        
        Args:
            llm_result: Dictionary from LLM extraction
            
        Returns:
            ExtractedCase object
        """
        case = ExtractedCase()
        
        # Normalize keys from new prompt schema to expected keys
        # parties_parsed -> parties
        if "parties_parsed" in llm_result and "parties" not in llm_result:
            llm_result["parties"] = llm_result["parties_parsed"]
        # judicial_panel -> judges
        if "judicial_panel" in llm_result and "judges" not in llm_result:
            llm_result["judges"] = llm_result["judicial_panel"]
        # legal_representation -> attorneys
        if "legal_representation" in llm_result and "attorneys" not in llm_result:
            llm_result["attorneys"] = llm_result["legal_representation"]
        # originating_court nested fields
        if "originating_court" in llm_result and isinstance(llm_result["originating_court"], dict):
            orig = llm_result["originating_court"]
            if not llm_result.get("county"):
                llm_result["county"] = orig.get("county")
            if not llm_result.get("trial_court"):
                llm_result["trial_court"] = orig.get("court_name")
            if not llm_result.get("trial_judge"):
                llm_result["trial_judge"] = orig.get("trial_judge")
            if not llm_result.get("source_docket_number"):
                llm_result["source_docket_number"] = orig.get("source_docket_number")
        # outcome nested fields
        if "outcome" in llm_result and isinstance(llm_result["outcome"], dict):
            out = llm_result["outcome"]
            if not llm_result.get("appeal_outcome"):
                llm_result["appeal_outcome"] = out.get("disposition")
            if not llm_result.get("outcome_detail"):
                llm_result["outcome_detail"] = out.get("details")
            if not llm_result.get("winner_legal_role"):
                llm_result["winner_legal_role"] = out.get("prevailing_party")
        # case_category -> case_type
        if "case_category" in llm_result and not llm_result.get("case_type"):
            llm_result["case_type"] = llm_result["case_category"]
        # legal_analysis -> issues and statutes
        if "legal_analysis" in llm_result and isinstance(llm_result["legal_analysis"], dict):
            analysis = llm_result["legal_analysis"]
            # major_issues -> issues
            if "major_issues" in analysis and "issues" not in llm_result:
                llm_result["issues"] = []
                for issue in analysis.get("major_issues", []):
                    if isinstance(issue, dict):
                        llm_result["issues"].append({
                            "summary": issue.get("question", ""),
                            "outcome": issue.get("ruling", ""),
                            "category": "Other"
                        })
            # key_statutes_cited -> statutes
            if "key_statutes_cited" in analysis and "statutes" not in llm_result:
                llm_result["statutes"] = []
                for statute in analysis.get("key_statutes_cited", []):
                    if isinstance(statute, str):
                        llm_result["statutes"].append({"citation": statute})
        
        # Simple fields
        case.summary = llm_result.get("summary", "")
        case.case_type = llm_result.get("case_type", "")
        case.county = llm_result.get("county")
        case.trial_court = llm_result.get("trial_court")
        case.trial_judge = llm_result.get("trial_judge")
        case.source_docket_number = llm_result.get("source_docket_number")
        case.appeal_outcome = llm_result.get("appeal_outcome")
        case.outcome_detail = llm_result.get("outcome_detail")
        case.winner_legal_role = llm_result.get("winner_legal_role")
        case.winner_personal_role = llm_result.get("winner_personal_role")
        
        # Parties (handles both old and new schema field names)
        for p in llm_result.get("parties", []):
            if isinstance(p, dict):
                name = p.get("name")
                # Build role from appellate_role and trial_role if present
                role = p.get("role") or p.get("appellate_role") or "Unknown"
                if p.get("trial_role") and p.get("trial_role") != "null":
                    role = f"{role} ({p.get('trial_role')})"
                party_type = p.get("party_type") or p.get("type")
                if name:
                    case.parties.append(Party(
                        name=name,
                        role=role,
                        party_type=party_type
                    ))
        
        # Attorneys (handles both old and new schema field names)
        for a in llm_result.get("attorneys", []):
            if isinstance(a, dict):
                name = a.get("name") or a.get("attorney_name")
                representing = a.get("representing", "Unknown")
                firm_name = a.get("firm_name") or a.get("firm_or_agency")
                if name:
                    case.attorneys.append(Attorney(
                        name=name,
                        representing=representing,
                        firm_name=firm_name
                    ))
        
        # Judges (handles both old and new schema field names)
        for j in llm_result.get("judges", []):
            if isinstance(j, dict):
                name = j.get("name") or j.get("judge_name")
                role = j.get("role", "Unknown")
                if name:
                    case.judges.append(Judge(
                        name=name,
                        role=role
                    ))
        
        # Citations
        for c in llm_result.get("citations", []):
            if isinstance(c, dict) and c.get("full_citation"):
                case.citations.append(Citation(
                    full_citation=c["full_citation"],
                    case_name=c.get("case_name"),
                    relationship=c.get("relationship")
                ))
        
        # Statutes
        for s in llm_result.get("statutes", []):
            if isinstance(s, dict) and s.get("citation"):
                case.statutes.append(Statute(
                    citation=s["citation"],
                    title=s.get("title")
                ))
        
        # Issues
        for i in llm_result.get("issues", []):
            if isinstance(i, dict) and i.get("summary"):
                case.issues.append(Issue(
                    category=i.get("category", "Other"),
                    subcategory=i.get("subcategory", "General"),
                    summary=i["summary"],
                    outcome=i.get("outcome"),
                    winner=i.get("winner")
                ))
        
        case.extraction_timestamp = datetime.now()
        case.llm_model = self.model
        case.extraction_successful = "error" not in llm_result
        
        if "error" in llm_result:
            case.error_message = llm_result["error"]
        
        return case
    
    def test_connection(self) -> bool:
        """Test if Ollama is available and the model is loaded."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if any(self.model in name for name in model_names):
                    logger.info(f"Ollama connection OK, model {self.model} available")
                    return True
                else:
                    logger.warning(f"Model {self.model} not found. Available: {model_names}")
                    return False
            return False
        except Exception as e:
            logger.error(f"Ollama connection failed: {e}")
            return False
