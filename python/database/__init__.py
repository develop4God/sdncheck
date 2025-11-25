"""
Database Package for SDNCheck Sanctions Screening System

This package provides:
- SQLAlchemy ORM models for all entities
- Database connection management
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
    DatabaseManager,
    get_db,
    get_async_db,
    init_db,
    close_db
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
    # Connection management
    'DatabaseManager',
    'get_db',
    'get_async_db',
    'init_db',
    'close_db'
]
