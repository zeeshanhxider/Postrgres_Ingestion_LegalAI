"""
Embedding service using Ollama (following your working approach)
Generates embeddings for both case-level and chunk-level content
"""

import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

def local_ollama_embed(text: str, model: str = None) -> List[float]:
    """
    Create an embedding using a local Ollama embeddings model.
    Default model is a 1024-dim choice to match DB schema.
    
    This is the EXACT same function from your working code.
    """
    try:
        # Try the new langchain-ollama package first
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        # Fallback to the deprecated version
        from langchain_community.embeddings import OllamaEmbeddings
    
    ollama_model = model or os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    embeddings = OllamaEmbeddings(model=ollama_model, base_url=ollama_base_url)
    return embeddings.embed_query(text)

def local_ollama_embed_batch(texts: List[str], model: str = None) -> List[List[float]]:
    """
    Create embeddings for multiple texts in a single batch call.
    Much faster than calling local_ollama_embed multiple times.
    
    Args:
        texts: List of texts to embed
        model: Ollama model name (default: mxbai-embed-large)
        
    Returns:
        List of embedding vectors
    """
    try:
        # Try the new langchain-ollama package first
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        # Fallback to the deprecated version
        from langchain_community.embeddings import OllamaEmbeddings
    
    ollama_model = model or os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    embeddings = OllamaEmbeddings(model=ollama_model, base_url=ollama_base_url)
    return embeddings.embed_documents(texts)

def openai_embed(text: str, dimensions: int = 1024) -> List[float]:
    """
    Create an embedding using OpenAI as fallback.
    Server deployment can replace this with an OSS model.
    """
    try:
        from openai import OpenAI
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        client = OpenAI(api_key=api_key)
        # text-embedding-3-large supports dimensions parameter
        resp = client.embeddings.create(model="text-embedding-3-large", input=text, dimensions=dimensions)
        return resp.data[0].embedding
    except Exception as e:
        logger.warning(f"OpenAI embedding failed: {e}")
        raise

def generate_embedding(text: str, prefer_ollama: bool = True, ollama_only: bool = False) -> Optional[List[float]]:
    """
    Generate embedding with fallback logic.
    
    Args:
        text: Text to embed
        prefer_ollama: Whether to try Ollama first (default True)
        ollama_only: If True, only use Ollama (no OpenAI fallback)
        
    Returns:
        Embedding vector as list of floats, or None if all methods fail
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding")
        return None
    
    # Check if Ollama-only mode is enabled via environment
    if os.getenv('USE_OLLAMA', 'false').lower() == 'true':
        ollama_only = True
    
    # Try Ollama first (your working approach)
    if prefer_ollama or ollama_only:
        try:
            logger.debug("Attempting Ollama embedding...")
            embedding = local_ollama_embed(text)
            logger.debug(f"Ollama embedding successful, dimension: {len(embedding)}")
            return embedding
        except Exception as e:
            if ollama_only:
                logger.error(f"Ollama-only mode: embedding failed: {e}")
                return None
            logger.warning(f"Ollama embedding failed: {e}, trying OpenAI...")
    
    # Fallback to OpenAI (only if not in Ollama-only mode)
    if not ollama_only:
        try:
            logger.debug("Attempting OpenAI embedding...")
            embedding = openai_embed(text)
            logger.debug(f"OpenAI embedding successful, dimension: {len(embedding)}")
            return embedding
        except Exception as e:
            logger.error(f"All embedding methods failed: {e}")
            return None
    
    logger.error("Embedding generation failed (Ollama-only mode)")
    return None

def generate_embeddings_batch(texts: List[str], prefer_ollama: bool = True, ollama_only: bool = False) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in batch (much faster than individual calls).
    
    Args:
        texts: List of texts to embed
        prefer_ollama: Whether to try Ollama first (default True)
        ollama_only: If True, only use Ollama (no OpenAI fallback)
        
    Returns:
        List of embedding vectors (None for failed embeddings)
    """
    if not texts:
        return []
    
    # Filter out empty texts
    filtered_texts = [(i, text) for i, text in enumerate(texts) if text and text.strip()]
    if not filtered_texts:
        logger.warning("All texts are empty")
        return [None] * len(texts)
    
    indices, valid_texts = zip(*filtered_texts) if filtered_texts else ([], [])
    
    # Check if Ollama-only mode is enabled via environment
    if os.getenv('USE_OLLAMA', 'false').lower() == 'true':
        ollama_only = True
    
    embeddings_result = [None] * len(texts)
    
    # Try Ollama batch embedding
    if prefer_ollama or ollama_only:
        try:
            logger.debug(f"Attempting Ollama batch embedding for {len(valid_texts)} texts...")
            batch_embeddings = local_ollama_embed_batch(list(valid_texts))
            logger.debug(f"Ollama batch embedding successful, {len(batch_embeddings)} embeddings generated")
            
            # Map back to original indices
            for idx, embedding in zip(indices, batch_embeddings):
                embeddings_result[idx] = embedding
            
            return embeddings_result
        except Exception as e:
            if ollama_only:
                logger.error(f"Ollama-only mode: batch embedding failed: {e}")
                return embeddings_result
            logger.warning(f"Ollama batch embedding failed: {e}, falling back to individual calls...")
    
    # Fallback: try individual embeddings (slower but more reliable)
    for idx, text in zip(indices, valid_texts):
        embeddings_result[idx] = generate_embedding(text, prefer_ollama=prefer_ollama, ollama_only=ollama_only)
    
    return embeddings_result

