"""
RAG Processor - Main orchestrator for all RAG pipeline components.

Coordinates chunking, sentence processing, word indexing, phrase extraction,
and embedding generation with configurable options.
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio

import psycopg2
from psycopg2.extras import execute_values
import httpx

from .config import Config
from .chunker import LegalTextChunker, TextChunk
from .sentence_processor import SentenceProcessor
from .word_processor import WordProcessor
from .phrase_extractor import PhraseExtractor
from .dimension_service import DimensionService

logger = logging.getLogger(__name__)


class ChunkEmbeddingMode(Enum):
    """Options for chunk-level embedding generation."""
    ALL = "all"           # Generate embeddings for all chunks
    IMPORTANT = "important"  # Only ANALYSIS, HOLDING, FACTS sections
    NONE = "none"         # No chunk embeddings (rely on case-level only)


class PhraseFilterMode(Enum):
    """Options for phrase filtering strictness."""
    STRICT = "strict"     # Only phrases with legal terms
    RELAXED = "relaxed"   # All meaningful phrases


@dataclass
class RAGProcessingResult:
    """Result of RAG processing for a case."""
    case_id: int
    chunks_created: int
    sentences_created: int
    words_indexed: int
    phrases_extracted: int
    embeddings_generated: int
    errors: List[str]


class RAGProcessor:
    """
    Main orchestrator for RAG processing pipeline.
    
    Handles:
    - Text chunking with section awareness
    - Sentence extraction and indexing
    - Word dictionary and occurrence tracking
    - Legal phrase extraction
    - Chunk-level embedding generation
    """
    
    # Sections considered "important" for selective embedding
    IMPORTANT_SECTIONS = {"ANALYSIS", "HOLDING", "FACTS"}
    
    def __init__(
        self,
        db_connection: psycopg2.extensions.connection,
        chunk_embedding_mode: ChunkEmbeddingMode = ChunkEmbeddingMode.ALL,
        phrase_filter_mode: PhraseFilterMode = PhraseFilterMode.STRICT,
        batch_size: int = 50,
        embedding_batch_size: int = 10
    ):
        """
        Initialize RAG processor.
        
        Args:
            db_connection: Active database connection
            chunk_embedding_mode: How to handle chunk embeddings
            phrase_filter_mode: Strictness of phrase filtering
            batch_size: Batch size for database inserts
            embedding_batch_size: Batch size for embedding API calls
        """
        self.conn = db_connection
        self.chunk_embedding_mode = chunk_embedding_mode
        self.phrase_filter_mode = phrase_filter_mode
        self.batch_size = batch_size
        self.embedding_batch_size = embedding_batch_size
        
        # Initialize sub-processors
        self.chunker = LegalTextChunker()
        self.sentence_processor = SentenceProcessor()
        self.word_processor = WordProcessor(db_connection, batch_size=batch_size)
        self.phrase_extractor = PhraseExtractor(
            strict_filtering=(phrase_filter_mode == PhraseFilterMode.STRICT)
        )
        self.dimension_service = DimensionService(db_connection)
        
        logger.info(
            f"RAGProcessor initialized: chunk_embedding={chunk_embedding_mode.value}, "
            f"phrase_filter={phrase_filter_mode.value}"
        )
    
    async def process_case(
        self,
        case_id: int,
        full_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RAGProcessingResult:
        """
        Process a case through the complete RAG pipeline.
        
        Args:
            case_id: Database ID of the case
            full_text: Full text content of the case
            metadata: Optional metadata dict (for dimension resolution)
            
        Returns:
            RAGProcessingResult with processing statistics
        """
        errors = []
        chunks_created = 0
        sentences_created = 0
        words_indexed = 0
        phrases_extracted = 0
        embeddings_generated = 0
        
        try:
            logger.info(f"Starting RAG processing for case {case_id}")
            
            # Step 1: Create chunks
            chunks = self.chunker.create_chunks(full_text)
            logger.info(f"Created {len(chunks)} chunks")
            
            # Step 2: Insert chunks and get IDs
            chunk_ids = await self._insert_chunks(case_id, chunks)
            chunks_created = len(chunk_ids)
            
            # Step 3: Generate chunk embeddings based on mode
            if self.chunk_embedding_mode != ChunkEmbeddingMode.NONE:
                embeddings_generated = await self._generate_chunk_embeddings(
                    chunks, chunk_ids
                )
            
            # Step 4: Process sentences for each chunk
            for chunk, chunk_id in zip(chunks, chunk_ids):
                try:
                    sentence_ids = self.sentence_processor.process_chunk_sentences(
                        self.conn, chunk_id, chunk.text
                    )
                    sentences_created += len(sentence_ids)
                    
                    # Step 5: Process words for each sentence
                    for sentence_id, sentence_text in zip(
                        sentence_ids, 
                        self.sentence_processor.split_into_sentences(chunk.text)
                    ):
                        word_count = self.word_processor.process_sentence_words(
                            sentence_id, sentence_text
                        )
                        words_indexed += word_count
                        
                except Exception as e:
                    logger.error(f"Error processing chunk {chunk_id}: {e}")
                    errors.append(f"Chunk {chunk_id}: {str(e)}")
            
            # Flush any remaining word occurrences
            self.word_processor.flush()
            
            # Step 6: Extract phrases for the entire case
            try:
                phrase_count = self.phrase_extractor.process_case_phrases(
                    self.conn, case_id, full_text
                )
                phrases_extracted = phrase_count
            except Exception as e:
                logger.error(f"Error extracting phrases: {e}")
                errors.append(f"Phrase extraction: {str(e)}")
            
            # Commit all changes
            self.conn.commit()
            
            logger.info(
                f"RAG processing complete for case {case_id}: "
                f"{chunks_created} chunks, {sentences_created} sentences, "
                f"{words_indexed} words, {phrases_extracted} phrases, "
                f"{embeddings_generated} embeddings"
            )
            
        except Exception as e:
            logger.error(f"RAG processing failed for case {case_id}: {e}")
            errors.append(f"Fatal: {str(e)}")
            self.conn.rollback()
        
        return RAGProcessingResult(
            case_id=case_id,
            chunks_created=chunks_created,
            sentences_created=sentences_created,
            words_indexed=words_indexed,
            phrases_extracted=phrases_extracted,
            embeddings_generated=embeddings_generated,
            errors=errors
        )
    
    async def _insert_chunks(
        self,
        case_id: int,
        chunks: List[TextChunk]
    ) -> List[int]:
        """Insert chunks into database and return their IDs."""
        chunk_ids = []
        cursor = self.conn.cursor()
        
        try:
            for chunk in chunks:
                cursor.execute("""
                    INSERT INTO case_chunks (
                        case_id, chunk_index, chunk_text,
                        section_type, start_char, end_char,
                        word_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    case_id,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.section_type,
                    chunk.start_char,
                    chunk.end_char,
                    chunk.word_count
                ))
                chunk_ids.append(cursor.fetchone()[0])
            
            logger.debug(f"Inserted {len(chunk_ids)} chunks for case {case_id}")
            return chunk_ids
            
        except Exception as e:
            logger.error(f"Error inserting chunks: {e}")
            raise
        finally:
            cursor.close()
    
    async def _generate_chunk_embeddings(
        self,
        chunks: List[TextChunk],
        chunk_ids: List[int]
    ) -> int:
        """Generate embeddings for chunks based on mode."""
        embeddings_generated = 0
        cursor = self.conn.cursor()
        
        try:
            # Filter chunks based on mode
            if self.chunk_embedding_mode == ChunkEmbeddingMode.IMPORTANT:
                eligible = [
                    (chunk, chunk_id) 
                    for chunk, chunk_id in zip(chunks, chunk_ids)
                    if chunk.section_type in self.IMPORTANT_SECTIONS
                ]
            else:  # ALL mode
                eligible = list(zip(chunks, chunk_ids))
            
            if not eligible:
                return 0
            
            logger.info(f"Generating embeddings for {len(eligible)} chunks")
            
            # Process in batches
            for i in range(0, len(eligible), self.embedding_batch_size):
                batch = eligible[i:i + self.embedding_batch_size]
                
                for chunk, chunk_id in batch:
                    try:
                        embedding = await self._generate_embedding(chunk.text)
                        if embedding:
                            cursor.execute("""
                                UPDATE case_chunks
                                SET chunk_embedding = %s
                                WHERE id = %s
                            """, (embedding, chunk_id))
                            embeddings_generated += 1
                    except Exception as e:
                        logger.warning(f"Failed to generate embedding for chunk {chunk_id}: {e}")
            
            return embeddings_generated
            
        finally:
            cursor.close()
    
    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using Ollama."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{Config.OLLAMA_BASE_URL}/api/embeddings",
                    json={
                        "model": Config.OLLAMA_EMBEDDING_MODEL,
                        "prompt": text[:8000]  # Truncate if too long
                    }
                )
                response.raise_for_status()
                result = response.json()
                return result.get("embedding")
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None


