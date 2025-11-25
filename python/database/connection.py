"""
Database Connection Management for SDNCheck Sanctions Screening System

This module provides:
- Synchronous and asynchronous database connections
- Connection pooling with proper configuration
- Health checks and connection validation
- Transaction management helpers
- Environment-based configuration

Uses SQLAlchemy 2.0 style with proper typing support.
"""

import os
import logging
from typing import Generator, Optional, AsyncGenerator
from contextlib import contextmanager, asynccontextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

# Optional async support
try:
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        AsyncSession,
        async_sessionmaker
    )
    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False

from database.models import Base

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

def get_database_url(async_mode: bool = False) -> str:
    """
    Build database URL from environment variables.
    
    Environment variables:
    - DB_HOST: Database host (default: localhost)
    - DB_PORT: Database port (default: 5432)
    - DB_NAME: Database name (default: sdn_database)
    - DB_USER: Database user (default: sdn_user)
    - DB_PASSWORD: Database password (default: sdn_password)
    - DATABASE_URL: Full connection URL (overrides individual settings)
    
    Args:
        async_mode: If True, returns async-compatible URL (postgresql+asyncpg)
    
    Returns:
        Database connection URL
    """
    # Check for full URL first
    full_url = os.getenv("DATABASE_URL")
    if full_url:
        if async_mode and full_url.startswith("postgresql://"):
            return full_url.replace("postgresql://", "postgresql+asyncpg://")
        return full_url
    
    # Build from components
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_NAME", "sdn_database")
    user = os.getenv("DB_USER", "sdn_user")
    password = os.getenv("DB_PASSWORD", "sdn_password")
    
    if async_mode:
        driver = "postgresql+asyncpg"
    else:
        driver = "postgresql+psycopg2"
    
    return f"{driver}://{user}:{password}@{host}:{port}/{database}"


def get_pool_settings() -> dict:
    """
    Get connection pool settings from environment.
    
    Environment variables:
    - DB_POOL_SIZE: Connection pool size (default: 5)
    - DB_MAX_OVERFLOW: Max connections above pool_size (default: 10)
    - DB_POOL_TIMEOUT: Timeout waiting for connection (default: 30)
    - DB_POOL_RECYCLE: Connection recycle time in seconds (default: 1800)
    
    Returns:
        Dictionary of pool settings
    """
    return {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True,  # Enable connection health checks
    }


# ============================================
# DATABASE MANAGER
# ============================================

