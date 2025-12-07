"""
N-gram phrase extraction and indexing for legal documents
This enables phrase-based search and legal terminology discovery
"""

import logging
from typing import List, Dict, Tuple, Set, Optional
from collections import Counter
from sqlalchemy import text
from sqlalchemy.engine import Engine
from .word_processor import WordProcessor

logger = logging.getLogger(__name__)

class PhraseExtractor:
    """Extract and index n-gram phrases from legal text"""
    
    def __init__(self, db_engine: Engine):
        self.db = db_engine
        self.word_processor = WordProcessor(db_engine)
        
    def extract_ngrams(self, tokens: List[str], n: int, min_frequency: int = 1) -> Dict[str, int]:
        """
        Extract n-grams from a list of tokens
        
        Args:
            tokens: List of word tokens
            n: N-gram size (2=bigram, 3=trigram, 4=4-gram)
            min_frequency: Minimum frequency to include phrase
            
        Returns:
            Dictionary of phrase -> frequency
        """
        if len(tokens) < n:
            return {}
            
        # Generate n-grams
        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngram = ' '.join(tokens[i:i + n])
            ngrams.append(ngram)
        
        # Count frequencies
        phrase_counts = Counter(ngrams)
        
        # Filter by minimum frequency
        return {phrase: count for phrase, count in phrase_counts.items() 
                if count >= min_frequency}
    
    def is_legal_phrase(self, phrase: str) -> bool:
        """
        Determine if a phrase is likely legal terminology worth indexing
        
        Args:
            phrase: The phrase to evaluate
            
        Returns:
            True if phrase appears to be legal terminology
        """
        # Convert to lowercase for checking
        phrase_lower = phrase.lower()
        
        # Legal keywords that indicate legal terminology
        legal_keywords = {
            'court', 'judge', 'attorney', 'counsel', 'appellant', 'respondent',
            'petitioner', 'defendant', 'plaintiff', 'trial', 'appeal', 'motion',
            'order', 'ruling', 'decision', 'judgment', 'decree', 'statute',
            'law', 'legal', 'constitutional', 'due process', 'evidence',
            'testimony', 'witness', 'hearing', 'proceeding', 'case', 'matter',
            'marriage', 'divorce', 'custody', 'support', 'maintenance',
            'property', 'assets', 'debt', 'alimony', 'child support',
            'parenting', 'visitation', 'modification', 'enforcement',
            'jurisdiction', 'venue', 'service', 'notice', 'pleading'
        }
        
        # Legal phrases that are commonly important
        legal_phrases = {
            'due process', 'equal protection', 'best interests', 'child support',
            'spousal support', 'community property', 'separate property',
            'parenting plan', 'residential time', 'decision making',
            'attorney fees', 'court costs', 'trial court', 'appeals court',
            'supreme court', 'family court', 'superior court',
            'motion to', 'order to', 'failure to', 'burden of proof',
            'standard of review', 'abuse of discretion', 'clearly erroneous',
            'substantial evidence', 'preponderance of evidence',
            'beyond reasonable doubt', 'material change', 'best interest'
        }
        
        # Check if phrase is in our known legal phrases
        if phrase_lower in legal_phrases:
            return True
            
        # Check if phrase contains legal keywords
        phrase_words = set(phrase_lower.split())
        if phrase_words.intersection(legal_keywords):
            return True
            
        # Check for common legal patterns
        legal_patterns = [
            'v.', 'vs.', 'versus', 'ex rel', 'in re', 'in the matter of',
            'rcw', 'usc', 'cfr', 'wac', 'pursuant to', 'according to',
            'based on', 'consistent with', 'in accordance with',
            'subject to', 'provided that', 'notwithstanding',
            'shall be', 'may be', 'must be', 'should be'
        ]
        
        for pattern in legal_patterns:
            if pattern in phrase_lower:
                return True
                
        # Reject common stop phrases that aren't legal
        stop_phrases = {
            'of the', 'in the', 'to the', 'for the', 'and the', 'at the',
            'on the', 'by the', 'with the', 'from the', 'this is',
            'that is', 'it is', 'there is', 'here is', 'what is',
            'how is', 'when is', 'where is', 'why is', 'who is'
        }
        
        if phrase_lower in stop_phrases:
            return False
            
        return False  # Default to not legal unless specifically identified
    
    def process_case_phrases(self, case_id: int, chunk_data: List[Dict], document_id: Optional[int] = None) -> Dict[str, any]:
        """
        Process all chunks in a case to extract and index phrases
        
        Args:
            case_id: Case identifier
            chunk_data: List of chunk dictionaries with 'chunk_id' and 'text'
            
        Returns:
            Dictionary with extraction statistics
        """
        if not chunk_data:
            return {'phrases_extracted': 0, 'phrases_inserted': 0}
            
        all_phrases = {}  # phrase -> frequency across all chunks
        phrase_examples = {}  # phrase -> example chunk_id
        
        # Process each chunk
        for chunk in chunk_data:
            chunk_id = chunk['chunk_id']
            text = chunk['text']
            
            if not text:
                continue
                
            # Tokenize the text
            tokens = self.word_processor.tokenize_text(text)
            
            if len(tokens) < 2:
                continue
                
            # Extract n-grams for different sizes
            for n in [2, 3, 4]:
                ngrams = self.extract_ngrams(tokens, n, min_frequency=1)
                
                for phrase, freq in ngrams.items():
                    # Only keep legal phrases
                    if self.is_legal_phrase(phrase):
                        if phrase not in all_phrases:
                            all_phrases[phrase] = 0
                            phrase_examples[phrase] = chunk_id
                        all_phrases[phrase] += freq
        
        # Filter phrases by frequency (at least 2 occurrences or very legal-sounding)
        high_value_phrases = {}
        for phrase, freq in all_phrases.items():
            if freq >= 2 or self._is_high_value_legal_phrase(phrase):
                high_value_phrases[phrase] = freq
        
        # Insert phrases into database
        inserted_count = 0
        if high_value_phrases:
            inserted_count = self._insert_case_phrases(
                case_id, high_value_phrases, phrase_examples, document_id
            )
        
        logger.info(f"Extracted {len(all_phrases)} phrases, inserted {inserted_count} for case {case_id}")
        
        return {
            'phrases_extracted': len(all_phrases),
            'phrases_inserted': inserted_count,
            'high_value_phrases': len(high_value_phrases)
        }
    
    def _is_high_value_legal_phrase(self, phrase: str) -> bool:
        """Check if phrase is high-value legal terminology worth keeping even with freq=1"""
        phrase_lower = phrase.lower()
        
        high_value_patterns = [
            'constitutional', 'due process', 'equal protection', 'first amendment',
            'fourteenth amendment', 'best interests', 'substantial evidence',
            'abuse of discretion', 'clearly erroneous', 'standard of review',
            'burden of proof', 'preponderance of evidence', 'beyond reasonable doubt',
            'material change', 'significant change', 'contempt of court',
            'res judicata', 'collateral estoppel', 'statute of limitations',
            'child support', 'spousal support', 'spousal maintenance',
            'community property', 'separate property', 'parenting plan',
            'residential time', 'decision making authority'
        ]
        
        return any(pattern in phrase_lower for pattern in high_value_patterns)
    
    def _insert_case_phrases(self, case_id: int, phrases: Dict[str, int], 
                           examples: Dict[str, str], document_id: Optional[int] = None) -> int:
        """Insert case phrases into database"""
        if not phrases:
            return 0
            
        phrase_records = []
        for phrase, frequency in phrases.items():
            # Determine n-gram size
            n = len(phrase.split())
            if n not in [2, 3, 4]:
                continue  # Skip invalid n-gram sizes
                
            phrase_records.append({
                'case_id': case_id,
                'phrase': phrase,
                'n': n,
                'frequency': frequency,
                'example_chunk': examples.get(phrase),
                'document_id': document_id if document_id is not None else None,
                'example_sentence': None  # Sentence ID not tracked during phrase extraction
            })
        
        if not phrase_records:
            return 0
            
        with self.db.connect() as conn:
            
            insert_query = text("""
                INSERT INTO case_phrases (case_id, document_id, phrase, n, frequency, example_chunk, example_sentence)
                VALUES (:case_id, :document_id, :phrase, :n, :frequency, :example_chunk, :example_sentence)
                ON CONFLICT (case_id, phrase) 
                DO UPDATE SET 
                    frequency = EXCLUDED.frequency,
                    example_chunk = EXCLUDED.example_chunk,
                    example_sentence = EXCLUDED.example_sentence
            """)
            
            conn.execute(insert_query, phrase_records)
            conn.commit()
        
        return len(phrase_records)
    
    def find_similar_phrases(self, query_phrase: str, limit: int = 20) -> List[Dict]:
        """
        Find phrases similar to the query phrase using trigram similarity
        
        Args:
            query_phrase: Phrase to find similarities for
            limit: Maximum number of results
            
        Returns:
            List of similar phrases with similarity scores
        """
        with self.db.connect() as conn:
            query = text("""
                SELECT 
                    phrase,
                    SUM(frequency) as total_frequency,
                    COUNT(DISTINCT case_id) as case_count,
                    similarity(phrase, :query_phrase) as similarity_score
                FROM case_phrases
                WHERE similarity(phrase, :query_phrase) > 0.3
                GROUP BY phrase
                ORDER BY similarity_score DESC, total_frequency DESC
                LIMIT :limit
            """)
            
            result = conn.execute(query, {
                'query_phrase': query_phrase,
                'limit': limit
            })
            
            return [
                {
                    'phrase': row.phrase,
                    'total_frequency': row.total_frequency,
                    'case_count': row.case_count,
                    'similarity_score': float(row.similarity_score)
                }
                for row in result
            ]
    
    def get_top_phrases(self, court: str = None, limit: int = 50) -> List[Dict]:
        """
        Get top phrases by frequency, optionally filtered by court
        
        Args:
            court: Optional court filter
            limit: Maximum number of results
            
        Returns:
            List of top phrases with statistics
        """
        with self.db.connect() as conn:
            if court:
                query = text("""
                    SELECT 
                        cp.phrase,
                        SUM(cp.frequency) as total_frequency,
                        COUNT(DISTINCT cp.case_id) as case_count,
                        cp.n
                    FROM case_phrases cp
                    JOIN cases c ON cp.case_id = c.case_id
                    WHERE c.court ILIKE :court
                    GROUP BY cp.phrase, cp.n
                    ORDER BY total_frequency DESC
                    LIMIT :limit
                """)
                params = {'court': f'%{court}%', 'limit': limit}
            else:
                query = text("""
                    SELECT 
                        phrase,
                        SUM(frequency) as total_frequency,
                        COUNT(DISTINCT case_id) as case_count,
                        n
                    FROM case_phrases
                    GROUP BY phrase, n
                    ORDER BY total_frequency DESC
                    LIMIT :limit
                """)
                params = {'limit': limit}
            
            result = conn.execute(query, params)
            
            return [
                {
                    'phrase': row.phrase,
                    'total_frequency': row.total_frequency,
                    'case_count': row.case_count,
                    'n_gram_size': row.n
                }
                for row in result
            ]
