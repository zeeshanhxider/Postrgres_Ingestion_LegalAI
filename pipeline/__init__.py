"""
Legal Case Ingestion Pipeline
Clean, production-grade extraction using LlamaParse + Ollama LLM.

Components:
- PDFExtractor: LlamaParse + pdfplumber fallback for PDF text extraction
- LLMExtractor: Ollama qwen:32b for structured data extraction
- CaseProcessor: Orchestrates PDF → LLM → ExtractedCase
- DatabaseInserter: SQL insertion with RAG processing integration

RAG Components:
- LegalTextChunker: Section-aware text chunking
- SentenceProcessor: Sentence extraction with citation protection
- WordProcessor: Word dictionary and occurrence tracking
- PhraseExtractor: Legal phrase n-gram extraction
- RAGProcessor: Main RAG orchestrator with configurable options
- DimensionService: FK resolution for dimension tables
"""

from .pdf_extractor import PDFExtractor
from .llm_extractor import LLMExtractor
from .case_processor import CaseProcessor
from .db_inserter import DatabaseInserter
from .models import ExtractedCase, CaseMetadata

# RAG components
from .chunker import LegalTextChunker, TextChunk
from .sentence_processor import SentenceProcessor
from .word_processor import WordProcessor
from .phrase_extractor import PhraseExtractor
from .rag_processor import (
    RAGProcessor,
    SyncRAGProcessor, 
    create_rag_processor,
    ChunkEmbeddingMode,
    PhraseFilterMode
)
from .dimension_service import DimensionService

__all__ = [
    # Core pipeline
    'PDFExtractor',
    'LLMExtractor', 
    'CaseProcessor',
    'DatabaseInserter',
    'ExtractedCase',
    'CaseMetadata',
    
    # RAG components
    'LegalTextChunker',
    'TextChunk',
    'SentenceProcessor',
    'WordProcessor',
    'PhraseExtractor',
    'RAGProcessor',
    'SyncRAGProcessor',
    'create_rag_processor',
    'ChunkEmbeddingMode',
    'PhraseFilterMode',
    'DimensionService',
]
