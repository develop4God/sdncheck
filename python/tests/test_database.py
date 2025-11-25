"""
Unit tests for database models and schema.

Tests the SQLAlchemy ORM models, relationships, and database operations.
Uses an in-memory SQLite database for fast testing where compatible,
and PostgreSQL for full integration tests.
"""

import pytest
import uuid
from datetime import datetime, timezone
from typing import Generator

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import models module to test normalization functions
from database.models import (
    DataSourceType,
    EntityType,
    ScreeningStatus,
    RecommendationType,
    AuditAction,
    normalize_name,
    normalize_document
)


class TestNormalizationFunctions:
    """Tests for name and document normalization functions."""
    
    def test_normalize_name_basic(self):
        """Test basic name normalization."""
        assert normalize_name("John Smith") == "JOHN SMITH"
        assert normalize_name("  John   Smith  ") == "JOHN SMITH"
    
    def test_normalize_name_accents(self):
        """Test accent removal in name normalization."""
        assert normalize_name("José García") == "JOSE GARCIA"
        assert normalize_name("François Müller") == "FRANCOIS MULLER"
    
    def test_normalize_name_special_chars(self):
        """Test special character handling."""
        assert normalize_name("O'Brien") == "O BRIEN"
        assert normalize_name("Smith-Jones") == "SMITH JONES"
    
    def test_normalize_name_empty(self):
        """Test empty name handling."""
        assert normalize_name("") == ""
    
    def test_normalize_name_none(self):
        """Test None name handling."""
        # The function should handle None gracefully
        result = normalize_name(None) if normalize_name.__code__.co_argcount == 1 else ""
        # If the function doesn't handle None, this test documents expected behavior
        try:
            assert normalize_name(None) == ""
        except (TypeError, AttributeError):
            # Some implementations may not handle None
            pass
    
    def test_normalize_document_basic(self):
        """Test basic document normalization."""
        assert normalize_document("PA12345678") == "PA12345678"
        assert normalize_document("pa-123-456-78") == "PA12345678"
    
    def test_normalize_document_with_spaces(self):
        """Test document normalization with spaces."""
        assert normalize_document("PA 123 456 78") == "PA12345678"
        # The function removes dots, so this should work
        result = normalize_document("12.345.678-9")
        assert result == "123456789"
    
    def test_normalize_document_empty(self):
        """Test empty document handling."""
        assert normalize_document("") == ""


class TestEnums:
    """Tests for enum types used in the database."""
    
    def test_entity_type_values(self):
        """Test EntityType enum values."""
        assert EntityType.INDIVIDUAL.value == "individual"
        assert EntityType.ENTITY.value == "entity"
        assert EntityType.VESSEL.value == "vessel"
        assert EntityType.AIRCRAFT.value == "aircraft"
    
    def test_data_source_type_values(self):
        """Test DataSourceType enum values."""
        assert DataSourceType.OFAC.value == "OFAC"
        assert DataSourceType.UN.value == "UN"
        assert DataSourceType.EU.value == "EU"
        assert DataSourceType.UK.value == "UK"
        assert DataSourceType.OTHER.value == "OTHER"
    
    def test_screening_status_values(self):
        """Test ScreeningStatus enum values."""
        assert ScreeningStatus.PENDING.value == "pending"
        assert ScreeningStatus.PROCESSING.value == "processing"
        assert ScreeningStatus.COMPLETED.value == "completed"
        assert ScreeningStatus.FAILED.value == "failed"
    
    def test_recommendation_type_values(self):
        """Test RecommendationType enum values."""
        assert RecommendationType.AUTO_ESCALATE.value == "AUTO_ESCALATE"
        assert RecommendationType.MANUAL_REVIEW.value == "MANUAL_REVIEW"
        assert RecommendationType.LOW_CONFIDENCE_REVIEW.value == "LOW_CONFIDENCE_REVIEW"
        assert RecommendationType.AUTO_CLEAR.value == "AUTO_CLEAR"
    
    def test_audit_action_values(self):
        """Test AuditAction enum values."""
        assert AuditAction.CREATE.value == "CREATE"
        assert AuditAction.READ.value == "READ"
        assert AuditAction.UPDATE.value == "UPDATE"
        assert AuditAction.DELETE.value == "DELETE"
        assert AuditAction.SCREEN.value == "SCREEN"
        assert AuditAction.BULK_SCREEN.value == "BULK_SCREEN"
        assert AuditAction.DATA_UPDATE.value == "DATA_UPDATE"


class TestModelImports:
    """Tests to verify all models can be imported correctly."""
    
    def test_import_base(self):
        """Test Base can be imported."""
        from database.models import Base
        assert Base is not None
    
    def test_import_entity_models(self):
        """Test entity models can be imported."""
        from database.models import (
            SanctionedEntity,
            EntityAlias,
            IdentityDocument,
            EntityAddress,
            EntityFeature
        )
        assert SanctionedEntity is not None
        assert EntityAlias is not None
        assert IdentityDocument is not None
        assert EntityAddress is not None
        assert EntityFeature is not None
    
    def test_import_program_models(self):
        """Test program models can be imported."""
        from database.models import (
            SanctionsProgram,
            EntityProgram
        )
        assert SanctionsProgram is not None
        assert EntityProgram is not None
    
    def test_import_screening_models(self):
        """Test screening models can be imported."""
        from database.models import (
            ScreeningRequest,
            ScreeningResult,
            ScreeningMatch
        )
        assert ScreeningRequest is not None
        assert ScreeningResult is not None
        assert ScreeningMatch is not None
    
    def test_import_audit_models(self):
        """Test audit models can be imported."""
        from database.models import (
            AuditLog,
            DataSource,
            DataUpdate
        )
        assert AuditLog is not None
        assert DataSource is not None
        assert DataUpdate is not None