class SyncRAGProcessor(RAGProcessor):
    """
    Synchronous wrapper for RAGProcessor.
    
    Use this when calling from non-async contexts.
    """
    
    def process_case_sync(
        self,
        case_id: int,
        full_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RAGProcessingResult:
        """Synchronous version of process_case."""
        return asyncio.run(self.process_case(case_id, full_text, metadata))
    
    def generate_embedding_sync(self, text: str) -> Optional[List[float]]:
        """Synchronous version of embedding generation."""
        return asyncio.run(self._generate_embedding(text))


def create_rag_processor(
    db_connection: psycopg2.extensions.connection,
    chunk_embedding_mode: str = "all",
    phrase_filter_mode: str = "strict",
    batch_size: int = 50
) -> SyncRAGProcessor:
    """
    Factory function to create RAG processor with string arguments.
    
    Args:
        db_connection: Active database connection
        chunk_embedding_mode: "all", "important", or "none"
        phrase_filter_mode: "strict" or "relaxed"
        batch_size: Batch size for database operations
        
    Returns:
        Configured SyncRAGProcessor instance
    """
    # Convert string to enum
    try:
        embedding_mode = ChunkEmbeddingMode(chunk_embedding_mode.lower())
    except ValueError:
        logger.warning(f"Invalid chunk_embedding_mode '{chunk_embedding_mode}', using 'all'")
        embedding_mode = ChunkEmbeddingMode.ALL
    
    try:
        filter_mode = PhraseFilterMode(phrase_filter_mode.lower())
    except ValueError:
        logger.warning(f"Invalid phrase_filter_mode '{phrase_filter_mode}', using 'strict'")
        filter_mode = PhraseFilterMode.STRICT
    
    return SyncRAGProcessor(
        db_connection=db_connection,
        chunk_embedding_mode=embedding_mode,
        phrase_filter_mode=filter_mode,
        batch_size=batch_size
    )
