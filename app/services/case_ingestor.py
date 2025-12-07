"""
Legal Case Ingestor
Complete legal case processing with AI/Regex extraction, chunking, word/phrase indexing, and database storage.
Designed for comprehensive RAG capabilities and reliable data extraction.
"""

import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Import our extraction and database services
from .ai_extractor import extract_case_data
from .regex_extractor import extract_case_data_regex
from .database_inserter import DatabaseInserter

# Import word and phrase processing
from .word_processor import WordProcessor
from .phrase_extractor import PhraseExtractor

# Import existing chunking and embedding
from ..pdf_parser import extract_text_from_pdf
from ..chunker import LegalTextChunker, TextChunk
from .embedding_service import generate_embedding
from .sentence_processor import SentenceProcessor

logger = logging.getLogger(__name__)

class LegalCaseIngestor:
    """
    Complete legal case ingestor that provides:
    1. Regex extraction (fast, free) OR AI extraction (slow, accurate)
    2. Database insertion (comprehensive schema)
    3. PDF chunking (for RAG)
    4. Word/phrase processing (for precise search)
    5. Embedding generation (for semantic search)
    """
    
    def __init__(self, db_engine: Engine):
        self.db = db_engine
        self.text_chunker = LegalTextChunker()
        
        # Initialize services
        self.database_inserter = DatabaseInserter(db_engine)
        self.word_processor = WordProcessor(db_engine)
        self.phrase_extractor = PhraseExtractor(db_engine)
        self.sentence_processor = SentenceProcessor(db_engine)
    
    def ingest_pdf_case(
        self, 
        pdf_content: bytes, 
        metadata: Dict[str, Any],
        source_file_info: Optional[Dict[str, str]] = None,
        enable_ai_extraction: bool = False,  # Default to regex (fast)
        extraction_mode: str = 'regex'  # 'regex', 'ai', or 'none'
    ) -> Dict[str, Any]:
        """
        Main ingestion method - processes PDF with complete hybrid approach
        
        Args:
            pdf_content: PDF file content as bytes
            metadata: Case metadata
            source_file_info: Source file information (filename, path)
            enable_ai_extraction: DEPRECATED - use extraction_mode instead
            extraction_mode: 'regex' (fast), 'ai' (slow), or 'none' (metadata only)
            
        Returns:
            Dictionary with ingestion results
        """
        # Handle legacy parameter
        if enable_ai_extraction:
            extraction_mode = 'ai'
        
        case_id = None

        try:
            logger.info(f"🚀 Starting case ingestion (mode: {extraction_mode})")
            
            # Step 1: Parse PDF content
            logger.info("📖 Parsing PDF content...")
            pages = extract_text_from_pdf(pdf_content)
            full_text = '\n\n'.join(pages)
            
            if not full_text or len(full_text.strip()) < 100:
                raise ValueError("PDF content too short or empty")
            
            logger.info(f"✅ Parsed PDF: {len(pages)} pages, {len(full_text)} characters")
            
            # Step 2: Extract case data based on mode
            if extraction_mode == 'regex':
                # FAST: Use regex extraction
                logger.info("🔍 Running regex extraction...")
                regex_result = extract_case_data_regex(full_text, metadata)
                
                logger.info(f"✅ Regex extraction: {len(regex_result.judges)} judges, "
                           f"{len(regex_result.citations)} citations, "
                           f"{len(regex_result.statutes)} statutes")
                
                # Insert using regex result
                case_id = self.database_inserter.insert_regex_extraction(
                    regex_result, metadata, source_file_info
                )
                
            elif extraction_mode == 'ai':
                # SLOW: Use AI extraction (original method)
                logger.info("🤖 Running AI extraction...")
                case_info = {
                    'case_number': metadata.get('case_number', 'Unknown'),
                    'title': metadata.get('title', metadata.get('case_title', 'Unknown')),
                    'court_level': metadata.get('court_level', 'Unknown'),
                    'division': metadata.get('division', 'Unknown'),
                    'publication': metadata.get('publication', 'Unknown'),
                    'court_info_raw': metadata.get('court_info_raw', '')
                }
                
                extracted_data = extract_case_data(full_text, case_info)
                
                if extracted_data:
                    logger.info("✅ AI extraction successful")
                    case_id = self.database_inserter.insert_complete_case(
                        extracted_data, metadata, source_file_info
                    )
                else:
                    logger.warning("⚠️ AI extraction failed, falling back to regex")
                    regex_result = extract_case_data_regex(full_text, metadata)
                    case_id = self.database_inserter.insert_regex_extraction(
                        regex_result, metadata, source_file_info
                    )
            else:
                raise ValueError(f"Invalid extraction_mode: {extraction_mode}. Use 'regex' or 'ai'.")
            
            if not case_id:
                raise ValueError("Failed to insert case record")
            
            logger.info(f"✅ Case inserted with ID: {case_id}")
            
            # Step 3: Create document record if we have a case
            document_id = None
            if case_id and source_file_info:
                logger.info("📄 Creating document record...")
                # Enhance source file info with page count
                enhanced_source_info = source_file_info.copy()
                enhanced_source_info['page_count'] = len(pages)
                
                # Resolve dimension IDs for document
                dimension_ids = self.database_inserter.dimension_service.resolve_metadata_to_ids(metadata)
                document_id = self.database_inserter.create_document_record(case_id, enhanced_source_info, dimension_ids)
                
                if document_id:
                    logger.info(f"✅ Created document record with ID: {document_id}")
                else:
                    logger.warning("⚠️ Failed to create document record")
            
            # Step 4: Create chunks for RAG
            logger.info("📄 Creating text chunks...")
            chunks = self.text_chunker.chunk_pages(pages)
            logger.info(f"✅ Created {len(chunks)} text chunks")
            
            # Step 5: Prepare chunks (no individual chunk embeddings)
            logger.info("📦 Preparing chunks for processing...")
            enhanced_chunks = []
            for chunk in chunks:
                enhanced_chunk = {
                    'chunk': chunk,
                    'embedding': None,  # No chunk-level embeddings
                    'section': self._determine_section(chunk.text)
                }
                enhanced_chunks.append(enhanced_chunk)
            
            logger.info(f"✅ Prepared {len(enhanced_chunks)} chunks")
            
            # Only process chunks if we have a valid case_id
            chunk_ids = []
            sentence_stats = {'total_sentences': 0, 'total_words': 0}
            word_stats = {'total_words': 0, 'unique_words': 0}
            phrase_stats = {'phrases_inserted': 0}
            case_stats = {}
            
            if case_id:
                # Step 6: Insert chunks with embeddings
                logger.info("💾 Inserting chunks...")
                chunk_ids = self._insert_chunks(case_id, enhanced_chunks, full_text, document_id)
                logger.info(f"✅ Inserted {len(chunk_ids)} chunks")
                
                # Step 7: Process chunks into sentences
                logger.info("✂️ Processing chunks into sentences...")
                sentence_stats = self._process_case_sentences(case_id, enhanced_chunks, chunk_ids, document_id)
                logger.info(f"✅ Processed {sentence_stats['total_sentences']} sentences with {sentence_stats['total_words']} words")
                
                # Step 8: Process words for precise search (sentence-level)
                logger.info("📝 Processing words at sentence level...")
                word_stats = self.word_processor.process_case_sentences_words(case_id, document_id)
                logger.info(f"✅ Processed {word_stats['total_words']} words, {word_stats['unique_words']} unique from {word_stats['sentences_processed']} sentences")
                
                # Step 9: Extract phrases for terminology search
                logger.info("🔤 Extracting phrases...")
                phrase_stats = self._extract_case_phrases(case_id, enhanced_chunks, document_id)
                logger.info(f"✅ Extracted {phrase_stats['phrases_inserted']} legal phrases")
                
                # Step 10: Generate embeddings for global search
                logger.info("🌟 Generating embeddings for global search...")
                
                # Generate embeddings for each chunk and store in global embeddings table
                self._create_global_embeddings(case_id, enhanced_chunks, chunk_ids, document_id)
                
                # Also create case-level embedding from combined text
                all_chunk_texts = [chunk['chunk'].text for chunk in enhanced_chunks]
                combined_text = "\n\n".join(all_chunk_texts)
                use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
                case_embedding = generate_embedding(combined_text, prefer_ollama=use_ollama)
                
                # Update case with embedding and full text
                self._update_case_embedding(case_id, case_embedding, full_text, source_file_info)
                logger.info("✅ Created global embeddings and case-level embedding")
                
                # Step 9: Update word document frequencies
                self.word_processor.update_word_document_frequencies(case_id)
                
                # Get final statistics
                case_stats = self.database_inserter.get_case_stats(case_id)
            else:
                logger.warning("⚠️ Skipping chunk processing - no valid case_id")
            
            result = {
                'case_id': case_id,
                'status': 'success',
                'extraction_mode': extraction_mode,
                'chunks_created': len(chunk_ids),
                'words_processed': word_stats['total_words'],
                'unique_words': word_stats['unique_words'],
                'phrases_extracted': phrase_stats['phrases_inserted'],
                'case_stats': case_stats,
                'full_text_length': len(full_text),
                'embedding_dimension': len(case_embedding) if case_embedding else 0
            }
            
            logger.info(f"🎉 Case ingestion completed successfully for case {case_id}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Case ingestion failed for case {case_id}: {str(e)}")
            raise
    
    def _determine_section(self, text: str) -> str:
        """Determine what section this chunk represents"""
        text_lower = text.lower()
        
        # Common legal document sections
        if any(word in text_lower for word in ['facts', 'background', 'procedural history']):
            return 'FACTS'
        elif any(word in text_lower for word in ['analysis', 'discussion', 'legal standard']):
            return 'ANALYSIS'
        elif any(word in text_lower for word in ['conclusion', 'holding', 'we conclude']):
            return 'CONCLUSION'
        elif any(word in text_lower for word in ['custody', 'parenting plan', 'residential time']):
            return 'CUSTODY'
        elif any(word in text_lower for word in ['support', 'maintenance', 'alimony']):
            return 'SUPPORT'
        elif any(word in text_lower for word in ['property', 'assets', 'debt']):
            return 'PROPERTY'
        elif any(word in text_lower for word in ['attorney fees', 'costs']):
            return 'FEES'
        else:
            return 'GENERAL'
    
    def _insert_chunks(self, case_id: int, enhanced_chunks: List[Dict], full_text: str, document_id: Optional[int] = None) -> List[int]:
        """Insert chunks with embeddings into database"""
        chunk_ids = []
        
        with self.db.connect() as conn:
            # Update case with full text
            update_case_query = text("UPDATE cases SET full_text = :full_text WHERE case_id = :case_id")
            conn.execute(update_case_query, {'full_text': full_text, 'case_id': case_id})
            
            for i, enhanced_chunk in enumerate(enhanced_chunks):
                chunk = enhanced_chunk['chunk']
                section = enhanced_chunk['section']
                
                # No chunk-level embeddings
                
                # Insert chunk with new schema
                query = text("""
                    INSERT INTO case_chunks (
                        case_id, document_id, chunk_order, section, text, 
                        sentence_count, created_at, updated_at
                    ) VALUES (
                        :case_id, :document_id, :chunk_order, :section, :text,
                        :sentence_count, :created_at, :updated_at
                    )
                    RETURNING chunk_id
                """)
                
                now = datetime.now()
                result = conn.execute(query, {
                    'case_id': case_id,
                    'document_id': document_id,
                    'chunk_order': chunk.order,
                    'section': section,
                    'text': chunk.text,
                    'sentence_count': 0,  # Will be updated later during sentence processing
                    'created_at': now,
                    'updated_at': now
                })
                
                chunk_row = result.fetchone()
                chunk_ids.append(chunk_row.chunk_id)
            
            conn.commit()
        
        return chunk_ids
    
    def _process_case_sentences(self, case_id: int, enhanced_chunks: List[Dict], 
                               chunk_ids: List[int], document_id: Optional[int] = None) -> Dict[str, int]:
        """Process chunks into sentences and create sentence records"""
        total_sentences = 0
        total_words = 0
        global_sentence_counter = 0
        
        try:
            for i, (enhanced_chunk, chunk_id) in enumerate(zip(enhanced_chunks, chunk_ids)):
                chunk = enhanced_chunk['chunk']
                
                # Process chunk into sentences
                sentence_records = self.sentence_processor.process_chunk_sentences(
                    case_id=case_id,
                    chunk_id=chunk_id,
                    chunk_text=chunk.text,
                    document_id=document_id,
                    global_sentence_counter=global_sentence_counter
                )
                
                # Update counters
                chunk_sentence_count = len(sentence_records)
                total_sentences += chunk_sentence_count
                total_words += sum(s['word_count'] for s in sentence_records)
                global_sentence_counter += chunk_sentence_count
                
                # Update chunk sentence count
                self.sentence_processor.update_chunk_sentence_count(chunk_id, chunk_sentence_count)
                
                logger.debug(f"Processed chunk {i+1}/{len(chunk_ids)}: {chunk_sentence_count} sentences")
            
            return {
                'total_sentences': total_sentences,
                'total_words': total_words
            }
            
        except Exception as e:
            logger.error(f"Error processing sentences: {e}")
            return {
                'total_sentences': 0,
                'total_words': 0
            }
    
    def _process_case_words(self, case_id: int, enhanced_chunks: List[Dict]) -> Dict[str, int]:
        """Process all words in case chunks"""
        total_words = 0
        unique_words = set()
        
        for enhanced_chunk in enhanced_chunks:
            chunk = enhanced_chunk['chunk']
            
            # Get chunk_id - we need to query for it since we just inserted
            with self.db.connect() as conn:
                query = text("""
                    SELECT chunk_id FROM case_chunks 
                    WHERE case_id = :case_id AND chunk_order = :chunk_order
                """)
                result = conn.execute(query, {
                    'case_id': case_id,
                    'chunk_order': chunk.order
                })
                row = result.fetchone()
                chunk_id = str(row.chunk_id)
            
            # Process words for this chunk
            word_stats = self.word_processor.process_chunk_words(
                case_id, chunk_id, chunk.text
            )
            
            total_words += word_stats['words_processed']
            
            # Get unique words from this chunk
            tokens = self.word_processor.tokenize_text(chunk.text)
            unique_words.update(tokens)
        
        return {
            'total_words': total_words,
            'unique_words': len(unique_words)
        }
    
    def _extract_case_phrases(self, case_id: int, enhanced_chunks: List[Dict], document_id: Optional[int] = None) -> Dict[str, int]:
        """Extract phrases from all case chunks"""
        # Prepare chunk data for phrase extraction
        chunk_data = []
        
        for enhanced_chunk in enhanced_chunks:
            chunk = enhanced_chunk['chunk']
            
            # Get chunk_id from database
            with self.db.connect() as conn:
                query = text("""
                    SELECT chunk_id FROM case_chunks 
                    WHERE case_id = :case_id AND chunk_order = :chunk_order
                """)
                result = conn.execute(query, {
                    'case_id': case_id,
                    'chunk_order': chunk.order
                })
                row = result.fetchone()
                chunk_id = str(row.chunk_id)
            
            chunk_data.append({
                'chunk_id': chunk_id,
                'text': chunk.text
            })
        
        # Extract phrases
        return self.phrase_extractor.process_case_phrases(case_id, chunk_data, document_id)
    
    def _create_case_summary(self, extracted_data, full_text: str) -> str:
        """Create a comprehensive case summary for embedding"""
        summary_parts = []
        
        if extracted_data:
            case = extracted_data.case
            summary_parts.append(f"Case: {case.title}")
            summary_parts.append(f"Court: {case.court_level.value} - {case.court}")
            if case.district and case.district.value != "N/A":
                summary_parts.append(f"Division: {case.district.value}")
            summary_parts.append(f"Summary: {case.summary}")
            
            # Add party information
            if extracted_data.parties:
                parties_info = []
                for party in extracted_data.parties:
                    parties_info.append(f"{party.name} ({party.legal_role.value}, {party.personal_role.value})")
                summary_parts.append(f"Parties: {'; '.join(parties_info)}")
            
            # Add key issues
            if extracted_data.issues_decisions:
                issues_info = []
                for issue in extracted_data.issues_decisions[:3]:  # Top 3 issues
                    issues_info.append(f"{issue.category}: {issue.issue_summary[:100]}")
                summary_parts.append(f"Key Issues: {'; '.join(issues_info)}")
        summary_parts.append(f"Content: {full_text[:500]}...")
        
        return "\n".join(summary_parts)
    
    def _update_case_embedding(
        self, 
        case_id: int, 
        embedding: List[float], 
        full_text: str,
        source_file_info: Optional[Dict[str, str]]
    ) -> None:
        """Update case with embedding, full text, and source file info"""
        with self.db.connect() as conn:
            query = text("""
                UPDATE cases SET 
                    full_text = :full_text,
                    full_embedding = :embedding,
                    source_file = :source_file,
                    source_file_path = :source_file_path,
                    extraction_timestamp = :extraction_timestamp,
                    updated_at = :updated_at
                WHERE case_id = :case_id
            """)
            
            conn.execute(query, {
                'case_id': case_id,
                'full_text': full_text,
                'embedding': embedding,
                'source_file': source_file_info.get('filename') if source_file_info else None,
                'source_file_path': source_file_info.get('file_path') if source_file_info else None,
                'extraction_timestamp': datetime.now(),
                'updated_at': datetime.now()
            })
            conn.commit()
    
    def get_ingestion_stats(self, case_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics for an ingested case"""
        with self.db.connect() as conn:
            query = text("""
                SELECT 
                    c.title,
                    c.court,
                    c.created_at,
                    LENGTH(c.full_text) as text_length,
                    (SELECT COUNT(*) FROM case_chunks WHERE case_id = :case_id) as chunks,
                    (SELECT COUNT(*) FROM parties WHERE case_id = :case_id) as parties,
                    (SELECT COUNT(*) FROM attorneys WHERE case_id = :case_id) as attorneys,
                    (SELECT COUNT(*) FROM case_judges WHERE case_id = :case_id) as judges,
                    (SELECT COUNT(*) FROM issues_decisions WHERE case_id = :case_id) as issues,
                    (SELECT COUNT(*) FROM arguments WHERE case_id = :case_id) as arguments,
                    (SELECT COUNT(*) FROM citation_edges WHERE source_case_id = :case_id) as citations,
                    (SELECT COUNT(*) FROM case_phrases WHERE case_id = :case_id) as phrases,
                    (SELECT COUNT(DISTINCT word_id) FROM word_occurrence WHERE case_id = :case_id) as unique_words
                FROM cases c
                WHERE c.case_id = :case_id
            """)
            
            result = conn.execute(query, {'case_id': case_id})
            row = result.fetchone()
            
            if not row:
                return {'error': 'Case not found'}
            
            return {
                'case_id': case_id,
                'title': row.title,
                'court': row.court,
                'created_at': row.created_at.isoformat() if row.created_at else None,
                'text_length': row.text_length,
                'chunks': row.chunks,
                'entities': {
                    'parties': row.parties,
                    'attorneys': row.attorneys,
                    'judges': row.judges,
                    'issues': row.issues,
                    'arguments': row.arguments,
                    'citations': row.citations
                },
                'search_indices': {
                    'phrases': row.phrases,
                    'unique_words': row.unique_words
                }
            }
    
    def _create_global_embeddings(self, case_id: int, enhanced_chunks: List[Dict], 
                                 chunk_ids: List[int], document_id: Optional[int] = None) -> None:
        """Create embeddings for each chunk and store in global embeddings table"""
        
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        
        with self.db.connect() as conn:
            for i, (enhanced_chunk, chunk_id) in enumerate(zip(enhanced_chunks, chunk_ids)):
                chunk = enhanced_chunk['chunk']
                section = enhanced_chunk['section']
                
                # Generate embedding for this chunk
                embedding = generate_embedding(chunk.text, prefer_ollama=use_ollama)
                
                if embedding is not None:
                    embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
                    
                    # Insert into global embeddings table
                    query = text("""
                        INSERT INTO embeddings (
                            case_id, chunk_id, document_id, text, embedding, 
                            chunk_order, section, created_at, updated_at
                        ) VALUES (
                            :case_id, :chunk_id, :document_id, :text, :embedding,
                            :chunk_order, :section, NOW(), NOW()
                        )
                    """)
                    
                    conn.execute(query, {
                        'case_id': case_id,
                        'chunk_id': chunk_id,
                        'document_id': document_id,
                        'text': chunk.text,
                        'embedding': embedding_list,
                        'chunk_order': chunk.order,
                        'section': section
                    })
                    
                    logger.debug(f"Created global embedding for chunk {chunk_id}")
                else:
                    logger.warning(f"Failed to generate embedding for chunk {chunk_id}")
            
            conn.commit()
            logger.info(f"✅ Created {len(chunk_ids)} global embeddings")
