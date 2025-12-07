"""
Sentence Processor
Splits chunks into sentences and creates sentence-level database records.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class SentenceProcessor:
    """Service for processing text chunks into sentences."""
    
    # Patterns to protect from sentence splitting
    PROTECTED_PATTERNS = [
        r'\d+\s+P\.\s*\d+d?\s+\d+',      # Pacific Reporter citations
        r'\d+\s+Wn\.\s*\d*\s+\d+',       # Washington Reports
        r'\d+\s+U\.S\.\s+\d+',           # U.S. Reports
        r'RCW\s+\d+\.\d+\.\d+',          # RCW statutes
        r'WAC\s+\d+\-\d+\-\d+',          # WAC regulations
        r'\d+\s+F\.\s*\d*d?\s+\d+',      # Federal Reporter
        r'\d+\s+S\.\s*Ct\.\s+\d+',       # Supreme Court Reporter
    ]
    
    def __init__(self, db_engine: Engine):
        self.db = db_engine
    
    def split_into_sentences(self, text: str) -> List[Dict[str, Any]]:
        """
        Split text into individual sentences.
        
        Args:
            text: Text content to split
            
        Returns:
            List of sentence dictionaries with text and metadata
        """
        if not text or len(text.strip()) < 10:
            return []
        
        # Protect citations from splitting
        protected_text = text
        protections = {}
        
        for i, pattern in enumerate(self.PROTECTED_PATTERNS):
            matches = list(re.finditer(pattern, protected_text, re.IGNORECASE))
            for j, match in enumerate(matches):
                placeholder = f"__CITATION_{i}_{j}__"
                protections[placeholder] = match.group()
                protected_text = protected_text.replace(match.group(), placeholder, 1)
        
        # Split on sentence boundaries
        # Look for periods, question marks, exclamation points followed by space and capital
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        raw_sentences = re.split(sentence_pattern, protected_text)
        
        sentences = []
        for i, sent in enumerate(raw_sentences):
            sent = sent.strip()
            if not sent:
                continue
            
            # Restore protected citations
            for placeholder, original in protections.items():
                sent = sent.replace(placeholder, original)
            
            # Skip very short sentences (likely fragments)
            if len(sent) < 15:
                continue
            
            word_count = len(sent.split())
            
            sentences.append({
                'text': sent,
                'sentence_order': i + 1,
                'word_count': word_count,
                'char_count': len(sent)
            })
        
        return sentences
    
    def process_chunk_sentences(
        self,
        conn,
        case_id: int,
        chunk_id: int,
        chunk_text: str,
        document_id: Optional[int] = None,
        global_sentence_counter: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Process chunk into sentences and create database records.
        
        Args:
            conn: Database connection (within transaction)
            case_id: Case ID
            chunk_id: Chunk ID
            chunk_text: Text content
            document_id: Optional document ID
            global_sentence_counter: Starting counter for global sentence order
            
        Returns:
            List of created sentence records with IDs
        """
        # Split into sentences
        sentences = self.split_into_sentences(chunk_text)
        
        if not sentences:
            return []
        
        sentence_records = []
        
        for sentence_data in sentences:
            global_sentence_counter += 1
            
            try:
                insert_query = text("""
                    INSERT INTO case_sentences (
                        case_id, chunk_id, document_id, sentence_order,
                        global_sentence_order, text, word_count,
                        created_at, updated_at
                    ) VALUES (
                        :case_id, :chunk_id, :document_id, :sentence_order,
                        :global_sentence_order, :text, :word_count,
                        NOW(), NOW()
                    )
                    RETURNING sentence_id
                """)
                
                result = conn.execute(insert_query, {
                    'case_id': case_id,
                    'chunk_id': chunk_id,
                    'document_id': document_id,
                    'sentence_order': sentence_data['sentence_order'],
                    'global_sentence_order': global_sentence_counter,
                    'text': sentence_data['text'],
                    'word_count': sentence_data['word_count']
                })
                
                sentence_id = result.fetchone().sentence_id
                
                sentence_records.append({
                    'sentence_id': sentence_id,
                    'case_id': case_id,
                    'chunk_id': chunk_id,
                    'document_id': document_id,
                    'sentence_order': sentence_data['sentence_order'],
                    'global_sentence_order': global_sentence_counter,
                    'text': sentence_data['text'],
                    'word_count': sentence_data['word_count']
                })
                
            except Exception as e:
                logger.warning(f"Failed to insert sentence: {e}")
                continue
        
        return sentence_records
    
    def update_chunk_sentence_count(self, conn, chunk_id: int, sentence_count: int) -> None:
        """Update the sentence count for a chunk."""
        query = text("UPDATE case_chunks SET sentence_count = :count WHERE chunk_id = :chunk_id")
        conn.execute(query, {'count': sentence_count, 'chunk_id': chunk_id})
    
    def get_case_sentences(self, case_id: int) -> List[Dict[str, Any]]:
        """Get all sentences for a case."""
        with self.db.connect() as conn:
            query = text("""
                SELECT sentence_id, chunk_id, text, word_count, sentence_order
                FROM case_sentences
                WHERE case_id = :case_id
                ORDER BY chunk_id, sentence_order
            """)
            result = conn.execute(query, {'case_id': case_id})
            
            return [
                {
                    'sentence_id': row.sentence_id,
                    'chunk_id': row.chunk_id,
                    'text': row.text,
                    'word_count': row.word_count,
                    'sentence_order': row.sentence_order
                }
                for row in result
            ]