class DatabaseManager:
    """
    Manages database connections and sessions.
    
    Provides both synchronous and asynchronous access patterns.
    Implements singleton pattern for application-wide usage.
    
    Usage:
        # Initialize (typically in app startup)
        db = DatabaseManager()
        db.init()
        
        # Get session
        with db.session() as session:
            entities = session.query(SanctionedEntity).all()
        
        # Async usage
        async with db.async_session() as session:
            result = await session.execute(select(SanctionedEntity))
    """
    
    _instance: Optional['DatabaseManager'] = None
    
    def __new__(cls) -> 'DatabaseManager':
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize database manager (only runs once due to singleton)."""
        if self._initialized:
            return
        
        self._engine = None
        self._async_engine = None
        self._session_factory = None
        self._async_session_factory = None
        self._initialized = True
    
    def init(self, echo: bool = False) -> None:
        """
        Initialize database engines and session factories.
        
        Args:
            echo: If True, log all SQL statements
        """
        # Create synchronous engine
        url = get_database_url(async_mode=False)
        pool_settings = get_pool_settings()
        
        self._engine = create_engine(
            url,
            echo=echo,
            poolclass=QueuePool,
            **pool_settings
        )
        
        # Create session factory
        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )
        
        # Set up connection event listeners
        self._setup_event_listeners()
        
        # Create async engine if available
        if HAS_ASYNC:
            try:
                async_url = get_database_url(async_mode=True)
                self._async_engine = create_async_engine(
                    async_url,
                    echo=echo,
                    pool_size=pool_settings["pool_size"],
                    max_overflow=pool_settings["max_overflow"],
                    pool_recycle=pool_settings["pool_recycle"],
                    pool_pre_ping=True
                )
                
                self._async_session_factory = async_sessionmaker(
                    bind=self._async_engine,
                    class_=AsyncSession,
                    autocommit=False,
                    autoflush=False,
                    expire_on_commit=False
                )
            except ImportError:
                logger.warning("asyncpg not installed, async support disabled")
        
        logger.info("Database manager initialized")
    
    def _setup_event_listeners(self) -> None:
        """Set up SQLAlchemy event listeners for logging and debugging."""
        
        @event.listens_for(self._engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            """Log new database connections."""
            logger.debug("New database connection established")
        
        @event.listens_for(self._engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            """Log connection checkout from pool."""
            logger.debug("Connection checked out from pool")
        
        @event.listens_for(self._engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            """Log connection return to pool."""
            logger.debug("Connection returned to pool")
    
    @property
    def engine(self):
        """Get the SQLAlchemy engine."""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._engine
    
    @property
    def async_engine(self):
        """Get the async SQLAlchemy engine."""
        if self._async_engine is None:
            raise RuntimeError("Async database not initialized or not available.")
        return self._async_engine
    
    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Get a database session as a context manager.
        
        Automatically commits on success, rolls back on exception.
        
        Usage:
            with db.session() as session:
                session.add(entity)
                # Commits automatically on exit
        """
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    @asynccontextmanager
    async def async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session as a context manager.
        
        Usage:
            async with db.async_session() as session:
                result = await session.execute(select(Entity))
        """
        if self._async_session_factory is None:
            raise RuntimeError("Async database not initialized or not available.")
        
        session = self._async_session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    def create_tables(self) -> None:
        """Create all database tables."""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        Base.metadata.create_all(self._engine)
        logger.info("Database tables created")
    
    def drop_tables(self) -> None:
        """Drop all database tables. USE WITH CAUTION!"""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        Base.metadata.drop_all(self._engine)
        logger.warning("Database tables dropped")
    
    def health_check(self) -> bool:
        """
        Check if database connection is healthy.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            with self.session() as session:
                session.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def async_health_check(self) -> bool:
        """
        Check if async database connection is healthy.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            async with self.async_session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as e:
            logger.error(f"Async database health check failed: {e}")
            return False
    
    def close(self) -> None:
        """Close database connections and clean up."""
        if self._engine:
            self._engine.dispose()
            logger.info("Database engine disposed")
    
    async def async_close(self) -> None:
        """Close async database connections."""
        if self._async_engine:
            await self._async_engine.dispose()
            logger.info("Async database engine disposed")
    
    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance. Useful for testing."""
        if cls._instance and cls._instance._engine:
            cls._instance._engine.dispose()
        cls._instance = None


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def init_db(echo: bool = False) -> DatabaseManager:
    """
    Initialize the global database manager.
    
    Call this during application startup.
    
    Args:
        echo: If True, log all SQL statements
    
    Returns:
        DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager()
    _db_manager.init(echo=echo)
    return _db_manager


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for getting a database session.
    
    Usage in FastAPI:
        @app.get("/entities")
        def get_entities(db: Session = Depends(get_db)):
            return db.query(SanctionedEntity).all()
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.init()
    
    with _db_manager.session() as session:
        yield session


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting an async database session.
    
    Usage in FastAPI:
        @app.get("/entities")
        async def get_entities(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(SanctionedEntity))
            return result.scalars().all()
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.init()
    
    async with _db_manager.async_session() as session:
        yield session


def close_db() -> None:
    """
    Close the global database manager.
    
    Call this during application shutdown.
    """
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None


def get_db_manager() -> DatabaseManager:
    """
    Get the global database manager instance.
    
    Returns:
        DatabaseManager instance
    """
    global _db_manager
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_manager
