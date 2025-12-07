"""
Phrase Extractor
N-gram phrase extraction and indexing for legal documents.
Enables phrase-based search and legal terminology discovery.
"""

import logging
from typing import List, Dict, Set, Optional
from collections import Counter
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .word_processor import WordProcessor

logger = logging.getLogger(__name__)


class PhraseExtractor:
    """Extract and index n-gram phrases from legal text."""
    
    # Legal keywords that indicate legal terminology
    LEGAL_KEYWORDS = {
        'court', 'judge', 'attorney', 'counsel', 'appellant', 'respondent',
        'petitioner', 'defendant', 'plaintiff', 'trial', 'appeal', 'motion',
        'order', 'ruling', 'decision', 'judgment', 'decree', 'statute',
        'law', 'legal', 'constitutional', 'evidence', 'testimony', 'witness',
        'hearing', 'proceeding', 'case', 'matter', 'marriage', 'divorce',
        'custody', 'support', 'maintenance', 'property', 'assets', 'debt',
        'alimony', 'parenting', 'visitation', 'modification', 'enforcement',
        'jurisdiction', 'venue', 'service', 'notice', 'pleading', 'rcw',
        'statute', 'regulation', 'code', 'criminal', 'civil', 'felony',
        'misdemeanor', 'conviction', 'sentence', 'probation', 'parole'
    }
    
    # Known high-value legal phrases
    LEGAL_PHRASES = {
        'due process', 'equal protection', 'best interests', 'child support',
        'spousal support', 'community property', 'separate property',
        'parenting plan', 'residential time', 'decision making',
        'attorney fees', 'court costs', 'trial court', 'appeals court',
        'supreme court', 'family court', 'superior court',
        'motion to', 'order to', 'failure to', 'burden of proof',
        'standard of review', 'abuse of discretion', 'clearly erroneous',
        'substantial evidence', 'preponderance of evidence',
        'beyond reasonable doubt', 'material change', 'best interest',
        'de novo', 'res judicata', 'collateral estoppel', 'summary judgment',
        'preliminary injunction', 'temporary restraining', 'directed verdict',
        'reasonable doubt', 'probable cause', 'search and seizure',
        'miranda rights', 'fifth amendment', 'fourth amendment',
        'sixth amendment', 'first amendment', 'fourteenth amendment'
    }
    
    # High-value patterns that should be kept even with frequency=1
    HIGH_VALUE_PATTERNS = [
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
    
    # Stop phrases to always filter out
    STOP_PHRASES = {
        'of the', 'in the', 'to the', 'for the', 'and the', 'at the',
        'on the', 'by the', 'with the', 'from the', 'this is',
        'that is', 'it is', 'there is', 'here is', 'what is',
        'how is', 'when is', 'where is', 'why is', 'who is',
        'was the', 'were the', 'has the', 'had the', 'have the',
        'be the', 'been the', 'being the', 'as the', 'but the'
    }
    
    def __init__(self, db_engine: Engine):
        self.db = db_engine
        self.word_processor = WordProcessor(db_engine)
    
    def extract_ngrams(
        self, 
        tokens: List[str], 
        n: int, 
        min_frequency: int = 1
    ) -> Dict[str, int]:
        """
        Extract n-grams from a list of tokens.
        
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
        return {
            phrase: count 
            for phrase, count in phrase_counts.items() 
            if count >= min_frequency
        }
    
    def is_legal_phrase(self, phrase: str) -> bool:
        """
        Determine if a phrase is likely legal terminology worth indexing.
        
        Args:
            phrase: The phrase to evaluate
            
        Returns:
            True if phrase appears to be legal terminology
        """
        phrase_lower = phrase.lower()
        
        # Check if phrase is a known stop phrase
        if phrase_lower in self.STOP_PHRASES:
            return False
        
        # Check if phrase is in our known legal phrases
        if phrase_lower in self.LEGAL_PHRASES:
            return True
        
        # Check if phrase contains legal keywords
        phrase_words = set(phrase_lower.split())
        if phrase_words.intersection(self.LEGAL_KEYWORDS):
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
        
        return False
    
    def is_high_value_phrase(self, phrase: str) -> bool:
        """Check if phrase is high-value legal terminology worth keeping even with freq=1."""
        phrase_lower = phrase.lower()
        return any(pattern in phrase_lower for pattern in self.HIGH_VALUE_PATTERNS)
    
    def process_case_phrases(
        self,
        conn,
        case_id: int,
        chunks: List[Dict],
        document_id: Optional[int] = None,
        strict_legal_filter: bool = True,
        min_frequency: int = 2
    ) -> Dict[str, int]:
        """
        Process all chunks in a case to extract and index phrases.
        
        Args:
            conn: Database connection (within transaction)
            case_id: Case identifier
            chunks: List of chunk dictionaries with 'chunk_id' and 'text'
            document_id: Optional document identifier
            strict_legal_filter: If True, only keep legal phrases. If False, keep all with freq >= min_frequency
            min_frequency: Minimum frequency to include phrase (only used if strict_legal_filter=False)
            
        Returns:
            Dictionary with extraction statistics
        """
        if not chunks:
            return {'phrases_extracted': 0, 'phrases_inserted': 0}
        
        all_phrases: Dict[str, int] = {}  # phrase -> frequency
        phrase_examples: Dict[str, int] = {}  # phrase -> example chunk_id
        
        # Process each chunk
        for chunk in chunks:
            chunk_id = chunk['chunk_id']
            text = chunk.get('text', '')
            
            if not text:
                continue
            
            # Tokenize the text (remove stop words for phrase extraction)
            tokens = self.word_processor.tokenize_text(text, remove_stop_words=False)
            
            if len(tokens) < 2:
                continue
            
            # Extract n-grams for different sizes (2, 3, 4)
            for n in [2, 3, 4]:
                ngrams = self.extract_ngrams(tokens, n, min_frequency=1)
                
                for phrase, freq in ngrams.items():
                    if strict_legal_filter:
                        # Only keep legal phrases
                        if not self.is_legal_phrase(phrase):
                            continue
                    
                    if phrase not in all_phrases:
                        all_phrases[phrase] = 0
                        phrase_examples[phrase] = chunk_id
                    all_phrases[phrase] += freq
        
        # Filter phrases based on mode
        if strict_legal_filter:
            # Keep all legal phrases OR high-value phrases with freq >= 1
            filtered_phrases = {
                phrase: freq for phrase, freq in all_phrases.items()
                if freq >= 2 or self.is_high_value_phrase(phrase)
            }
        else:
            # Keep all phrases with frequency >= min_frequency
            filtered_phrases = {
                phrase: freq for phrase, freq in all_phrases.items()
                if freq >= min_frequency
            }
        
        # Insert phrases into database
        inserted_count = 0
        if filtered_phrases:
            inserted_count = self._insert_case_phrases(
                conn, case_id, filtered_phrases, phrase_examples, document_id
            )
        
        logger.debug(f"Extracted {len(all_phrases)} phrases, inserted {inserted_count} for case {case_id}")
        
        return {
            'phrases_extracted': len(all_phrases),
            'phrases_filtered': len(filtered_phrases),
            'phrases_inserted': inserted_count
        }
    
    def _insert_case_phrases(
        self,
        conn,
        case_id: int,
        phrases: Dict[str, int],
        examples: Dict[str, int],
        document_id: Optional[int] = None
    ) -> int:
        """Insert case phrases into database."""
        if not phrases:
            return 0
        
        insert_query = text("""
            INSERT INTO case_phrases (case_id, document_id, phrase, n, frequency, example_chunk, created_at)
            VALUES (:case_id, :document_id, :phrase, :n, :frequency, :example_chunk, NOW())
            ON CONFLICT (case_id, phrase) DO UPDATE SET 
                frequency = EXCLUDED.frequency,
                example_chunk = EXCLUDED.example_chunk
        """)
        
        inserted = 0
        for phrase, frequency in phrases.items():
            # Determine n-gram size
            n = len(phrase.split())
            if n not in [2, 3, 4]:
                continue  # Skip invalid n-gram sizes
            
            try:
                conn.execute(insert_query, {
                    'case_id': case_id,
                    'document_id': document_id,
                    'phrase': phrase,
                    'n': n,
                    'frequency': frequency,
                    'example_chunk': examples.get(phrase)
                })
                inserted += 1
            except Exception as e:
                logger.warning(f"Failed to insert phrase '{phrase}': {e}")
        
        return inserted
    
    def search_phrases(self, query: str, case_id: Optional[int] = None, limit: int = 50) -> List[Dict]:
        """
        Search for phrases matching a query.
        
        Args:
            query: Search query (partial match)
            case_id: Optional case ID to limit search
            limit: Maximum results to return
            
        Returns:
            List of matching phrase records
        """
        with self.db.connect() as conn:
            if case_id:
                sql = text("""
                    SELECT phrase, frequency, n, case_id, example_chunk
                    FROM case_phrases
                    WHERE phrase ILIKE :query AND case_id = :case_id
                    ORDER BY frequency DESC
                    LIMIT :limit
                """)
                result = conn.execute(sql, {
                    'query': f'%{query}%',
                    'case_id': case_id,
                    'limit': limit
                })
            else:
                sql = text("""
                    SELECT phrase, frequency, n, case_id, example_chunk
                    FROM case_phrases
                    WHERE phrase ILIKE :query
                    ORDER BY frequency DESC
                    LIMIT :limit
                """)
                result = conn.execute(sql, {'query': f'%{query}%', 'limit': limit})
            
            return [
                {
                    'phrase': row.phrase,
                    'frequency': row.frequency,
                    'n': row.n,
                    'case_id': row.case_id,
                    'example_chunk': row.example_chunk
                }
                for row in result
            ]
