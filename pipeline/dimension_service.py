"""
Dimension Service
Handles lookups and creation of dimension table records.
Maps metadata to dimension FKs (case_type_id, stage_type_id, document_type_id, court_id).
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DimensionService:
    """Service for managing dimension table lookups and creation."""
    
    # Mapping of case_type strings to normalized values
    CASE_TYPE_MAPPING = {
        'criminal': 'Criminal',
        'civil': 'Civil',
        'family': 'Family',
        'estate': 'Estate',
        'administrative': 'Administrative',
        'tort': 'Tort',
        'contract': 'Contract',
        'property': 'Property',
        'employment': 'Employment',
        'divorce': 'Divorce',
        'custody': 'Custody',
        'other': 'Other'
    }
    
    # Mapping of opinion_type to stage_type
    STAGE_TYPE_MAPPING = {
        'supreme court': ('Supreme Court', 1),
        'court of appeals': ('Court Of Appeals', 2),
        'superior court': ('Superior Court', 3),
        'district court': ('District Court', 4)
    }
    
    # Mapping of opinion_type to document_type
    DOCUMENT_TYPE_MAPPING = {
        'supreme court': 'Supreme Court Opinion',
        'court of appeals': 'Court of Appeals Opinion',
        'majority opinion': 'Majority Opinion',
        'concurring opinion': 'Concurring Opinion',
        'dissenting opinion': 'Dissenting Opinion',
        'court decision': 'Court Decision'
    }
    
    def __init__(self, db_engine: Engine):
        self.db = db_engine
        self._cache = {
            'case_types': {},
            'stage_types': {},
            'document_types': {},
            'courts': {}
        }
    
    def resolve_all_dimensions(
        self,
        case_type: Optional[str] = None,
        opinion_type: Optional[str] = None,
        court_level: Optional[str] = None,
        court_name: Optional[str] = None,
        division: Optional[str] = None,
        county: Optional[str] = None
    ) -> Dict[str, Optional[int]]:
        """
        Resolve all dimension IDs from case metadata.
        
        Args:
            case_type: Case type string (e.g., 'tort', 'criminal')
            opinion_type: Opinion type from metadata (e.g., 'Supreme Court')
            court_level: Court level (e.g., 'Supreme', 'Appeals')
            court_name: Full court name
            division: Division for Court of Appeals
            county: County name
            
        Returns:
            Dictionary with case_type_id, stage_type_id, document_type_id, court_id
        """
        return {
            'case_type_id': self.get_or_create_case_type(case_type) if case_type else None,
            'stage_type_id': self.get_or_create_stage_type(opinion_type, court_level),
            'document_type_id': self.get_or_create_document_type(opinion_type),
            'court_id': self.get_or_create_court(court_name, court_level, division, county)
        }
    
    def get_or_create_case_type(self, case_type: str, jurisdiction: str = "WA") -> Optional[int]:
        """Get or create case type and return ID."""
        if not case_type:
            return None
        
        # Normalize case type
        normalized = self.CASE_TYPE_MAPPING.get(case_type.lower(), case_type.title())
        
        # Check cache
        cache_key = f"{normalized}_{jurisdiction}"
        if cache_key in self._cache['case_types']:
            return self._cache['case_types'][cache_key]
        
        with self.db.connect() as conn:
            # Try to find existing
            query = text("""
                SELECT case_type_id FROM case_types 
                WHERE case_type = :case_type AND (jurisdiction = :jurisdiction OR jurisdiction IS NULL)
            """)
            result = conn.execute(query, {'case_type': normalized, 'jurisdiction': jurisdiction})
            row = result.fetchone()
            
            if row:
                case_type_id = row.case_type_id
            else:
                # Create new
                insert_query = text("""
                    INSERT INTO case_types (case_type, description, jurisdiction, created_at)
                    VALUES (:case_type, :description, :jurisdiction, NOW())
                    RETURNING case_type_id
                """)
                result = conn.execute(insert_query, {
                    'case_type': normalized,
                    'description': f"{normalized} case type",
                    'jurisdiction': jurisdiction
                })
                case_type_id = result.fetchone().case_type_id
                conn.commit()
                logger.info(f"Created case type: {normalized} (ID: {case_type_id})")
            
            self._cache['case_types'][cache_key] = case_type_id
            return case_type_id
    
    def get_or_create_stage_type(
        self, 
        opinion_type: Optional[str] = None,
        court_level: Optional[str] = None
    ) -> Optional[int]:
        """Get or create stage type and return ID."""
        # Determine stage from opinion_type or court_level
        stage_name = None
        level = 1
        
        if opinion_type:
            opinion_lower = opinion_type.lower()
            for key, (name, lvl) in self.STAGE_TYPE_MAPPING.items():
                if key in opinion_lower:
                    stage_name = name
                    level = lvl
                    break
        
        if not stage_name and court_level:
            court_lower = court_level.lower()
            if 'supreme' in court_lower:
                stage_name = 'Supreme Court'
                level = 1
            elif 'appeal' in court_lower:
                stage_name = 'Court Of Appeals'
                level = 2
        
        if not stage_name:
            return None
        
        # Check cache
        if stage_name in self._cache['stage_types']:
            return self._cache['stage_types'][stage_name]
        
        with self.db.connect() as conn:
            # Try to find existing
            query = text("SELECT stage_type_id FROM stage_types WHERE stage_type = :stage_type")
            result = conn.execute(query, {'stage_type': stage_name})
            row = result.fetchone()
            
            if row:
                stage_type_id = row.stage_type_id
            else:
                # Create new
                insert_query = text("""
                    INSERT INTO stage_types (stage_type, description, level, created_at)
                    VALUES (:stage_type, :description, :level, NOW())
                    RETURNING stage_type_id
                """)
                result = conn.execute(insert_query, {
                    'stage_type': stage_name,
                    'description': f"{stage_name} legal stage",
                    'level': level
                })
                stage_type_id = result.fetchone().stage_type_id
                conn.commit()
                logger.info(f"Created stage type: {stage_name} (ID: {stage_type_id})")
            
            self._cache['stage_types'][stage_name] = stage_type_id
            return stage_type_id
    
    def get_or_create_document_type(self, opinion_type: Optional[str] = None) -> int:
        """Get or create document type and return ID."""
        # Determine document type from opinion_type
        doc_type_name = 'Court Decision'  # Default
        
        if opinion_type:
            opinion_lower = opinion_type.lower()
            for key, name in self.DOCUMENT_TYPE_MAPPING.items():
                if key in opinion_lower:
                    doc_type_name = name
                    break
        
        # Check cache
        if doc_type_name in self._cache['document_types']:
            return self._cache['document_types'][doc_type_name]
        
        with self.db.connect() as conn:
            # Try to find existing
            query = text("SELECT document_type_id FROM document_types WHERE document_type = :document_type")
            result = conn.execute(query, {'document_type': doc_type_name})
            row = result.fetchone()
            
            if row:
                doc_type_id = row.document_type_id
            else:
                # Create new
                insert_query = text("""
                    INSERT INTO document_types (document_type, description, has_decision, role, created_at)
                    VALUES (:document_type, :description, :has_decision, :role, NOW())
                    RETURNING document_type_id
                """)
                result = conn.execute(insert_query, {
                    'document_type': doc_type_name,
                    'description': f"{doc_type_name} document",
                    'has_decision': True,
                    'role': 'court'
                })
                doc_type_id = result.fetchone().document_type_id
                conn.commit()
                logger.info(f"Created document type: {doc_type_name} (ID: {doc_type_id})")
            
            self._cache['document_types'][doc_type_name] = doc_type_id
            return doc_type_id
    
    def get_or_create_court(
        self,
        court_name: Optional[str] = None,
        court_level: Optional[str] = None,
        division: Optional[str] = None,
        county: Optional[str] = None
    ) -> Optional[int]:
        """Get or create court and return ID."""
        if not court_name:
            # Build court name from level and division
            if court_level == 'Supreme':
                court_name = 'Washington State Supreme Court'
            elif court_level == 'Appeals' and division:
                court_name = f'Washington Court of Appeals Division {division}'
            elif court_level == 'Appeals':
                court_name = 'Washington Court of Appeals'
            else:
                return None
        
        # Check cache
        if court_name in self._cache['courts']:
            return self._cache['courts'][court_name]
        
        # Determine court_type
        court_type = None
        if 'supreme' in court_name.lower():
            court_type = 'Supreme Court'
        elif 'appeals' in court_name.lower():
            court_type = 'Court of Appeals'
        elif 'superior' in court_name.lower():
            court_type = 'Superior Court'
        
        with self.db.connect() as conn:
            # Try to find existing
            query = text("SELECT court_id FROM courts_dim WHERE court = :court")
            result = conn.execute(query, {'court': court_name})
            row = result.fetchone()
            
            if row:
                court_id = row.court_id
            else:
                # Create new
                insert_query = text("""
                    INSERT INTO courts_dim (court, level, jurisdiction, district, county, court_type)
                    VALUES (:court, :level, :jurisdiction, :district, :county, :court_type)
                    RETURNING court_id
                """)
                
                district = f"Division {division}" if division else None
                
                result = conn.execute(insert_query, {
                    'court': court_name,
                    'level': court_level,
                    'jurisdiction': 'WA',
                    'district': district,
                    'county': county,
                    'court_type': court_type
                })
                court_id = result.fetchone().court_id
                conn.commit()
                logger.info(f"Created court: {court_name} (ID: {court_id})")
            
            self._cache['courts'][court_name] = court_id
            return court_id
    
    def clear_cache(self):
        """Clear the dimension cache."""
        self._cache = {
            'case_types': {},
            'stage_types': {},
            'document_types': {},
            'courts': {}
        }
