"""
Unit tests for database models and schema.

Tests the SQLAlchemy ORM models, relationships, and database operations.
Uses pytest fixtures for database session management instead of singletons.
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


# ============================================
# PYTEST FIXTURES FOR DATABASE
# ============================================

@pytest.fixture
def db_settings():
    """Create test database settings."""
    from database.connection import DatabaseSettings
    return DatabaseSettings(
        host="localhost",
        port=5432,
        database="sdn_test_database",
        user="sdn_user",
        password="sdn_password",
        pool_size=2,
        max_overflow=5,
        echo=False
    )


@pytest.fixture
def db_provider(db_settings):
    """
    Create a database provider for testing.
    
    Uses pytest fixture pattern instead of singleton.
    """
    from database.connection import create_test_provider
    from sqlalchemy import create_engine
    
    # Create in-memory SQLite for fast unit tests
    # (PostgreSQL-specific tests are skipped unless PG is available)
    try:
        engine = create_engine("sqlite:///:memory:", echo=False)
        provider = create_test_provider(engine=engine)
        provider.init()
        yield provider
    finally:
        if provider:
            provider.close()


@pytest.fixture
def db_session(db_provider):
    """
    Get a database session from the provider.
    
    Uses the new dependency injection pattern.
    """
    # Use the session_scope context manager
    with db_provider.session_scope() as session:
        yield session


@pytest.fixture
def unit_of_work(db_provider):
    """
    Get a Unit of Work instance for testing explicit transactions.
    """
    uow = db_provider.get_unit_of_work()
    yield uow
    if uow._session:
        uow.close()


# ============================================
# NORMALIZATION FUNCTION TESTS
# ============================================

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
        """Test None name handling - function should return empty string."""
        assert normalize_name(None) == ""
    
    def test_normalize_document_basic(self):
        """Test basic document normalization."""
        assert normalize_document("PA12345678") == "PA12345678"
        assert normalize_document("pa-123-456-78") == "PA12345678"
    
    def test_normalize_document_with_spaces(self):
        """Test that spaces, dashes and dots are removed from document numbers."""
        assert normalize_document("PA 123 456 78") == "PA12345678"
        # Dots should also be removed during normalization
        result = normalize_document("12.345.678-9")
        assert result == "123456789"
    
    def test_normalize_document_empty(self):
        """Test empty document handling."""
        assert normalize_document("") == ""


# ============================================
# ENUM TESTS
# ============================================

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


# ============================================
# MODEL IMPORT TESTS
# ============================================

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


# ============================================
# MODEL ATTRIBUTE TESTS
# ============================================

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


# ============================================
# MODEL RELATIONSHIP TESTS
# ============================================

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


# ============================================
# CONNECTION PROVIDER TESTS
# ============================================

class TestDatabaseSessionProvider:
    """Tests for the DatabaseSessionProvider (FastAPI DI pattern)."""
    
    def test_create_provider(self):
        """Test creating a database provider."""
        from database.connection import DatabaseSessionProvider, DatabaseSettings
        
        settings = DatabaseSettings(
            host="localhost",
            port=5432,
            database="test_db"
        )
        provider = DatabaseSessionProvider(settings=settings)
        assert provider is not None
        assert provider._settings == settings
    
    def test_provider_not_initialized(self):
        """Test that uninitialized provider raises error."""
        from database.connection import DatabaseSessionProvider, DatabaseSettings
        
        settings = DatabaseSettings()
        provider = DatabaseSessionProvider(settings=settings)
        
        # Engine should be None before init
        with pytest.raises(RuntimeError, match="Database not initialized"):
            _ = provider.engine


class TestUnitOfWork:
    """Tests for the Unit of Work pattern."""
    
    def test_unit_of_work_pattern(self):
        """Test Unit of Work context manager."""
        from database.connection import UnitOfWork
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create test engine
        engine = create_engine("sqlite:///:memory:", echo=False)
        session_factory = sessionmaker(bind=engine)
        
        with UnitOfWork(session_factory) as uow:
            assert uow.session is not None
            # Session should be available
            assert uow._session is not None
    
    def test_unit_of_work_explicit_commit(self):
        """Test Unit of Work with explicit commit."""
        from database.connection import UnitOfWork
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        engine = create_engine("sqlite:///:memory:", echo=False)
        session_factory = sessionmaker(bind=engine)
        
        with UnitOfWork(session_factory) as uow:
            # Can execute queries
            uow.session.execute(text("SELECT 1"))
            uow.commit()  # Explicit commit


class TestDatabaseSettings:
    """Tests for DatabaseSettings dataclass."""
    
    def test_default_settings(self):
        """Test default database settings."""
        from database.connection import DatabaseSettings
        
        settings = DatabaseSettings()
        assert settings.host == "localhost"
        assert settings.port == 5432
        assert settings.database == "sdn_database"
        assert settings.pool_size == 5
    
    def test_get_url(self):
        """Test URL generation from settings."""
        from database.connection import DatabaseSettings
        
        settings = DatabaseSettings(
            host="testhost",
            port=5433,
            database="testdb",
            user="testuser",
            password="testpass"
        )
        
        url = settings.get_url()
        assert "testhost" in url
        assert "5433" in url
        assert "testdb" in url
        assert "testuser" in url


# ============================================
# BACKWARD COMPATIBILITY TESTS
# ============================================

class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing code."""
    
    def test_database_manager_import(self):
        """Test DatabaseManager can still be imported (deprecated)."""
        from database.connection import DatabaseManager
        assert DatabaseManager is not None
    
    def test_get_db_function(self):
        """Test get_db function exists for FastAPI dependency."""
        from database.connection import get_db
        assert get_db is not None
        assert callable(get_db)
    
    def test_init_db_function(self):
        """Test init_db function exists."""
        from database.connection import init_db
        assert init_db is not None
        assert callable(init_db)
    
    def test_close_db_function(self):
        """Test close_db function exists."""
        from database.connection import close_db
        assert close_db is not None
        assert callable(close_db)


# ============================================
# POSTGRESQL INTEGRATION TESTS
# ============================================

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
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from database.models import Base
        
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
        engine = create_engine(url, echo=False)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
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

