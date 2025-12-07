"""
Configuration for the Legal Case Pipeline
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load .env file
load_dotenv()


@dataclass
class PipelineConfig:
    """Configuration settings for the pipeline."""
    
    # Database
    database_url: str = ""
    
    # LlamaParse (PDF extraction)
    llama_cloud_api_key: Optional[str] = None
    
    # Ollama (LLM extraction)
    ollama_base_url: str = "https://ollama.legaldb.ai"
    ollama_model: str = "qwen:32b"
    ollama_embedding_model: str = "mxbai-embed-large"
    
    # Processing settings
    max_text_chars: int = 30000      # Max chars to send to LLM
    llm_timeout: int = 300           # LLM request timeout in seconds
    
    @classmethod
    def from_env(cls) -> 'PipelineConfig':
        """Load configuration from environment variables."""
        return cls(
            database_url=os.getenv(
                "DATABASE_URL", 
                "postgresql://postgres:postgres@localhost:5435/cases_llama3_3"
            ),
            llama_cloud_api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "https://ollama.legaldb.ai"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen:32b"),
            ollama_embedding_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large"),
            max_text_chars=int(os.getenv("MAX_TEXT_CHARS", "30000")),
            llm_timeout=int(os.getenv("LLM_TIMEOUT", "300")),
        )
    
    def validate(self) -> bool:
        """Validate that required settings are present."""
        if not self.database_url:
            raise ValueError("DATABASE_URL is required")
        return True


class Config:
    """
    Static configuration accessor for convenience.
    Loads from environment variables.
    """
    
    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5435/cases_llama3_3"
    )
    
    # Ollama
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.legaldb.ai")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen:32b")
    OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
    
    # LlamaParse
    LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")
    
    @classmethod
    def get_database_url(cls) -> str:
        """Get database URL from environment."""
        return cls.DATABASE_URL
    
    @classmethod
    def reload(cls):
        """Reload configuration from environment."""
        load_dotenv()
        cls.DATABASE_URL = os.getenv(
            "DATABASE_URL", 
            "postgresql://postgres:postgres@localhost:5435/cases_llama3_3"
        )
        cls.OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.legaldb.ai")
        cls.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen:32b")
        cls.OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
        cls.LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")

