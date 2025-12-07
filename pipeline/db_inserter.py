"""
Database Inserter - Clean SQL insertion for extracted cases
Maps ExtractedCase to the database schema.

Integrates with RAG processor for full indexing pipeline.
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import psycopg2

from .models import ExtractedCase, Party, Attorney, Judge, Citation, Statute, Issue
from .dimension_service import DimensionService

logger = logging.getLogger(__name__)


def generate_embedding(text: str, model: str = None) -> Optional[List[float]]:
    """
    Generate embedding using Ollama.
    Returns 1024-dim vector for mxbai-embed-large.
    """
    try:
        try:
            from langchain_ollama import OllamaEmbeddings
        except ImportError:
            from langchain_community.embeddings import OllamaEmbeddings
        
        ollama_model = model or os.getenv("OLLAMA_EMBED_MODEL", "mxbai-embed-large")
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        embeddings = OllamaEmbeddings(model=ollama_model, base_url=ollama_base_url)
        return embeddings.embed_query(text)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None


class DatabaseInserter:
    """
    Insert extracted case data into PostgreSQL database.
    Uses simple, direct SQL - no ORM complexity.
    
    Integrates with DimensionService for FK resolution and
    optionally with RAGProcessor for full indexing.
    """
    
    def __init__(self, db_engine: Engine, enable_rag: bool = True):
        """
        Initialize with database engine.
        
        Args:
            db_engine: SQLAlchemy engine instance
            enable_rag: Whether to enable RAG processing
        """
        self.db = db_engine
        self.enable_rag = enable_rag
        self._dimension_service = None
        self._rag_processor = None
    
    @classmethod
    def from_url(cls, database_url: str, enable_rag: bool = True) -> 'DatabaseInserter':
        """
        Create inserter from database URL.
        
        Args:
            database_url: PostgreSQL connection string
            enable_rag: Whether to enable RAG processing
        """
        engine = create_engine(database_url)
        return cls(engine, enable_rag=enable_rag)
    
    def _get_psycopg2_connection(self):
        """Get a psycopg2 connection from SQLAlchemy URL."""
        url = self.db.url
        return psycopg2.connect(
            host=url.host,
            port=url.port or 5432,
            database=url.database,
            user=url.username,
            password=url.password
        )
    
    def _get_dimension_service(self, conn) -> DimensionService:
        """Get or create dimension service."""
        if self._dimension_service is None:
            # DimensionService uses SQLAlchemy Engine, not psycopg2
            self._dimension_service = DimensionService(self.db)
        return self._dimension_service
    
    def configure_rag(
        self,
        chunk_embedding_mode: str = "all",
        phrase_filter_mode: str = "strict"
    ):
        """
        Configure RAG processor options.
        
        Args:
            chunk_embedding_mode: "all", "important", or "none"
            phrase_filter_mode: "strict" or "relaxed"
        """
        from .rag_processor import create_rag_processor
        
        pg_conn = self._get_psycopg2_connection()
        self._rag_processor = create_rag_processor(
            pg_conn,
            chunk_embedding_mode=chunk_embedding_mode,
            phrase_filter_mode=phrase_filter_mode
        )
    
    def insert_case(self, case: ExtractedCase) -> Optional[int]:
        """
        Insert a complete case with all related entities.
        Optionally runs RAG processing for chunks, sentences, words, phrases.
        
        Args:
            case: ExtractedCase object with all data
            
        Returns:
            case_id if successful, None if failed
        """
        try:
            with self.db.connect() as conn:
                trans = conn.begin()
                
                try:
                    # 1. Insert main case record
                    case_id = self._insert_case_record(conn, case)
                    logger.info(f"Inserted case with ID: {case_id}")
                    
                    # 2. Insert parties
                    for party in case.parties:
                        self._insert_party(conn, case_id, party)
                    logger.info(f"Inserted {len(case.parties)} parties")
                    
                    # 3. Insert attorneys
                    for attorney in case.attorneys:
                        self._insert_attorney(conn, case_id, attorney)
                    logger.info(f"Inserted {len(case.attorneys)} attorneys")
                    
                    # 4. Insert judges
                    for judge in case.judges:
                        self._insert_judge(conn, case_id, judge)
                    logger.info(f"Inserted {len(case.judges)} judges")
                    
                    # 5. Insert citations
                    for citation in case.citations:
                        self._insert_citation(conn, case_id, citation)
                    logger.info(f"Inserted {len(case.citations)} citations")
                    
                    # 6. Insert statutes
                    for statute in case.statutes:
                        self._insert_statute(conn, case_id, statute)
                    logger.info(f"Inserted {len(case.statutes)} statutes")
                    
                    # 7. Insert issues
                    for issue in case.issues:
                        self._insert_issue(conn, case_id, issue)
                    logger.info(f"Inserted {len(case.issues)} issues")
                    
                    trans.commit()
                    logger.info(f"Successfully committed case {case_id}")
                    
                    # 8. Run RAG processing if enabled
                    if self.enable_rag and case.full_text:
                        self._run_rag_processing(case_id, case)
                    
                    return case_id
                    
                except Exception as e:
                    trans.rollback()
                    logger.error(f"Insert failed, rolling back: {e}")
                    raise
                    
        except Exception as e:
            logger.error(f"Database error: {e}")
            return None
    
    def _run_rag_processing(self, case_id: int, case: ExtractedCase):
        """
        Run RAG processing for a case.
        Creates chunks, sentences, words, phrases, and embeddings.
        """
        try:
            # Lazy-load RAG processor with default settings
            if self._rag_processor is None:
                from .rag_processor import create_rag_processor
                pg_conn = self._get_psycopg2_connection()
                self._rag_processor = create_rag_processor(pg_conn)
            
            # Process the case
            result = self._rag_processor.process_case_sync(
                case_id,
                case.full_text,
                metadata=None  # Could pass case.metadata if needed
            )
            
            logger.info(
                f"RAG processing for case {case_id}: "
                f"{result.chunks_created} chunks, {result.sentences_created} sentences, "
                f"{result.words_indexed} words, {result.phrases_extracted} phrases, "
                f"{result.embeddings_generated} embeddings"
            )
            
            if result.errors:
                for err in result.errors:
                    logger.warning(f"RAG processing error: {err}")
                    
        except Exception as e:
            logger.error(f"RAG processing failed for case {case_id}: {e}")
            # Don't fail the whole insert if RAG fails
    
    def _insert_case_record(self, conn, case: ExtractedCase) -> int:
        """Insert main case record and return case_id."""
        
        meta = case.metadata
        
        # Generate embedding for full text
        full_embedding = None
        if case.full_text and len(case.full_text) > 100:
            # Use summary + first part of text for embedding (more semantic)
            embed_text = f"{case.summary}\n\n{case.full_text[:4000]}"
            logger.info("Generating full_embedding...")
            full_embedding = generate_embedding(embed_text)
            if full_embedding:
                logger.info(f"Generated {len(full_embedding)}-dim embedding")
        
        # Use DimensionService for all FK resolution
        dim_service = self._get_dimension_service(conn)
        dimension_ids = dim_service.resolve_all_dimensions(
            case_type=case.case_type,
            opinion_type=meta.opinion_type,
            court_level=meta.court_level,
            division=meta.division,
            county=case.county
        )
        
        query = text("""
            INSERT INTO cases (
                case_file_id, title, court_level, court, district, county,
                docket_number, source_docket_number, trial_judge,
                appeal_published_date, published,
                summary, full_text, full_embedding,
                source_url, case_info_url,
                overall_case_outcome, appeal_outcome,
                winner_legal_role, winner_personal_role,
                opinion_type, publication_status, 
                decision_year, decision_month,
                case_type, source_file, source_file_path,
                court_id, case_type_id, stage_type_id,
                extraction_timestamp, processing_status,
                created_at, updated_at
            ) VALUES (
                :case_file_id, :title, :court_level, :court, :district, :county,
                :docket_number, :source_docket_number, :trial_judge,
                :appeal_published_date, :published,
                :summary, :full_text, :full_embedding,
                :source_url, :case_info_url,
                :overall_case_outcome, :appeal_outcome,
                :winner_legal_role, :winner_personal_role,
                :opinion_type, :publication_status,
                :decision_year, :decision_month,
                :case_type, :source_file, :source_file_path,
                :court_id, :case_type_id, :stage_type_id,
                :extraction_timestamp, :processing_status,
                :created_at, :updated_at
            )
            RETURNING case_id
        """)
        
        now = datetime.now()
        
        # Determine published boolean
        published = 'published' in (meta.publication_status or '').lower()
        
        # Build court name
        court = None
        if meta.court_level == 'Supreme':
            court = 'Washington State Supreme Court'
        elif meta.court_level == 'Appeals':
            division = meta.division or ''
            court = f'Washington Court of Appeals Division {division}'.strip()
        
        # Format docket number
        docket = meta.case_number
        if meta.division:
            docket = f"{meta.case_number}-{meta.division}"
        
        params = {
            'case_file_id': meta.case_number or None,
            'title': meta.case_title or 'Unknown',
            'court_level': meta.court_level or None,
            'court': court,
            'district': f"Division {meta.division}" if meta.division else None,
            'county': case.county,
            'docket_number': docket,
            'source_docket_number': case.source_docket_number,
            'trial_judge': case.trial_judge,
            'appeal_published_date': meta.file_date,
            'published': published,
            'summary': case.summary or None,
            'full_text': case.full_text,
            'full_embedding': full_embedding,
            'source_url': meta.pdf_url or None,
            'case_info_url': meta.case_info_url or None,
            'overall_case_outcome': case.appeal_outcome,
            'appeal_outcome': case.appeal_outcome,
            'winner_legal_role': case.winner_legal_role,
            'winner_personal_role': case.winner_personal_role,
            'opinion_type': meta.opinion_type or None,
            'publication_status': meta.publication_status or 'Published',
            'decision_year': meta.year,
            'decision_month': meta.month or None,
            'case_type': case.case_type or None,
            'source_file': meta.pdf_filename or None,
            'source_file_path': case.source_file_path,
            'court_id': dimension_ids.get('court_id'),
            'case_type_id': dimension_ids.get('case_type_id'),
            'stage_type_id': dimension_ids.get('stage_type_id'),
            'extraction_timestamp': case.extraction_timestamp or now,
            'processing_status': 'ai_processed' if case.extraction_successful else 'failed',
            'created_at': now,
            'updated_at': now,
        }
        
        result = conn.execute(query, params)
        row = result.fetchone()
        return row.case_id
    
    def _get_or_create_court_id(self, conn, case: ExtractedCase, meta) -> Optional[int]:
        """
        Get or create court_id from courts_dim.
        
        Args:
            conn: Database connection
            case: ExtractedCase object
            meta: CaseMetadata object
            
        Returns:
            court_id from courts_dim, or None if not found/created
        """
        # Build court name
        court_name = None
        court_type = None
        level = meta.court_level
        district = f"Division {meta.division}" if meta.division else None
        
        if meta.court_level == 'Supreme':
            court_name = 'Washington State Supreme Court'
            court_type = 'Supreme Court'
        elif meta.court_level == 'Appeals':
            division = meta.division or ''
            court_name = f'Washington Court of Appeals Division {division}'.strip()
            court_type = 'Court of Appeals'
        
        if not court_name:
            return None
        
        # Try to find existing court
        get_court = text("SELECT court_id FROM courts_dim WHERE court = :court")
        result = conn.execute(get_court, {'court': court_name})
        row = result.fetchone()
        
        if row:
            return row.court_id
        
        # Create new court entry
        insert_court = text("""
            INSERT INTO courts_dim (court, level, jurisdiction, district, county, court_type)
            VALUES (:court, :level, :jurisdiction, :district, :county, :court_type)
            RETURNING court_id
        """)
        
        result = conn.execute(insert_court, {
            'court': court_name,
            'level': level,
            'jurisdiction': 'WA',
            'district': district,
            'county': case.county,
            'court_type': court_type,
        })
        
        new_row = result.fetchone()
        logger.info(f"Created new court in courts_dim: {court_name} (ID: {new_row.court_id})")
        return new_row.court_id
    
    def _insert_party(self, conn, case_id: int, party: Party) -> int:
        """Insert a party record."""
        query = text("""
            INSERT INTO parties (case_id, name, legal_role, party_type, created_at)
            VALUES (:case_id, :name, :legal_role, :party_type, :created_at)
            RETURNING party_id
        """)
        
        result = conn.execute(query, {
            'case_id': case_id,
            'name': party.name,
            'legal_role': party.role,
            'party_type': party.party_type,
            'created_at': datetime.now(),
        })
        
        return result.fetchone().party_id
    
    def _insert_attorney(self, conn, case_id: int, attorney: Attorney) -> int:
        """Insert an attorney record."""
        query = text("""
            INSERT INTO attorneys (case_id, name, firm_name, representing, created_at)
            VALUES (:case_id, :name, :firm_name, :representing, :created_at)
            RETURNING attorney_id
        """)
        
        result = conn.execute(query, {
            'case_id': case_id,
            'name': attorney.name,
            'firm_name': attorney.firm_name,
            'representing': attorney.representing,
            'created_at': datetime.now(),
        })
        
        return result.fetchone().attorney_id
    
    def _insert_judge(self, conn, case_id: int, judge: Judge) -> int:
        """
        Insert a judge record (uses normalized judges table).
        Creates judge if not exists, then links to case.
        """
        # First, get or create the judge in judges table
        get_judge = text("SELECT judge_id FROM judges WHERE name = :name")
        result = conn.execute(get_judge, {'name': judge.name})
        row = result.fetchone()
        
        if row:
            judge_id = row.judge_id
        else:
            # Create new judge
            insert_judge = text("""
                INSERT INTO judges (name) VALUES (:name) RETURNING judge_id
            """)
            result = conn.execute(insert_judge, {'name': judge.name})
            judge_id = result.fetchone().judge_id
        
        # Link judge to case
        link_query = text("""
            INSERT INTO case_judges (case_id, judge_id, role, created_at)
            VALUES (:case_id, :judge_id, :role, :created_at)
            RETURNING id
        """)
        
        result = conn.execute(link_query, {
            'case_id': case_id,
            'judge_id': judge_id,
            'role': judge.role,
            'created_at': datetime.now(),
        })
        
        return result.fetchone().id
    
    def _insert_citation(self, conn, case_id: int, citation: Citation) -> int:
        """Insert a case citation edge."""
        query = text("""
            INSERT INTO citation_edges (
                source_case_id, target_case_citation, relationship, created_at
            ) VALUES (
                :source_case_id, :target_case_citation, :relationship, :created_at
            )
            ON CONFLICT (source_case_id, target_case_citation, COALESCE(pin_cite, '')) DO NOTHING
            RETURNING citation_id
        """)
        
        result = conn.execute(query, {
            'source_case_id': case_id,
            'target_case_citation': citation.full_citation,
            'relationship': citation.relationship or 'cited',
            'created_at': datetime.now(),
        })
        
        row = result.fetchone()
        return row.citation_id if row else 0
    
    def _insert_statute(self, conn, case_id: int, statute: Statute) -> int:
        """Insert a statute citation."""
        query = text("""
            INSERT INTO statute_citations (case_id, raw_text, created_at)
            VALUES (:case_id, :raw_text, :created_at)
            RETURNING id
        """)
        
        result = conn.execute(query, {
            'case_id': case_id,
            'raw_text': statute.citation,
            'created_at': datetime.now(),
        })
        
        return result.fetchone().id
    
    def _insert_issue(self, conn, case_id: int, issue: Issue) -> int:
        """Insert an issue/decision record."""
        query = text("""
            INSERT INTO issues_decisions (
                case_id, category, subcategory, issue_summary,
                appeal_outcome, winner_legal_role,
                created_at, updated_at
            ) VALUES (
                :case_id, :category, :subcategory, :issue_summary,
                :appeal_outcome, :winner_legal_role,
                :created_at, :updated_at
            )
            RETURNING issue_id
        """)
        
        now = datetime.now()
        
        result = conn.execute(query, {
            'case_id': case_id,
            'category': issue.category or 'Other',
            'subcategory': issue.subcategory or 'General',
            'issue_summary': issue.summary,
            'appeal_outcome': issue.outcome,
            'winner_legal_role': issue.winner,
            'created_at': now,
            'updated_at': now,
        })
        
        return result.fetchone().issue_id
    
    def insert_batch(self, cases: List[ExtractedCase]) -> Dict[str, int]:
        """
        Insert a batch of cases.
        
        Args:
            cases: List of ExtractedCase objects
            
        Returns:
            Dictionary with success/failure counts
        """
        results = {'success': 0, 'failed': 0, 'case_ids': []}
        
        for case in cases:
            case_id = self.insert_case(case)
            if case_id:
                results['success'] += 1
                results['case_ids'].append(case_id)
            else:
                results['failed'] += 1
        
        logger.info(f"Batch insert complete: {results['success']} success, {results['failed']} failed")
        return results
    
    def get_case_count(self) -> int:
        """Get total number of cases in database."""
        with self.db.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM cases"))
            return result.scalar()
