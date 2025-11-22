"""
Legal Brief Ingestion Service
Similar architecture to case_ingestor.py but adapted for briefs
Implements multi-strategy case linking and brief chaining
"""

import os
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..pdf_parser import extract_text_from_pdf, clean_pdf_text, get_pdf_metadata
from ..chunker import LegalTextChunker
from .word_processor import WordProcessor
from .phrase_extractor import PhraseExtractor
from .sentence_processor import SentenceProcessor
from .embedding_service import generate_embedding

logger = logging.getLogger(__name__)

class BriefIngestor:
    """
    Ingests legal briefs into the database with:
    - Multi-strategy case linking (folder + filename)
    - Brief chaining (conversation tracking)
    - Hierarchical argument extraction
    - Table of Authorities prioritization
    """
    
    def __init__(self, db_engine: Engine):
        self.db = db_engine
        self.text_chunker = LegalTextChunker()
        self.word_processor = WordProcessor(db_engine)
        self.phrase_extractor = PhraseExtractor(db_engine)
        self.sentence_processor = SentenceProcessor(db_engine)
    
    def ingest_pdf_brief(self, file_path: str, year: Optional[int] = None) -> Dict[str, Any]:
        """
        Main orchestrator for brief PDF ingestion
        
        Args:
            file_path: Path to brief PDF file
            year: Filing year (optional, extracted from path if not provided)
            
        Returns:
            Dictionary with brief_id, stats, and linking info
        """
        logger.info(f"🚀 Starting brief ingestion for: {file_path}")
        
        try:
            # Step 1: Parse filename and extract metadata
            logger.info("📝 Parsing filename metadata...")
            metadata = self._parse_brief_filename(file_path)
            if year:
                metadata['year'] = year
            logger.info(f"✅ Extracted metadata: {metadata}")
            
            # Step 2: Parse PDF content
            logger.info("📄 Parsing PDF content...")
            with open(file_path, 'rb') as f:
                pdf_content = f.read()
            pages_text = extract_text_from_pdf(pdf_content)
            full_text = "\n\n".join(pages_text)
            full_text = clean_pdf_text(full_text)
            logger.info(f"✅ Parsed {len(pages_text)} pages, {len(full_text)} characters")
            
            # Step 3: Insert brief record with multi-strategy case linking
            logger.info("💾 Creating brief record with case linking...")
            brief_id, case_id = self._insert_brief(metadata, full_text, len(pages_text))
            
            if case_id:
                logger.info(f"✅ Linked to case_id: {case_id}")
            else:
                logger.warning(f"⚠️ Could not link to case - will remain orphaned")
            
            # Step 4: Detect brief chaining (responds_to_brief_id)
            logger.info("🔗 Detecting brief chaining...")
            self._detect_brief_chaining(brief_id, metadata['case_file_id'], metadata['brief_type'])
            
            # Step 5: Create chunks for RAG
            logger.info("📄 Creating text chunks...")
            chunks = self.text_chunker.chunk_pages(pages_text)
            logger.info(f"✅ Created {len(chunks)} text chunks")
            
            # Step 6: Insert chunks with section detection
            logger.info("📦 Inserting chunks with embeddings...")
            chunk_ids = self._insert_chunks(brief_id, case_id, chunks)
            logger.info(f"✅ Inserted {len(chunk_ids)} chunks")
            
            # Step 7: Process sentences
            # TEMPORARILY DISABLED - too slow with Ollama (generates embeddings per sentence)
            # logger.info("✂️ Processing sentences...")
            # sentence_stats = self._process_sentences(brief_id, chunks, chunk_ids)
            # logger.info(f"✅ Processed {sentence_stats['total_sentences']} sentences")
            sentence_stats = {'total_sentences': 0}
            
            # Step 8: Process words for precise search
            # TEMPORARILY DISABLED - performance optimization
            # logger.info("📝 Processing words...")
            # word_stats = self._process_words(brief_id, chunks, chunk_ids)
            # logger.info(f"✅ Processed {word_stats['total_words']} words")
            word_stats = {'total_words': 0}
            
            # Step 9: Extract phrases
            logger.info("🔤 Extracting legal phrases...")
            phrase_stats = self._extract_phrases(brief_id, chunks)
            logger.info(f"✅ Extracted {phrase_stats['phrases_inserted']} phrases")
            
            # Step 10: Generate full brief embedding
            logger.info("🌟 Generating brief embedding...")
            use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
            brief_embedding = generate_embedding(full_text[:8000], prefer_ollama=use_ollama)  # Limit to first 8000 chars
            self._update_brief_embedding(brief_id, brief_embedding)
            logger.info("✅ Generated brief embedding")
            
            # Step 11: Extract Table of Authorities (TOA)
            logger.info("📚 Extracting Table of Authorities...")
            toa_stats = self._extract_toa(brief_id, full_text)
            logger.info(f"✅ Extracted {toa_stats['citations_found']} citations from TOA")
            
            # Step 12: Update processing status
            self._update_processing_status(brief_id, 'completed')
            
            result = {
                'brief_id': brief_id,
                'case_id': case_id,
                'case_linked': case_id is not None,
                'chunks_created': len(chunk_ids),
                'sentences_processed': sentence_stats['total_sentences'],
                'words_indexed': word_stats['total_words'],
                'phrases_extracted': phrase_stats['phrases_inserted'],
                'toa_citations': toa_stats['citations_found'],
                'embedding_dimension': len(brief_embedding) if brief_embedding else 0,
                'status': 'success'
            }
            
            logger.info(f"🎉 Brief ingestion completed for brief_id {brief_id}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Brief ingestion failed: {str(e)}")
            raise
    
    def _parse_brief_filename(self, file_path: str) -> Dict[str, str]:
        """
        Parse brief filename to extract metadata
        
        Returns metadata dict with:
        - case_file_id: From folder name (e.g., "83895-4")
        - brief_type: Opening/Response/Reply
        - filing_party: Appellant/Respondent
        - source_file: Filename only
        - source_file_path: Full path
        - year: Extracted from path
        """
        path = Path(file_path)
        filename = path.stem  # Without extension
        
        # Extract folder case_file_id (e.g., "83895-4" from "downloaded-briefs/2024-briefs/83895-4/")
        parts = path.parts
        case_file_id = None
        year = None
        
        for i, part in enumerate(parts):
            # Look for year pattern: "2024-briefs"
            if re.match(r'\d{4}-briefs', part):
                year = int(part.split('-')[0])
                # Next part should be case number
                if i + 1 < len(parts):
                    case_file_id = parts[i + 1]
                break
        
        if not case_file_id:
            raise ValueError(f"Could not extract case_file_id from path: {file_path}")
        
        # Parse filename for brief type and party
        filename_lower = filename.lower()
        
        # Determine filing party first (needed for default brief type)
        if 'appellant' in filename_lower or 'petitioner' in filename_lower:
            filing_party = 'Appellant'
        elif 'respondent' in filename_lower:
            filing_party = 'Respondent'
        else:
            filing_party = 'Unknown'
        
        # Determine brief type with improved detection
        if 'reply' in filename_lower:
            # Check for supplemental or amended
            if 'supplemental' in filename_lower:
                brief_type = 'Supplemental Reply'
            elif 'amended' in filename_lower:
                brief_type = 'Amended Reply'
            else:
                brief_type = 'Reply'
        elif 'response' in filename_lower or 'answer' in filename_lower:
            if 'supplemental' in filename_lower:
                brief_type = 'Supplemental Response'
            elif 'amended' in filename_lower:
                brief_type = 'Amended Response'
            else:
                brief_type = 'Response'
        elif 'opening' in filename_lower or 'initial' in filename_lower:
            brief_type = 'Opening'
        elif 'statement_of_additional_grounds' in filename_lower or 'additional_grounds' in filename_lower:
            brief_type = 'Statement of Additional Grounds'
        elif 'supplemental' in filename_lower:
            brief_type = 'Supplemental Brief'
        elif 'amended' in filename_lower:
            brief_type = 'Amended Brief'
        else:
            # Default based on party if no type keyword found
            # Appellant's first brief is typically "Opening", Respondent's is "Response"
            if filing_party == 'Appellant':
                brief_type = 'Opening'
            elif filing_party == 'Respondent':
                brief_type = 'Response'
            else:
                brief_type = 'Unknown'
        
        return {
            'case_file_id': case_file_id,
            'brief_type': brief_type,
            'filing_party': filing_party,
            'source_file': path.name,
            'source_file_path': str(path.absolute()),
            'year': year
        }
    
    def _insert_brief(self, metadata: Dict[str, str], full_text: str, page_count: int) -> Tuple[int, Optional[int]]:
        """
        Insert brief record with case linking via folder case_file_id
        
        Returns:
            (brief_id, case_id) - case_id is None if linking failed
        """
        with self.db.connect() as conn:
            trans = conn.begin()
            
            try:
                folder_case_id = metadata['case_file_id']
                
                # Link to case via folder case_file_id and get outcome data
                case_id, outcome_data = self._link_to_case(conn, folder_case_id)
                
                # Extract summary (first 500 chars)
                summary = full_text[:500] if full_text else None
                
                # Insert brief
                insert_query = text("""
                    INSERT INTO briefs (
                        case_id, case_file_id,
                        brief_type, filing_party, 
                        winner_legal_role, winner_personal_role, appeal_outcome,
                        page_count, word_count,
                        summary, full_text, source_file, source_file_path, year,
                        processing_status, extraction_timestamp
                    ) VALUES (
                        :case_id, :case_file_id,
                        :brief_type, :filing_party,
                        :winner_legal_role, :winner_personal_role, :appeal_outcome,
                        :page_count, :word_count,
                        :summary, :full_text, :source_file, :source_file_path, :year,
                        'processing', NOW()
                    )
                    RETURNING brief_id
                """)
                
                result = conn.execute(insert_query, {
                    'case_id': case_id,
                    'case_file_id': folder_case_id,
                    'brief_type': metadata['brief_type'],
                    'filing_party': metadata['filing_party'],
                    'winner_legal_role': outcome_data.get('winner_legal_role'),
                    'winner_personal_role': outcome_data.get('winner_personal_role'),
                    'appeal_outcome': outcome_data.get('appeal_outcome'),
                    'page_count': page_count,
                    'word_count': len(full_text.split()) if full_text else 0,
                    'summary': summary,
                    'full_text': full_text,
                    'source_file': metadata['source_file'],
                    'source_file_path': metadata['source_file_path'],
                    'year': metadata.get('year')
                })
                
                brief_id = result.fetchone()[0]
                trans.commit()
                
                return brief_id, case_id
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to insert brief: {str(e)}")
                raise
    
    def _link_to_case(self, conn, folder_case_id: str) -> Tuple[Optional[int], Dict[str, Optional[str]]]:
        """
        Link brief to case via folder case_file_id (exact match) and fetch outcome data
        
        Returns:
            (case_id, outcome_data) - case_id is None if no match
            outcome_data dict contains: winner_legal_role, winner_personal_role, appeal_outcome
        """
        query = text("""
            SELECT case_id, winner_legal_role, winner_personal_role, appeal_outcome
            FROM cases
            WHERE case_file_id = :folder_case_id
            LIMIT 1
        """)
        
        result = conn.execute(query, {'folder_case_id': folder_case_id})
        row = result.fetchone()
        
        if row:
            logger.info(f"✅ Linked via folder case_file_id: {folder_case_id}")
            outcome_data = {
                'winner_legal_role': row[1],
                'winner_personal_role': row[2],
                'appeal_outcome': row[3]
            }
            return row[0], outcome_data
        
        logger.warning(f"⚠️ No case match for folder '{folder_case_id}'")
        return None, {}
    
    def _detect_brief_chaining(self, brief_id: int, case_file_id: str, brief_type: str):
        """
        Detect if this brief responds to a previous brief (conversation tracking)
        
        Logic:
        - Response brief responds to Opening brief
        - Reply brief responds to Response brief
        """
        with self.db.connect() as conn:
            trans = conn.begin()
            
            try:
                responds_to = None
                sequence = 1
                
                if brief_type == 'Response':
                    # Find Opening brief for same case
                    query = text("""
                        SELECT brief_id FROM briefs
                        WHERE normalize_case_file_id(case_file_id) = normalize_case_file_id(:case_file_id)
                        AND brief_type = 'Opening'
                        ORDER BY created_at DESC
                        LIMIT 1
                    """)
                    result = conn.execute(query, {'case_file_id': case_file_id})
                    row = result.fetchone()
                    if row:
                        responds_to = row[0]
                        sequence = 2
                
                elif brief_type == 'Reply':
                    # Find Response brief for same case
                    query = text("""
                        SELECT brief_id FROM briefs
                        WHERE normalize_case_file_id(case_file_id) = normalize_case_file_id(:case_file_id)
                        AND brief_type = 'Response'
                        ORDER BY created_at DESC
                        LIMIT 1
                    """)
                    result = conn.execute(query, {'case_file_id': case_file_id})
                    row = result.fetchone()
                    if row:
                        responds_to = row[0]
                        sequence = 3
                
                # Update brief with chaining info
                update_query = text("""
                    UPDATE briefs
                    SET responds_to_brief_id = :responds_to, brief_sequence = :sequence
                    WHERE brief_id = :brief_id
                """)
                
                conn.execute(update_query, {
                    'brief_id': brief_id,
                    'responds_to': responds_to,
                    'sequence': sequence
                })
                
                trans.commit()
                
                if responds_to:
                    logger.info(f"✅ Brief chain detected: brief {brief_id} responds to brief {responds_to}")
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to detect brief chaining: {str(e)}")
    
    def _insert_chunks(self, brief_id: int, case_id: Optional[int], chunks: List) -> List[str]:
        """Insert chunks with section detection and embeddings"""
        chunk_ids = []
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        
        with self.db.connect() as conn:
            trans = conn.begin()
            
            try:
                for i, chunk in enumerate(chunks):
                    section = self._determine_section(chunk.text)
                    
                    # Generate embedding for chunk
                    embedding = generate_embedding(chunk.text, prefer_ollama=use_ollama)
                    embedding_str = f"[{','.join(map(str, embedding))}]" if embedding else None
                    
                    insert_query = text("""
                        INSERT INTO brief_chunks (
                            brief_id, case_id, chunk_order, text, section,
                            word_count, char_count, embedding
                        ) VALUES (
                            :brief_id, :case_id, :chunk_order, :text, :section,
                            :word_count, :char_count, CAST(:embedding AS vector)
                        )
                        RETURNING chunk_id
                    """)
                    
                    result = conn.execute(insert_query, {
                        'brief_id': brief_id,
                        'case_id': case_id,
                        'chunk_order': i,
                        'text': chunk.text,
                        'section': section,
                        'word_count': len(chunk.text.split()),
                        'char_count': len(chunk.text),
                        'embedding': embedding_str
                    })
                    
                    chunk_id = result.fetchone()[0]
                    chunk_ids.append(chunk_id)
                
                trans.commit()
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to insert chunks: {str(e)}")
                raise
        
        return chunk_ids
    
    def _determine_section(self, text: str) -> str:
        """Determine brief section from chunk text"""
        text_lower = text.lower()
        
        # Brief-specific sections
        if any(word in text_lower for word in ['table of authorities', 'table of cases', 'authorities cited']):
            return 'TABLE_OF_AUTHORITIES'
        elif any(word in text_lower for word in ['statement of the case', 'procedural history']):
            return 'STATEMENT_OF_CASE'
        elif any(word in text_lower for word in ['statement of facts', 'facts', 'background']):
            return 'STATEMENT_OF_FACTS'
        elif any(word in text_lower for word in ['issues presented', 'questions presented', 'issues']):
            return 'ISSUES'
        elif any(word in text_lower for word in ['argument', 'discussion', 'analysis']):
            return 'ARGUMENT'
        elif any(word in text_lower for word in ['conclusion', 'prayer for relief', 'relief requested']):
            return 'CONCLUSION'
        else:
            return 'GENERAL'
    
    def _process_sentences(self, brief_id: int, chunks: List, chunk_ids: List[str]) -> Dict[str, int]:
        """Process chunks into sentences with embeddings"""
        total_sentences = 0
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        
        with self.db.connect() as conn:
            trans = conn.begin()
            
            try:
                for chunk, chunk_id in zip(chunks, chunk_ids):
                    # Split into sentences (simple approach)
                    sentences = re.split(r'[.!?]+\s+', chunk.text)
                    
                    for pos, sentence in enumerate(sentences):
                        if len(sentence.strip()) < 10:  # Skip very short sentences
                            continue
                        
                        # Generate embedding
                        embedding = generate_embedding(sentence, prefer_ollama=use_ollama)
                        embedding_str = f"[{','.join(map(str, embedding))}]" if embedding else None
                        
                        insert_query = text("""
                            INSERT INTO brief_sentences (
                                brief_id, chunk_id, text, position, word_count, embedding
                            ) VALUES (
                                :brief_id, :chunk_id, :text, :position, :word_count, CAST(:embedding AS vector)
                            )
                        """)
                        
                        conn.execute(insert_query, {
                            'brief_id': brief_id,
                            'chunk_id': chunk_id,
                            'text': sentence.strip(),
                            'position': pos,
                            'word_count': len(sentence.split()),
                            'embedding': embedding_str
                        })
                        
                        total_sentences += 1
                
                trans.commit()
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to process sentences: {str(e)}")
                raise
        
        return {'total_sentences': total_sentences}
    
    def _process_words(self, brief_id: int, chunks: List, chunk_ids: List[str]) -> Dict[str, int]:
        """Process words for word-level indexing (reuses word_dictionary)"""
        total_words = 0
        
        with self.db.connect() as conn:
            trans = conn.begin()
            
            try:
                for chunk, chunk_id in zip(chunks, chunk_ids):
                    words = re.findall(r'\b\w+\b', chunk.text.lower())
                    
                    for pos, word in enumerate(words):
                        if len(word) < 3:  # Skip very short words
                            continue
                        
                        # Get or create word_id
                        word_query = text("""
                            INSERT INTO word_dictionary (word)
                            VALUES (:word)
                            ON CONFLICT (word) DO UPDATE SET word = EXCLUDED.word
                            RETURNING word_id
                        """)
                        
                        result = conn.execute(word_query, {'word': word})
                        word_id = result.fetchone()[0]
                        
                        # Insert word occurrence
                        occur_query = text("""
                            INSERT INTO brief_word_occurrence (brief_id, chunk_id, word_id, position)
                            VALUES (:brief_id, :chunk_id, :word_id, :position)
                            ON CONFLICT (chunk_id, word_id, position) DO NOTHING
                        """)
                        
                        conn.execute(occur_query, {
                            'brief_id': brief_id,
                            'chunk_id': chunk_id,
                            'word_id': word_id,
                            'position': pos
                        })
                        
                        total_words += 1
                
                trans.commit()
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to process words: {str(e)}")
                raise
        
        return {'total_words': total_words}
    
    def _extract_phrases(self, brief_id: int, chunks: List) -> Dict[str, int]:
        """Extract legal phrases (2-5 grams)"""
        phrases_inserted = 0
        phrase_counts = {}
        
        # Extract phrases from all chunks
        for chunk in chunks:
            words = re.findall(r'\b\w+\b', chunk.text.lower())
            
            # Extract 2-5 grams
            for n in range(2, 6):
                for i in range(len(words) - n + 1):
                    phrase = ' '.join(words[i:i+n])
                    phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
        
        # Insert phrases with frequency > 1
        with self.db.connect() as conn:
            trans = conn.begin()
            
            try:
                for phrase, freq in phrase_counts.items():
                    if freq < 2:  # Skip single occurrences
                        continue
                    
                    insert_query = text("""
                        INSERT INTO brief_phrases (brief_id, phrase, frequency, phrase_length)
                        VALUES (:brief_id, :phrase, :frequency, :phrase_length)
                    """)
                    
                    conn.execute(insert_query, {
                        'brief_id': brief_id,
                        'phrase': phrase,
                        'frequency': freq,
                        'phrase_length': len(phrase.split())
                    })
                    
                    phrases_inserted += 1
                
                trans.commit()
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to extract phrases: {str(e)}")
                raise
        
        return {'phrases_inserted': phrases_inserted}
    
    def _update_brief_embedding(self, brief_id: int, embedding: List[float]):
        """Update brief with full text embedding"""
        with self.db.connect() as conn:
            embedding_str = f"[{','.join(map(str, embedding))}]" if embedding else None
            
            update_query = text("""
                UPDATE briefs
                SET full_embedding = CAST(:embedding AS vector)
                WHERE brief_id = :brief_id
            """)
            
            conn.execute(update_query, {
                'brief_id': brief_id,
                'embedding': embedding_str
            })
            conn.commit()
    
    def _extract_toa(self, brief_id: int, full_text: str) -> Dict[str, int]:
        """
        Extract Table of Authorities (TOA) citations
        
        Looks for TOA section and extracts citations with page references
        """
        citations_found = 0
        
        # Find TOA section
        toa_pattern = r'TABLE OF (AUTHORITIES|CASES|CONTENTS).*?(?=\n[A-Z]{2,}|\Z)'
        match = re.search(toa_pattern, full_text, re.IGNORECASE | re.DOTALL)
        
        if not match:
            logger.info("No Table of Authorities found")
            return {'citations_found': 0}
        
        toa_text = match.group(0)
        
        # Extract citations with page numbers
        # Pattern: "Citation Name, 123 Wn.2d 456 .......... 5, 10, 15"
        citation_pattern = r'([^,\n]+(?:Wn\.2d|Wn\. App\.|P\.2d|P\.3d|F\.2d|F\.3d|U\.S\.|S\.Ct\.)[^\.]+)\.*\s*(\d+(?:,\s*\d+)*)'
        
        with self.db.connect() as conn:
            trans = conn.begin()
            
            try:
                for match in re.finditer(citation_pattern, toa_text):
                    citation_text = match.group(1).strip()
                    page_refs = [p.strip() for p in match.group(2).split(',')]
                    
                    insert_query = text("""
                        INSERT INTO brief_citations (
                            brief_id, citation_text, citation_type, from_toa, toa_page_refs
                        ) VALUES (
                            :brief_id, :citation_text, 'case', TRUE, :toa_page_refs
                        )
                    """)
                    
                    conn.execute(insert_query, {
                        'brief_id': brief_id,
                        'citation_text': citation_text,
                        'toa_page_refs': page_refs
                    })
                    
                    citations_found += 1
                
                trans.commit()
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Failed to extract TOA: {str(e)}")
                raise
        
        return {'citations_found': citations_found}
    
    def _update_processing_status(self, brief_id: int, status: str):
        """Update brief processing status"""
        with self.db.connect() as conn:
            update_query = text("""
                UPDATE briefs
                SET processing_status = :status
                WHERE brief_id = :brief_id
            """)
            
            conn.execute(update_query, {
                'brief_id': brief_id,
                'status': status
            })
            conn.commit()
