"""
Database Package for SDNCheck Sanctions Screening System

This package provides:
- SQLAlchemy ORM models for all entities
- FastAPI Dependency Injection for database sessions
- Unit of Work pattern for transaction management
- Repository pattern for data access
- Alembic integration for migrations
"""

from database.models import (
    Base,
    SanctionedEntity,
    EntityAlias,
    IdentityDocument,
    EntityAddress,
    EntityFeature,
    SanctionsProgram,
    EntityProgram,
    ScreeningRequest,
    ScreeningResult,
    ScreeningMatch,
    AuditLog,
    DataSource,
    DataUpdate
)
from database.connection import (
    # New recommended classes
    DatabaseSessionProvider,
    DatabaseSettings,
    UnitOfWork,
    AsyncUnitOfWork,
    # FastAPI dependencies
    get_db,
    get_async_db,
    get_db_provider,
    # Initialization
    init_db,
    close_db,
    # Testing support
    create_test_provider,
    # Backward compatible (deprecated)
    DatabaseManager,
    get_db_manager,
)

__all__ = [
    # Base
    'Base',
    # Entity models
    'SanctionedEntity',
    'EntityAlias',
    'IdentityDocument',
    'EntityAddress',
    'EntityFeature',
    'SanctionsProgram',
    'EntityProgram',
    # Screening models
    'ScreeningRequest',
    'ScreeningResult',
    'ScreeningMatch',
    # Audit models
    'AuditLog',
    'DataSource',
    'DataUpdate',
    # New database provider (recommended)
    'DatabaseSessionProvider',
    'DatabaseSettings',
    'UnitOfWork',
    'AsyncUnitOfWork',
    # FastAPI dependencies
    'get_db',
    'get_async_db',
    'get_db_provider',
    # Initialization
    'init_db',
    'close_db',
    # Testing support
    'create_test_provider',
    # Backward compatible (deprecated)
    'DatabaseManager',
    'get_db_manager',
]
