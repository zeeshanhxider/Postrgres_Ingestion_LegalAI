"""
Legal Text Chunker
Splits full text into semantic chunks for RAG indexing.
Production-grade with legal section detection.
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """Represents a chunk of text with metadata."""
    order: int
    text: str
    word_count: int
    char_count: int
    section: str = "CONTENT"


class LegalTextChunker:
    """
    Chunks legal text into semantically meaningful pieces.
    
    Designed for legal documents with typical patterns:
    - Court headers
    - Procedural sections
    - Facts sections
    - Analysis/Discussion
    - Conclusions
    """
    
    # Legal document section patterns
    SECTION_PATTERNS = {
        "HEADER": [
            r"IN THE .* COURT",
            r"STATE OF .*",
            r"COUNTY OF .*",
            r"No\.\s*\d+",
            r"Case No\.",
            r"Docket"
        ],
        "PARTIES": [
            r"Plaintiff",
            r"Defendant",
            r"Appellant",
            r"Respondent",
            r"Petitioner"
        ],
        "PROCEDURAL": [
            r"PROCEDURAL HISTORY",
            r"BACKGROUND",
            r"PROCEEDINGS",
            r"MOTION",
            r"APPEAL"
        ],
        "FACTS": [
            r"STATEMENT OF FACTS",
            r"FACTUAL BACKGROUND",
            r"FACTS",
            r"FINDINGS OF FACT"
        ],
        "ANALYSIS": [
            r"ANALYSIS",
            r"DISCUSSION",
            r"LEGAL ANALYSIS",
            r"CONCLUSIONS OF LAW",
            r"OPINION"
        ],
        "HOLDING": [
            r"HOLDING",
            r"CONCLUSION",
            r"DECISION",
            r"JUDGMENT",
            r"ORDER"
        ]
    }
    
    def __init__(
        self,
        target_chunk_size: int = 350,
        min_chunk_size: int = 200,
        max_chunk_size: int = 500
    ):
        """
        Initialize the chunker.
        
        Args:
            target_chunk_size: Target words per chunk (default: 350)
            min_chunk_size: Minimum words per chunk (default: 200)
            max_chunk_size: Maximum words per chunk (default: 500)
        """
        self.target_chunk_size = target_chunk_size
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
    
    def chunk_text(self, full_text: str) -> List[TextChunk]:
        """
        Chunk full text into semantic chunks.
        
        Args:
            full_text: Complete document text
            
        Returns:
            List of TextChunk objects in order
        """
        if not full_text or len(full_text.strip()) < 100:
            return []
        
        # Split into paragraphs
        paragraphs = self._split_into_paragraphs(full_text)
        
        # Identify sections
        sectioned_paragraphs = self._identify_sections(paragraphs)
        
        # Create chunks respecting section boundaries
        chunks = self._create_chunks(sectioned_paragraphs)
        
        logger.info(f"Created {len(chunks)} chunks from {len(full_text)} chars")
        return chunks
    
    def chunk_pages(self, pages: List[str]) -> List[TextChunk]:
        """
        Chunk a list of page texts into semantic chunks.
        
        Args:
            pages: List of page texts from PDF
            
        Returns:
            List of TextChunk objects in order
        """
        full_text = "\n\n".join(pages)
        return self.chunk_text(full_text)
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split on double line breaks or more
        paragraphs = re.split(r'\n\s*\n', text)
        
        # Clean and filter empty paragraphs
        cleaned = []
        for para in paragraphs:
            para = para.strip()
            # Normalize whitespace
            para = re.sub(r'\s+', ' ', para)
            if para and len(para.split()) >= 5:  # At least 5 words
                cleaned.append(para)
        
        return cleaned
    
    def _identify_sections(self, paragraphs: List[str]) -> List[Dict[str, str]]:
        """Identify which section each paragraph belongs to."""
        sectioned = []
        current_section = "CONTENT"
        
        for para in paragraphs:
            # Check if this paragraph is a section header
            detected_section = self._detect_section(para)
            if detected_section:
                current_section = detected_section
            
            sectioned.append({
                "text": para,
                "section": current_section
            })
        
        return sectioned
    
    def _detect_section(self, paragraph: str) -> Optional[str]:
        """Detect if paragraph is a section header."""
        para_upper = paragraph.upper()
        
        for section_name, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, para_upper):
                    return section_name
        
        return None
    
    def _create_chunks(self, sectioned_paragraphs: List[Dict[str, str]]) -> List[TextChunk]:
        """Create chunks from sectioned paragraphs."""
        chunks = []
        current_chunk_paras = []
        current_section = "CONTENT"
        chunk_order = 1
        
        for para_data in sectioned_paragraphs:
            para_text = para_data["text"]
            para_section = para_data["section"]
            
            # If section changes and we have content, finalize current chunk
            if para_section != current_section and current_chunk_paras:
                chunk = self._finalize_chunk(current_chunk_paras, chunk_order, current_section)
                if chunk:
                    chunks.append(chunk)
                    chunk_order += 1
                current_chunk_paras = []
            
            current_section = para_section
            current_chunk_paras.append(para_text)
            
            # Check if current chunk is large enough
            current_word_count = sum(len(p.split()) for p in current_chunk_paras)
            
            if current_word_count >= self.target_chunk_size:
                if current_word_count > self.max_chunk_size:
                    # Split into multiple chunks
                    sub_chunks = self._split_large_chunk(current_chunk_paras, chunk_order, current_section)
                    chunks.extend(sub_chunks)
                    chunk_order += len(sub_chunks)
                else:
                    # Finalize at target size
                    chunk = self._finalize_chunk(current_chunk_paras, chunk_order, current_section)
                    if chunk:
                        chunks.append(chunk)
                        chunk_order += 1
                
                current_chunk_paras = []
        
        # Handle remaining paragraphs
        if current_chunk_paras:
            chunk = self._finalize_chunk(current_chunk_paras, chunk_order, current_section)
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def _finalize_chunk(self, paragraphs: List[str], order: int, section: str) -> Optional[TextChunk]:
        """Create a TextChunk from paragraphs."""
        if not paragraphs:
            return None
        
        text = "\n\n".join(paragraphs)
        word_count = len(text.split())
        
        # Skip very small chunks
        if word_count < self.min_chunk_size // 2:
            return None
        
        return TextChunk(
            order=order,
            text=text,
            word_count=word_count,
            char_count=len(text),
            section=section
        )
    
    def _split_large_chunk(self, paragraphs: List[str], start_order: int, section: str) -> List[TextChunk]:
        """Split a large chunk into smaller ones."""
        chunks = []
        current_paras = []
        current_order = start_order
        
        for para in paragraphs:
            current_paras.append(para)
            word_count = sum(len(p.split()) for p in current_paras)
            
            if word_count >= self.target_chunk_size:
                chunk = self._finalize_chunk(current_paras, current_order, section)
                if chunk:
                    chunks.append(chunk)
                    current_order += 1
                current_paras = []
        
        # Handle remaining
        if current_paras:
            chunk = self._finalize_chunk(current_paras, current_order, section)
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def determine_section(self, text: str) -> str:
        """
        Determine what section a chunk represents.
        More nuanced than pattern matching.
        """
        text_lower = text.lower()
        
        # Check for specific content types
        if any(word in text_lower for word in ['facts', 'background', 'procedural history']):
            return 'FACTS'
        elif any(word in text_lower for word in ['analysis', 'discussion', 'legal standard']):
            return 'ANALYSIS'
        elif any(word in text_lower for word in ['conclusion', 'holding', 'we conclude', 'affirm', 'reverse']):
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