def generate_case_level_embedding(title: str, summary: str = "") -> Optional[List[float]]:
    """
    Generate case-level embedding from title and summary.
    
    Args:
        title: Case title
        summary: Case summary (optional)
        
    Returns:
        Embedding vector for the entire case
    """
    # Combine title and summary for case-level embedding
    case_text = title
    if summary and summary.strip():
        case_text = f"{title}\n\n{summary}"
    
    logger.info(f"Generating case-level embedding for: {title[:50]}...")
    embedding = generate_embedding(case_text, prefer_ollama=True)
    
    if embedding:
        logger.info(f"✅ Case-level embedding generated (dimension: {len(embedding)})")
    else:
        logger.error("❌ Case-level embedding failed")
    
    return embedding

def generate_chunk_embeddings(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate embeddings for a list of text chunks.
    
    Args:
        chunks: List of chunk dictionaries with 'chunk_text' key
        
    Returns:
        List of chunks with 'embedding' added to each
    """
    logger.info(f"Generating embeddings for {len(chunks)} chunks...")
    
    enhanced_chunks = []
    embedding_model = os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
    embedding_timestamp = datetime.now()
    
    for i, chunk in enumerate(chunks):
        chunk_text = chunk.get('chunk_text', '')
        if not chunk_text:
            logger.warning(f"Chunk {i} has no text, skipping embedding")
            enhanced_chunk = chunk.copy()
            enhanced_chunk['embedding'] = None
            enhanced_chunk['embedding_model'] = None
            enhanced_chunk['embedding_created_at'] = None
            enhanced_chunks.append(enhanced_chunk)
            continue
        
        logger.debug(f"Generating embedding for chunk {i+1}/{len(chunks)}: {chunk_text[:50]}...")
        embedding = generate_embedding(chunk_text, prefer_ollama=True)
        
        # Add embedding info to chunk
        enhanced_chunk = chunk.copy()
        enhanced_chunk['embedding'] = embedding
        enhanced_chunk['embedding_model'] = embedding_model if embedding else None
        enhanced_chunk['embedding_created_at'] = embedding_timestamp if embedding else None
        enhanced_chunks.append(enhanced_chunk)
        
        if embedding:
            logger.debug(f"✅ Chunk {i+1} embedding successful (dimension: {len(embedding)})")
        else:
            logger.warning(f"❌ Chunk {i+1} embedding failed")
    
    successful_embeddings = sum(1 for chunk in enhanced_chunks if chunk.get('embedding'))
    logger.info(f"✅ Generated {successful_embeddings}/{len(chunks)} chunk embeddings successfully")
    
    return enhanced_chunks

def get_embedding_metadata() -> Dict[str, Any]:
    """Get metadata about the embedding model being used"""
    return {
        'embedding_model': os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large"),
        'embedding_created_at': datetime.now(),
        'provider': 'ollama',
        'dimension': 1024
    }

# Test function to verify embedding service
def test_embedding_service():
    """Test the embedding service with sample text"""
    print("🧪 Testing Embedding Service...")
    
    # Test case-level embedding
    test_title = "In re Marriage of Derrick Badgley and Michelle Elise Pappas"
    test_summary = "Appeal regarding property characterization in dissolution proceeding"
    
    case_embedding = generate_case_level_embedding(test_title, test_summary)
    if case_embedding:
        print(f"✅ Case embedding: dimension={len(case_embedding)}, first 3 values: {case_embedding[:3]}")
    else:
        print("❌ Case embedding failed")
    
    # Test chunk embeddings
    test_chunks = [
        {'chunk_text': 'The parties were in a committed intimate relationship and lived together.'},
        {'chunk_text': 'The trial court applied Washington law to characterize the property.'},
        {'chunk_text': 'Court of Appeals affirmed the trial court decision.'}
    ]
    
    enhanced_chunks = generate_chunk_embeddings(test_chunks)
    successful_chunks = sum(1 for chunk in enhanced_chunks if chunk.get('embedding'))
    print(f"✅ Chunk embeddings: {successful_chunks}/{len(test_chunks)} successful")
    
    if enhanced_chunks and enhanced_chunks[0].get('embedding'):
        first_embedding = enhanced_chunks[0]['embedding']
        print(f"   First chunk embedding: dimension={len(first_embedding)}, first 3 values: {first_embedding[:3]}")
    
    print("🎉 Embedding service test complete!")

if __name__ == "__main__":
    test_embedding_service()