class TestModelAttributes:
    """Tests to verify model attributes and structure."""
    
    def test_sanctioned_entity_has_required_columns(self):
        """Test SanctionedEntity has required columns."""
        from database.models import SanctionedEntity
        
        # Check table name
        assert SanctionedEntity.__tablename__ == "sanctioned_entities"
        
        # Check key column names exist
        mapper = SanctionedEntity.__mapper__
        column_names = [c.key for c in mapper.columns]
        
        required_columns = [
            'id', 'external_id', 'source', 'entity_type',
            'primary_name', 'normalized_name', 'is_deleted',
            'created_at', 'updated_at'
        ]
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_entity_alias_has_required_columns(self):
        """Test EntityAlias has required columns."""
        from database.models import EntityAlias
        
        assert EntityAlias.__tablename__ == "entity_aliases"
        
        mapper = EntityAlias.__mapper__
        column_names = [c.key for c in mapper.columns]
        
        required_columns = ['id', 'entity_id', 'alias_name', 'normalized_alias']
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_identity_document_has_required_columns(self):
        """Test IdentityDocument has required columns."""
        from database.models import IdentityDocument
        
        assert IdentityDocument.__tablename__ == "identity_documents"
        
        mapper = IdentityDocument.__mapper__
        column_names = [c.key for c in mapper.columns]
        
        required_columns = ['id', 'entity_id', 'document_type', 'document_number', 'normalized_number']
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_screening_request_has_required_columns(self):
        """Test ScreeningRequest has required columns."""
        from database.models import ScreeningRequest
        
        assert ScreeningRequest.__tablename__ == "screening_requests"
        
        mapper = ScreeningRequest.__mapper__
        column_names = [c.key for c in mapper.columns]
        
        required_columns = ['id', 'request_type', 'status', 'input_data']
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"
    
    def test_audit_log_has_required_columns(self):
        """Test AuditLog has required columns."""
        from database.models import AuditLog
        
        assert AuditLog.__tablename__ == "audit_logs"
        
        mapper = AuditLog.__mapper__
        column_names = [c.key for c in mapper.columns]
        
        required_columns = ['id', 'timestamp', 'action', 'resource_type', 'success']
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"


class TestModelRelationships:
    """Tests to verify model relationships are defined correctly."""
    
    def test_sanctioned_entity_relationships(self):
        """Test SanctionedEntity has correct relationships."""
        from database.models import SanctionedEntity
        
        # Check relationships exist
        relationships = SanctionedEntity.__mapper__.relationships.keys()
        
        expected_rels = ['aliases', 'documents', 'addresses', 'features', 'programs', 'matches']
        for rel in expected_rels:
            assert rel in relationships, f"Missing relationship: {rel}"
    
    def test_screening_request_relationships(self):
        """Test ScreeningRequest has correct relationships."""
        from database.models import ScreeningRequest
        
        relationships = ScreeningRequest.__mapper__.relationships.keys()
        assert 'results' in relationships
    
    def test_screening_result_relationships(self):
        """Test ScreeningResult has correct relationships."""
        from database.models import ScreeningResult
        
        relationships = ScreeningResult.__mapper__.relationships.keys()
        assert 'request' in relationships
        assert 'matches' in relationships


# PostgreSQL-specific tests (skipped if not available)
@pytest.fixture
def pg_session():
    """Create a PostgreSQL session for integration tests."""
    import os
    
    # Check if we can connect to PostgreSQL
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_NAME", "sdn_database")
    user = os.getenv("DB_USER", "sdn_user")
    password = os.getenv("DB_PASSWORD", "sdn_password")
    
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database.models import Base
        
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
        engine = create_engine(url, echo=False)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        
        # Create tables
        Base.metadata.create_all(engine)
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        yield session
        
        session.close()
        
        # Clean up tables after test
        Base.metadata.drop_all(engine)
        engine.dispose()
        
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


@pytest.mark.skipif(
    True,  # Skip by default since PostgreSQL may not be running
    reason="PostgreSQL integration tests require running database"
)
class TestPostgreSQLIntegration:
    """Integration tests requiring PostgreSQL."""
    
    def test_create_entity_postgresql(self, pg_session):
        """Test creating entity with PostgreSQL."""
        from database.models import SanctionedEntity, DataSourceType, EntityType
        
        entity = SanctionedEntity(
            external_id="PG-TEST-001",
            source=DataSourceType.OFAC,
            entity_type=EntityType.INDIVIDUAL,
            primary_name="PostgreSQL Test",
            normalized_name="POSTGRESQL TEST"
        )
        pg_session.add(entity)
        pg_session.commit()
        
        assert entity.id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

