"""
Database Insertion Service
Clean and reliable database insertion for all legal case entities.
Enhanced for new schema with document management and dimension tables.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.engine import Engine
from .models import LegalCaseExtraction, PublicationStatus
from .dimension_service import DimensionService

logger = logging.getLogger(__name__)

class DatabaseInserter:
    """Clean and reliable database insertion using sequential IDs"""
    
    def __init__(self, db_engine: Engine):
        self.db = db_engine
        self.dimension_service = DimensionService(db_engine)
    
    def insert_complete_case(self, extracted_data: LegalCaseExtraction, metadata: Dict[str, Any] = None, 
                           source_file_info: Dict[str, str] = None) -> Optional[int]:
        """
        Insert complete case data into all tables with sequential ID assignment
        
        Args:
            extracted_data: Complete extracted case data (content only, no IDs)
            metadata: Original metadata from batch processor
            source_file_info: Source file information
            
        Returns:
            case_id if successful, None if failed
        """
        try:
            with self.db.connect() as conn:
                # Start transaction
                trans = conn.begin()
                
                try:
                    # 1. Resolve dimension table IDs from metadata
                    dimension_ids = {}
                    if metadata:
                        dimension_ids = self.dimension_service.resolve_metadata_to_ids(metadata)
                        logger.info(f"🔍 Resolved dimension IDs: {dimension_ids}")
                    
                    # 2. Insert case with dimension references - DB auto-assigns case_id
                    case_id = self._insert_case(conn, extracted_data.case, dimension_ids, source_file_info)
                    logger.info(f"📁 Inserted case with ID: {case_id}")
                    
                    # 2. Insert parties - DB auto-assigns party_id for each
                    party_ids = []
                    for party in extracted_data.parties:
                        party_id = self._insert_party(conn, party, case_id)
                        party_ids.append(party_id)
                        logger.info(f"👥 Inserted party: {party.name} (ID: {party_id})")
                    
                    # 3. Insert attorneys - DB auto-assigns attorney_id for each
                    attorney_ids = []
                    for attorney in extracted_data.attorneys:
                        attorney_id = self._insert_attorney(conn, attorney, case_id)
                        attorney_ids.append(attorney_id)
                        logger.info(f"⚖️ Inserted attorney: {attorney.name} (ID: {attorney_id})")
                    
                    # 4. Insert judges - DB auto-assigns judge_id for each
                    for judge in extracted_data.appeals_judges:
                        self._insert_judge(conn, judge, case_id)
                        logger.info(f"👨‍⚖️ Inserted judge: {judge.judge_name}")
                    
                    # 5. Insert issues - DB auto-assigns issue_id for each
                    issue_id_mapping = {}
                    for i, issue in enumerate(extracted_data.issues_decisions):
                        issue_id = self._insert_issue(conn, issue, case_id)
                        issue_id_mapping[i] = issue_id  # Map by position in array
                        logger.info(f"📋 Inserted issue: {issue.issue_summary[:50]}... (ID: {issue_id})")
                    
                    # 6. Insert arguments - link to issues by matching content/position
                    for argument in extracted_data.arguments:
                        # Since AI doesn't provide issue_id anymore, we need to link arguments to issues
                        # For now, we'll link all arguments to the first issue
                        # TODO: Implement smarter issue-argument matching
                        related_issue_id = list(issue_id_mapping.values())[0] if issue_id_mapping else None
                        if related_issue_id:
                            argument_id = self._insert_argument(conn, argument, case_id, related_issue_id)
                            logger.info(f"💬 Inserted argument: {argument.side} (ID: {argument_id})")
                    
                    # 7. Insert precedents (citations)
                    for precedent in extracted_data.precedents:
                        citation_id = self._insert_citation(conn, precedent, case_id)
                        logger.info(f"📖 Inserted citation: {precedent.citation} (ID: {citation_id})")
                    
                    # Commit transaction
                    trans.commit()
                    
                    logger.info(f"✅ Successfully inserted complete case with ID: {case_id}")
                    return case_id
                    
                except Exception as e:
                    trans.rollback()
                    logger.error(f"❌ Failed to insert case: {e}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            return None
    
    def _insert_case(self, conn, case_data, dimension_ids: Dict[str, Optional[int]] = None, 
                    source_file_info: Dict[str, str] = None) -> int:
        """Insert case record and return the auto-generated case_id"""
        # Convert published enum to boolean
        published_bool = case_data.published == PublicationStatus.PUBLISHED
        
        # Parse dates
        trial_start_date = self._parse_date(getattr(case_data, 'trial_start_date', None))
        trial_end_date = self._parse_date(getattr(case_data, 'trial_end_date', None))
        trial_published_date = self._parse_date(getattr(case_data, 'trial_published_date', None))
        appeal_start_date = self._parse_date(getattr(case_data, 'appeal_start_date', None))
        appeal_end_date = self._parse_date(getattr(case_data, 'appeal_end_date', None))
        appeal_published_date = self._parse_date(getattr(case_data, 'appeal_published_date', None))
        oral_arg_date = self._parse_date(case_data.oral_argument_date)
        
        query = text("""
            INSERT INTO cases (
                case_file_id, title, court_level, court, district, county,
                docket_number, source_docket_number, trial_judge,
                trial_start_date, trial_end_date, trial_published_date,
                appeal_start_date, appeal_end_date, appeal_published_date,
                oral_argument_date, published,
                summary, full_text, source_url, overall_case_outcome, 
                case_type_id, stage_type_id, court_id, parent_case_id,
                case_type, source_file, source_file_path, extraction_timestamp,
                winner_legal_role, winner_personal_role, appeal_outcome,
                created_at, updated_at
            ) VALUES (
                :case_file_id, :title, :court_level, :court, :district, :county,
                :docket_number, :source_docket_number, :trial_judge,
                :trial_start_date, :trial_end_date, :trial_published_date,
                :appeal_start_date, :appeal_end_date, :appeal_published_date,
                :oral_argument_date, :published,
                :summary, :full_text, :source_url, :overall_case_outcome,
                :case_type_id, :stage_type_id, :court_id, :parent_case_id,
                :case_type, :source_file, :source_file_path, :extraction_timestamp,
                :winner_legal_role, :winner_personal_role, :appeal_outcome,
                :created_at, :updated_at
            )
            RETURNING case_id
        """)
        
        now = datetime.now()
        dimension_ids = dimension_ids or {}
        
        result = conn.execute(query, {
            'case_file_id': getattr(case_data, 'case_file_id', None),
            'title': case_data.title,
            'court_level': case_data.court_level.value,
            'court': case_data.court,
            'district': case_data.district.value if case_data.district else None,
            'county': case_data.county,
            'docket_number': case_data.docket_number,
            'source_docket_number': case_data.source_docket_number,
            'trial_judge': case_data.trial_judge,
            'trial_start_date': trial_start_date,
            'trial_end_date': trial_end_date,
            'trial_published_date': trial_published_date,
            'appeal_start_date': appeal_start_date,
            'appeal_end_date': appeal_end_date,
            'appeal_published_date': appeal_published_date,
            'oral_argument_date': oral_arg_date,
            'published': published_bool,
            'summary': case_data.summary,
            'full_text': '',  # Will be populated later during chunking
            'source_url': None,  # Not extracting source URLs for now
            'overall_case_outcome': case_data.overall_case_outcome.value if case_data.overall_case_outcome else None,
            'case_type_id': dimension_ids.get('case_type_id'),
            'stage_type_id': dimension_ids.get('stage_type_id'),
            'court_id': dimension_ids.get('court_id'),
            'parent_case_id': None,  # Not used in batch processing currently
            'case_type': getattr(case_data, 'case_type', 'divorce'),  # Legacy field
            'source_file': source_file_info.get('filename') if source_file_info else None,
            'source_file_path': source_file_info.get('file_path') if source_file_info else None,
            'extraction_timestamp': now,
            'winner_legal_role': case_data.winner_legal_role.value if case_data.winner_legal_role else None,
            'winner_personal_role': case_data.winner_personal_role.value if case_data.winner_personal_role else None,
            'appeal_outcome': case_data.appeal_outcome.value if case_data.appeal_outcome else None,
            'created_at': now,
            'updated_at': now
        })
        
        case_id = result.fetchone().case_id
        return case_id
    
    def create_document_record(self, case_id: int, source_file_info: Dict[str, str], 
                              dimension_ids: Dict[str, Optional[int]]) -> Optional[int]:
        """Create a document record for the PDF and return document_id"""
        try:
            with self.db.connect() as conn:
                query = text("""
                    INSERT INTO documents (
                        case_id, stage_type_id, document_type_id, title, 
                        source_url, local_path, file_size, page_count, 
                        processing_status, created_at, updated_at
                    ) VALUES (
                        :case_id, :stage_type_id, :document_type_id, :title,
                        :source_url, :local_path, :file_size, :page_count,
                        :processing_status, :created_at, :updated_at
                    )
                    RETURNING document_id
                """)
                
                now = datetime.now()
                
                result = conn.execute(query, {
                    'case_id': case_id,
                    'stage_type_id': dimension_ids.get('stage_type_id'),
                    'document_type_id': dimension_ids.get('document_type_id'),
                    'title': source_file_info.get('filename', 'Unknown Document'),
                    'source_url': source_file_info.get('source_url'),
                    'local_path': source_file_info.get('file_path'),
                    'file_size': source_file_info.get('file_size'),
                    'page_count': source_file_info.get('page_count'),
                    'processing_status': 'completed',
                    'created_at': now,
                    'updated_at': now
                })
                
                document_id = result.fetchone().document_id
                conn.commit()
                
                logger.info(f"📄 Created document record with ID: {document_id}")
                return document_id
                
        except Exception as e:
            logger.error(f"Failed to create document record: {e}")
            return None
    
    def _insert_party(self, conn, party_data, case_id: int) -> int:
        """Insert party record and return the auto-generated party_id"""
        query = text("""
            INSERT INTO parties (
                case_id, name, legal_role, personal_role, party_type, created_at
            ) VALUES (
                :case_id, :name, :legal_role, :personal_role, :party_type, :created_at
            )
            RETURNING party_id
        """)
        
        result = conn.execute(query, {
            'case_id': case_id,
            'name': party_data.name,
            'legal_role': party_data.legal_role.value,
            'personal_role': party_data.personal_role.value if party_data.personal_role else None,
            'party_type': 'Individual',  # Default for family law cases
            'created_at': datetime.now()
        })
        
        party_id = result.fetchone().party_id
        return party_id
    
    def _insert_attorney(self, conn, attorney_data, case_id: int) -> int:
        """Insert attorney record and return the auto-generated attorney_id"""
        query = text("""
            INSERT INTO attorneys (
                case_id, name, firm_name, firm_address, representing, attorney_type, created_at
            ) VALUES (
                :case_id, :name, :firm_name, :firm_address, :representing, :attorney_type, :created_at
            )
            RETURNING attorney_id
        """)
        
        result = conn.execute(query, {
            'case_id': case_id,
            'name': attorney_data.name,
            'firm_name': attorney_data.firm_name,
            'firm_address': attorney_data.firm_address,
            'representing': attorney_data.representing.value,
            'attorney_type': attorney_data.attorney_type.value,
            'created_at': datetime.now()
        })
        
        attorney_id = result.fetchone().attorney_id
        return attorney_id
    
    def _insert_judge(self, conn, judge_data, case_id: int) -> None:
        """Insert judge with normalized approach"""
        # First, insert or get judge record
        judge_query = text("""
            INSERT INTO judges (name) VALUES (:name)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING judge_id
        """)
        
        result = conn.execute(judge_query, {'name': judge_data.judge_name})
        judge_row = result.fetchone()
        if not judge_row:
            # Get existing judge_id
            select_query = text("SELECT judge_id FROM judges WHERE name = :name")
            result = conn.execute(select_query, {'name': judge_data.judge_name})
            judge_row = result.fetchone()
        
        judge_id = judge_row.judge_id
        
        # Insert case-judge relationship
        case_judge_query = text("""
            INSERT INTO case_judges (case_id, judge_id, role, court, created_at)
            VALUES (:case_id, :judge_id, :role, :court, :created_at)
            ON CONFLICT (case_id, judge_id, role) DO UPDATE SET
                court = EXCLUDED.court
        """)
        
        # Map role names to database format
        role_map = {
            'Authored by': 'Author',
            'Concurring': 'Concurring', 
            'Dissenting': 'Dissenting',
            'Joining': 'Panelist'
        }
        
        conn.execute(case_judge_query, {
            'case_id': case_id,
            'judge_id': judge_id,
            'role': role_map.get(judge_data.role.value, judge_data.role.value),
            'court': 'Appeals Court',  # Default for family law cases
            'created_at': datetime.now()
        })
    
    def _insert_issue(self, conn, issue_data, case_id: int) -> int:
        """Insert issue_decision record and return the auto-generated issue_id"""
        query = text("""
            INSERT INTO issues_decisions (
                case_id, category, subcategory, rcw_reference, keywords,
                issue_summary, decision_stage, decision_summary, appeal_outcome,
                winner_legal_role, winner_personal_role, created_at, updated_at
            ) VALUES (
                :case_id, :category, :subcategory, :rcw_reference, :keywords,
                :issue_summary, :decision_stage, :decision_summary, :appeal_outcome,
                :winner_legal_role, :winner_personal_role, :created_at, :updated_at
            )
            RETURNING issue_id
        """)
        
        now = datetime.now()
        result = conn.execute(query, {
            'case_id': case_id,
            'category': issue_data.category.value,
            'subcategory': issue_data.subcategory,
            'rcw_reference': issue_data.rcw_reference,
            'keywords': issue_data.keywords,
            'issue_summary': issue_data.issue_summary,
            'decision_stage': issue_data.decision_stage.value if issue_data.decision_stage else None,
            'decision_summary': issue_data.decision_summary,
            'appeal_outcome': issue_data.appeal_outcome.value if issue_data.appeal_outcome else None,
            'winner_legal_role': issue_data.winner_legal_role.value if issue_data.winner_legal_role else None,
            'winner_personal_role': issue_data.winner_personal_role.value if issue_data.winner_personal_role else None,
            'created_at': now,
            'updated_at': now
        })
        
        issue_id = result.fetchone().issue_id
        return issue_id
    
    def _insert_argument(self, conn, argument_data, case_id: int, issue_id: int) -> int:
        """Insert argument record and return the auto-generated argument_id"""
        query = text("""
            INSERT INTO arguments (
                case_id, issue_id, side, argument_text, created_at, updated_at
            ) VALUES (
                :case_id, :issue_id, :side, :argument_text, :created_at, :updated_at
            )
            RETURNING argument_id
        """)
        
        now = datetime.now()
        result = conn.execute(query, {
            'case_id': case_id,
            'issue_id': issue_id,
            'side': argument_data.side.value,
            'argument_text': argument_data.argument_text,
            'created_at': now,
            'updated_at': now
        })
        
        argument_id = result.fetchone().argument_id
        return argument_id
    
    def _insert_citation(self, conn, precedent_data, case_id: int) -> int:
        """Insert citation edge record and return the auto-generated citation_id"""
        query = text("""
            INSERT INTO citation_edges (
                source_case_id, target_case_citation, relationship, importance, created_at
            ) VALUES (
                :source_case_id, :target_case_citation, :relationship, :importance, :created_at
            )
            RETURNING citation_id
        """)
        
        result = conn.execute(query, {
            'source_case_id': case_id,
            'target_case_citation': precedent_data.citation,
            'relationship': precedent_data.relationship.value,
            'importance': 'cited',  # Default importance
            'created_at': datetime.now()
        })
        
        citation_id = result.fetchone().citation_id
        return citation_id
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_str:
            return None
            
        try:
            # Try YYYY-MM-DD format first
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            try:
                # Try MM/DD/YYYY format
                return datetime.strptime(date_str, '%m/%d/%Y')
            except ValueError:
                try:
                    # Try MM-DD-YYYY format
                    return datetime.strptime(date_str, '%m-%d-%Y')
                except ValueError:
                    logger.warning(f"Could not parse date: {date_str}")
                    return None
    
    def insert_regex_extraction(self, regex_result, metadata: Dict[str, Any] = None,
                                 source_file_info: Dict[str, str] = None) -> Optional[int]:
        """
        Insert case data from regex extraction (fast, no LLM).
        
        Args:
            regex_result: RegexExtractionResult from regex_extractor
            metadata: Original metadata from CSV
            source_file_info: Source file information
            
        Returns:
            case_id if successful, None if failed
        """
        from .regex_extractor import RegexExtractionResult
        
        try:
            with self.db.connect() as conn:
                trans = conn.begin()
                
                try:
                    # 1. Resolve dimension table IDs from metadata
                    dimension_ids = {}
                    if metadata:
                        dimension_ids = self.dimension_service.resolve_metadata_to_ids(metadata)
                        logger.info(f"🔍 Resolved dimension IDs: {dimension_ids}")
                    
                    # 2. Insert case record
                    case_id = self._insert_case_from_regex(conn, regex_result, dimension_ids, source_file_info)
                    logger.info(f"📁 Inserted case with ID: {case_id}")
                    
                    # 3. Insert parties
                    for party in regex_result.parties:
                        self._insert_party_from_regex(conn, party, case_id)
                        logger.info(f"👥 Inserted party: {party.name}")
                    
                    # 4. Insert judges
                    for judge in regex_result.judges:
                        self._insert_judge_from_regex(conn, judge, case_id)
                        logger.info(f"👨‍⚖️ Inserted judge: {judge.name} ({judge.role})")
                    
                    # 5. Insert statute citations (RCW)
                    for statute in regex_result.statutes:
                        self._insert_statute_citation(conn, statute, case_id)
                    logger.info(f"📜 Inserted {len(regex_result.statutes)} statute citations")
                    
                    # 6. Insert case citations
                    for citation in regex_result.citations:
                        self._insert_case_citation(conn, citation, case_id)
                    logger.info(f"📖 Inserted {len(regex_result.citations)} case citations")
                    
                    trans.commit()
                    logger.info(f"✅ Successfully inserted case {case_id} via regex extraction")
                    return case_id
                    
                except Exception as e:
                    trans.rollback()
                    logger.error(f"❌ Failed to insert regex case: {e}")
                    import traceback
                    traceback.print_exc()
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            return None
    
    def _insert_case_from_regex(self, conn, regex_result, dimension_ids: Dict[str, Optional[int]],
                                source_file_info: Dict[str, str] = None) -> int:
        """Insert case from regex extraction result"""
        
        # Map court_level string to enum value
        court_level_map = {
            'supreme_court': 'supreme_court',
            'court_of_appeals': 'court_of_appeals',
            'unknown': 'unknown'
        }
        court_level = court_level_map.get(regex_result.court_level, 'unknown')
        
        # Map division
        division_map = {
            'division_one': 'division_one',
            'division_two': 'division_two', 
            'division_three': 'division_three',
            None: None
        }
        division = division_map.get(regex_result.division)
        
        # Map outcome
        outcome_map = {
            'affirmed': 'affirmed',
            'reversed': 'reversed',
            'remanded': 'remanded',
            'dismissed': 'dismissed',
            None: None
        }
        outcome = outcome_map.get(regex_result.appeal_outcome)
        
        query = text("""
            INSERT INTO cases (
                case_file_id, title, court_level, district, county,
                docket_number, appeal_published_date,
                published, source_url, overall_case_outcome, appeal_outcome,
                case_type_id, stage_type_id, court_id,
                source_file, source_file_path, extraction_timestamp,
                created_at, updated_at
            ) VALUES (
                :case_file_id, :title, :court_level, :district, :county,
                :docket_number, :appeal_published_date,
                :published, :source_url, :overall_case_outcome, :appeal_outcome,
                :case_type_id, :stage_type_id, :court_id,
                :source_file, :source_file_path, :extraction_timestamp,
                :created_at, :updated_at
            )
            RETURNING case_id
        """)
        
        now = datetime.now()
        dimension_ids = dimension_ids or {}
        
        result = conn.execute(query, {
            'case_file_id': regex_result.case_number,
            'title': regex_result.case_name,
            'court_level': court_level,
            'district': division,
            'county': regex_result.county,
            'docket_number': regex_result.case_number,
            'appeal_published_date': regex_result.decision_date,
            'published': regex_result.publication_status == 'published',
            'source_url': regex_result.pdf_url,
            'overall_case_outcome': outcome,
            'appeal_outcome': outcome,
            'case_type_id': dimension_ids.get('case_type_id'),
            'stage_type_id': dimension_ids.get('stage_type_id'),
            'court_id': dimension_ids.get('court_id'),
            'source_file': source_file_info.get('filename') if source_file_info else None,
            'source_file_path': source_file_info.get('file_path') if source_file_info else None,
            'extraction_timestamp': now,
            'created_at': now,
            'updated_at': now
        })
        
        case_id = result.fetchone().case_id
        return case_id
    
    def _insert_party_from_regex(self, conn, party, case_id: int) -> int:
        """Insert party from regex extraction"""
        # Map role to legal_role enum
        role_map = {
            'appellant': 'appellant',
            'respondent': 'respondent',
            'petitioner': 'petitioner',
            'appellee': 'respondent',
            'cross_appellant': 'cross_appellant',
        }
        legal_role = role_map.get(party.role, 'appellant')
        
        query = text("""
            INSERT INTO parties (case_id, name, legal_role, created_at)
            VALUES (:case_id, :name, :legal_role, :created_at)
            RETURNING party_id
        """)
        
        result = conn.execute(query, {
            'case_id': case_id,
            'name': party.name,
            'legal_role': legal_role,
            'created_at': datetime.now()
        })
        
        return result.fetchone().party_id
    
    def _insert_judge_from_regex(self, conn, judge, case_id: int) -> None:
        """Insert judge from regex extraction with normalized approach"""
        # First, insert or get judge record
        judge_query = text("""
            INSERT INTO judges (name) VALUES (:name)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING judge_id
        """)
        
        result = conn.execute(judge_query, {'name': judge.name})
        judge_row = result.fetchone()
        
        if not judge_row:
            select_query = text("SELECT judge_id FROM judges WHERE name = :name")
            result = conn.execute(select_query, {'name': judge.name})
            judge_row = result.fetchone()
        
        if judge_row:
            judge_id = judge_row.judge_id
            
            # Map regex role to database role
            role_map = {
                'author': 'authoring',
                'concurring': 'concurring',
                'dissenting': 'dissenting',
                'pro_tempore': 'pro_tempore',
                'author_pro_tempore': 'authoring',
                'concurring_pro_tempore': 'concurring',
            }
            judge_role = role_map.get(judge.role, 'authoring')
            
            # Insert into case_judges junction table
            case_judge_query = text("""
                INSERT INTO case_judges (case_id, judge_id, role)
                VALUES (:case_id, :judge_id, :role)
                ON CONFLICT (case_id, judge_id) DO NOTHING
            """)
            
            conn.execute(case_judge_query, {
                'case_id': case_id,
                'judge_id': judge_id,
                'role': judge_role
            })
    
    def _insert_statute_citation(self, conn, statute, case_id: int) -> None:
        """Insert RCW statute citation"""
        # First insert into statutes table (normalized)
        statute_query = text("""
            INSERT INTO statutes (statute_number, jurisdiction, title)
            VALUES (:statute_number, 'WA', :title)
            ON CONFLICT (statute_number) DO UPDATE SET statute_number = EXCLUDED.statute_number
            RETURNING statute_id
        """)
        
        result = conn.execute(statute_query, {
            'statute_number': statute.rcw_number,
            'title': statute.full_text
        })
        row = result.fetchone()
        
        if not row:
            select_query = text("SELECT statute_id FROM statutes WHERE statute_number = :num")
            result = conn.execute(select_query, {'num': statute.rcw_number})
            row = result.fetchone()
        
        if row:
            # Insert into statute_citations junction
            cite_query = text("""
                INSERT INTO statute_citations (case_id, statute_id, citation_text)
                VALUES (:case_id, :statute_id, :citation_text)
                ON CONFLICT DO NOTHING
            """)
            conn.execute(cite_query, {
                'case_id': case_id,
                'statute_id': row.statute_id,
                'citation_text': statute.full_text
            })
    
    def _insert_case_citation(self, conn, citation, case_id: int) -> None:
        """Insert case citation into citation_edges"""
        query = text("""
            INSERT INTO citation_edges (source_case_id, target_case_citation, relationship, importance, created_at)
            VALUES (:source_case_id, :target_case_citation, :relationship, :importance, :created_at)
            ON CONFLICT DO NOTHING
        """)
        
        conn.execute(query, {
            'source_case_id': case_id,
            'target_case_citation': citation.full_citation,
            'relationship': 'cited',
            'importance': 'cited',
            'created_at': datetime.now()
        })

    def get_case_stats(self, case_id: int) -> dict:
        """Get statistics for inserted case data"""
        with self.db.connect() as conn:
            query = text("""
                SELECT 
                    (SELECT COUNT(*) FROM parties WHERE case_id = :case_id) as parties,
                    (SELECT COUNT(*) FROM attorneys WHERE case_id = :case_id) as attorneys,
                    (SELECT COUNT(*) FROM case_judges WHERE case_id = :case_id) as judges,
                    (SELECT COUNT(*) FROM issues_decisions WHERE case_id = :case_id) as issues,
                    (SELECT COUNT(*) FROM arguments WHERE case_id = :case_id) as arguments,
                    (SELECT COUNT(*) FROM citation_edges WHERE source_case_id = :case_id) as citations
            """)
            
            result = conn.execute(query, {'case_id': case_id})
            row = result.fetchone()
            
            return {
                'parties': row.parties,
                'attorneys': row.attorneys,
                'judges': row.judges,
                'issues': row.issues,
                'arguments': row.arguments,
                'citations': row.citations
            }