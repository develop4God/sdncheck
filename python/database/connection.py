"""
Database Connection Management for SDNCheck Sanctions Screening System

This module provides:
- FastAPI Dependency Injection pattern for database sessions
- Unit of Work pattern for explicit transaction boundaries
- Connection pooling with proper configuration
- Health checks and connection validation with retry logic
- Environment-based configuration

Uses SQLAlchemy 2.0 style with proper typing support.
"""

import os
import logging
import threading
from typing import Generator, Optional, AsyncGenerator, Callable
from contextlib import contextmanager, asynccontextmanager
from functools import lru_cache
from dataclasses import dataclass

from sqlalchemy import create_engine, event, text, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError

# Optional async support
try:
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        AsyncSession,
        async_sessionmaker,
        AsyncEngine
    )
    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False
    AsyncEngine = None

# Retry logic with tenacity
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log
    )
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

from database.models import Base

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

@dataclass
class DatabaseSettings:
    """Database configuration settings."""
    host: str = "localhost"
    port: int = 5432
    database: str = "sdn_database"
    user: str = "sdn_user"
    password: str = "sdn_password"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800
    echo: bool = False
    
    @classmethod
    def from_env(cls) -> 'DatabaseSettings':
        """Create settings from environment variables."""
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "sdn_database"),
            user=os.getenv("DB_USER", "sdn_user"),
            password=os.getenv("DB_PASSWORD", "sdn_password"),
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
            echo=os.getenv("DB_ECHO", "false").lower() == "true"
        )
    
    def get_url(self, async_mode: bool = False) -> str:
        """Build database URL."""
        # Check for full URL first
        full_url = os.getenv("DATABASE_URL")
        if full_url:
            if async_mode and full_url.startswith("postgresql://"):
                return full_url.replace("postgresql://", "postgresql+asyncpg://")
            return full_url
        
        driver = "postgresql+asyncpg" if async_mode else "postgresql+psycopg2"
        return f"{driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@lru_cache()
def get_settings() -> DatabaseSettings:
    """Get cached database settings."""
    return DatabaseSettings.from_env()


def get_database_url(async_mode: bool = False) -> str:
    """
    Build database URL from environment variables.
    
    Args:
        async_mode: If True, returns async-compatible URL (postgresql+asyncpg)
    
    Returns:
        Database connection URL
    """
    return get_settings().get_url(async_mode)


def get_pool_settings() -> dict:
    """
    Get connection pool settings from environment.
    
    Returns:
        Dictionary of pool settings
    """
    settings = get_settings()
    return {
        "pool_size": settings.pool_size,
        "max_overflow": settings.max_overflow,
        "pool_timeout": settings.pool_timeout,
        "pool_recycle": settings.pool_recycle,
        "pool_pre_ping": True,
    }


# ============================================
# RETRY LOGIC
# ============================================

def create_retry_decorator(
    max_attempts: int = 3,
    min_wait: float = 1,
    max_wait: float = 10
) -> Callable:
    """
    Create a retry decorator for database operations.
    
    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
    
    Returns:
        Retry decorator or identity function if tenacity not available
    """
    if not HAS_TENACITY:
        # Return identity decorator if tenacity not installed
        def identity(func):
            return func
        return identity
    
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(OperationalError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


# Create default retry decorator
db_retry = create_retry_decorator()


# ============================================
# UNIT OF WORK PATTERN
# ============================================

class UnitOfWork:
    """
    Unit of Work pattern for explicit transaction management.
    
    Provides clear transaction boundaries and ensures proper
    commit/rollback semantics.
    
    Usage:
        with UnitOfWork(session_factory) as uow:
            repo = SanctionedEntityRepository(uow.session)
            entity = repo.create(data)
            uow.commit()  # Explicit commit
    """
    
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory
        self._session: Optional[Session] = None
    
    def __enter__(self) -> 'UnitOfWork':
        self._session = self._session_factory()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        self.close()
    
    @property
    def session(self) -> Session:
        """Get the current session."""
        if self._session is None:
            raise RuntimeError("UnitOfWork not started. Use as context manager.")
        return self._session
    
    def commit(self) -> None:
        """Explicitly commit the transaction."""
        if self._session:
            self._session.commit()
    
    def rollback(self) -> None:
        """Rollback the transaction."""
        if self._session:
            self._session.rollback()
    
    def close(self) -> None:
        """Close the session."""
        if self._session:
            self._session.close()
            self._session = None


class AsyncUnitOfWork:
    """
    Async Unit of Work pattern for explicit transaction management.
    
    Usage:
        async with AsyncUnitOfWork(async_session_factory) as uow:
            repo = SanctionedEntityRepository(uow.session)
            entity = await repo.create_async(data)
            await uow.commit()
    """
    
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._session: Optional[AsyncSession] = None
    
    async def __aenter__(self) -> 'AsyncUnitOfWork':
        self._session = self._session_factory()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        await self.close()
    
    @property
    def session(self) -> AsyncSession:
        """Get the current session."""
        if self._session is None:
            raise RuntimeError("AsyncUnitOfWork not started. Use as context manager.")
        return self._session
    
    async def commit(self) -> None:
        """Explicitly commit the transaction."""
        if self._session:
            await self._session.commit()
    
    async def rollback(self) -> None:
        """Rollback the transaction."""
        if self._session:
            await self._session.rollback()
    
    async def close(self) -> None:
        """Close the session."""
        if self._session:
            await self._session.close()
            self._session = None


# ============================================
# DATABASE SESSION PROVIDER (FastAPI DI)
# ============================================

class DatabaseSessionProvider:
    """
    Provides database sessions using FastAPI Dependency Injection pattern.
    
    This replaces the singleton DatabaseManager with a more testable,
    injectable approach that's idiomatic for FastAPI applications.
    
    Usage:
        # Create provider (typically in app startup)
        db_provider = DatabaseSessionProvider()
        
        # Use in FastAPI endpoint
        @app.get("/entities")
        def get_entities(db: Session = Depends(db_provider.get_session)):
            return db.query(SanctionedEntity).all()
    """
    
    def __init__(
        self,
        settings: Optional[DatabaseSettings] = None,
        engine: Optional[Engine] = None,
        async_engine: Optional[AsyncEngine] = None
    ):
        """
        Initialize the database session provider.
        
        Args:
            settings: Database settings (uses env if not provided)
            engine: Pre-created engine (for testing)
            async_engine: Pre-created async engine (for testing)
        """
        self._settings = settings or get_settings()
        self._engine = engine
        self._async_engine = async_engine
        self._session_factory: Optional[sessionmaker] = None
        self._async_session_factory = None
        self._initialized = False
    
    def init(self, echo: Optional[bool] = None) -> None:
        """
        Initialize database engines and session factories.
        
        Args:
            echo: Override echo setting for SQL logging
        """
        if self._initialized:
            return
        
        if echo is not None:
            self._settings.echo = echo
        
        # Create synchronous engine if not provided
        if self._engine is None:
            self._engine = self._create_engine_with_retry()
        
        # Create session factory
        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )
        
        # Set up connection event listeners
        self._setup_event_listeners()
        
        # Create async engine if available and not provided
        if HAS_ASYNC and self._async_engine is None:
            try:
                self._async_engine = self._create_async_engine()
                self._async_session_factory = async_sessionmaker(
                    bind=self._async_engine,
                    class_=AsyncSession,
                    autocommit=False,
                    autoflush=False,
                    expire_on_commit=False
                )
            except ImportError:
                logger.warning("asyncpg not installed, async support disabled")
        
        self._initialized = True
        logger.info("Database session provider initialized")
    
    @db_retry
    def _create_engine_with_retry(self) -> Engine:
        """Create database engine with retry logic."""
        url = self._settings.get_url(async_mode=False)
        pool_settings = get_pool_settings()
        
        engine = create_engine(
            url,
            echo=self._settings.echo,
            poolclass=QueuePool,
            **pool_settings
        )
        
        # Verify connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return engine
    
    def _create_async_engine(self) -> AsyncEngine:
        """Create async database engine."""
        url = self._settings.get_url(async_mode=True)
        pool_settings = get_pool_settings()
        
        return create_async_engine(
            url,
            echo=self._settings.echo,
            pool_size=pool_settings["pool_size"],
            max_overflow=pool_settings["max_overflow"],
            pool_recycle=pool_settings["pool_recycle"],
            pool_pre_ping=True
        )
    
    def _setup_event_listeners(self) -> None:
        """Set up SQLAlchemy event listeners for logging and debugging."""
        
        @event.listens_for(self._engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            logger.debug("New database connection established")
        
        @event.listens_for(self._engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            logger.debug("Connection checked out from pool")
        
        @event.listens_for(self._engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            logger.debug("Connection returned to pool")
    
    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine."""
        if self._engine is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._engine
    
    @property
    def async_engine(self) -> AsyncEngine:
        """Get the async SQLAlchemy engine."""
        if self._async_engine is None:
            raise RuntimeError("Async database not initialized or not available.")
        return self._async_engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """Get the session factory."""
        if self._session_factory is None:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._session_factory
    
    def get_session(self) -> Generator[Session, None, None]:
        """
        FastAPI dependency for getting a database session.
        
        This is the primary method for dependency injection.
        
        Usage:
            @app.get("/entities")
            def get_entities(db: Session = Depends(db_provider.get_session)):
                return db.query(SanctionedEntity).all()
        """
        if self._session_factory is None:
            self.init()
        
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()
    
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        FastAPI dependency for getting an async database session.
        
        Usage:
            @app.get("/entities")
            async def get_entities(db: AsyncSession = Depends(db_provider.get_async_session)):
                result = await db.execute(select(SanctionedEntity))
                return result.scalars().all()
        """
        if self._async_session_factory is None:
            self.init()
        
        session = self._async_session_factory()
        try:
            yield session
        finally:
            await session.close()
    
    def get_unit_of_work(self) -> UnitOfWork:
        """
        Get a Unit of Work for explicit transaction management.
        
        Usage:
            with db_provider.get_unit_of_work() as uow:
                repo = SanctionedEntityRepository(uow.session)
                entity = repo.create(data)
                uow.commit()
        """
        if self._session_factory is None:
            self.init()
        return UnitOfWork(self._session_factory)
    
    def get_async_unit_of_work(self) -> AsyncUnitOfWork:
        """Get an async Unit of Work for explicit transaction management."""
        if self._async_session_factory is None:
            self.init()
        return AsyncUnitOfWork(self._async_session_factory)
    
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Context manager for session with auto-commit/rollback.
        
        Usage:
            with db_provider.session_scope() as session:
                session.add(entity)
                # Auto-commits on exit, rollbacks on exception
        """
        if self._session_factory is None:
            self.init()
        
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
    async def async_session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for async session with auto-commit/rollback."""
        if self._async_session_factory is None:
            self.init()
        
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
            self.init()
        Base.metadata.create_all(self._engine)
        logger.info("Database tables created")
    
    def drop_tables(self) -> None:
        """Drop all database tables. USE WITH CAUTION!"""
        if self._engine is None:
            self.init()
        Base.metadata.drop_all(self._engine)
        logger.warning("Database tables dropped")
    
    @db_retry
    def health_check(self) -> bool:
        """
        Check if database connection is healthy with retry.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            with self.session_scope() as session:
                session.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def async_health_check(self) -> bool:
        """Check if async database connection is healthy."""
        try:
            async with self.async_session_scope() as session:
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
        self._initialized = False
    
    async def async_close(self) -> None:
        """Close async database connections."""
        if self._async_engine:
            await self._async_engine.dispose()
            logger.info("Async database engine disposed")


# ============================================
# BACKWARD COMPATIBLE SINGLETON (DEPRECATED)
# ============================================

import warnings


class DatabaseManager(DatabaseSessionProvider):
    """
    DEPRECATED: Use DatabaseSessionProvider instead.
    
    Maintained for backward compatibility with existing code.
    This class will be removed in version 2.0.
    
    Migration Guide:
        See docs/MIGRATION_GUIDE.md for migration instructions.
    
    Example Migration:
        # Before (deprecated):
        db = DatabaseManager()
        with db.session() as session:
            entities = session.query(SanctionedEntity).all()
        
        # After (recommended):
        from database.connection import get_db
        
        @app.get("/entities")
        def get_entities(db: Session = Depends(get_db)):
            return db.query(SanctionedEntity).all()
    """
    
    _instance: Optional['DatabaseManager'] = None
    _deprecation_warning_shown: bool = False
    _warning_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs) -> 'DatabaseManager':
        """Singleton pattern for backward compatibility."""
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance._initialized = False
        
        # Show deprecation warning once per session (thread-safe)
        with cls._warning_lock:
            if not cls._deprecation_warning_shown:
                warnings.warn(
                    "DatabaseManager is deprecated and will be removed in version 2.0. "
                    "Use DatabaseSessionProvider with FastAPI Depends() or get_db() instead. "
                    "See docs/MIGRATION_GUIDE.md for migration instructions.",
                    DeprecationWarning,
                    stacklevel=2
                )
                cls._deprecation_warning_shown = True
        
        return cls._instance
    
    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        DEPRECATED: Use session_scope() or get_session() instead.
        
        This method will be removed in version 2.0.
        """
        warnings.warn(
            "DatabaseManager.session() is deprecated. "
            "Use session_scope() or FastAPI Depends(get_db) instead.",
            DeprecationWarning,
            stacklevel=2
        )
        with self.session_scope() as session:
            yield session
    
    @asynccontextmanager
    async def async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        DEPRECATED: Use async_session_scope() instead.
        
        This method will be removed in version 2.0.
        """
        warnings.warn(
            "DatabaseManager.async_session() is deprecated. "
            "Use async_session_scope() or FastAPI Depends(get_async_db) instead.",
            DeprecationWarning,
            stacklevel=2
        )
        async with self.async_session_scope() as session:
            yield session
    
    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance. Useful for testing."""
        if cls._instance and cls._instance._engine:
            cls._instance._engine.dispose()
        cls._instance = None
        cls._deprecation_warning_shown = False


# ============================================
# GLOBAL PROVIDER INSTANCE
# ============================================

# Default database provider instance
_db_provider: Optional[DatabaseSessionProvider] = None


def get_db_provider() -> DatabaseSessionProvider:
    """
    Get the global database provider instance.
    
    Returns:
        DatabaseSessionProvider instance
    """
    global _db_provider
    if _db_provider is None:
        _db_provider = DatabaseSessionProvider()
    return _db_provider


def init_db(echo: bool = False) -> DatabaseSessionProvider:
    """
    Initialize the global database provider.
    
    Call this during application startup.
    
    Args:
        echo: If True, log all SQL statements
    
    Returns:
        DatabaseSessionProvider instance
    """
    provider = get_db_provider()
    provider.init(echo=echo)
    return provider


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for getting a database session.
    
    Usage in FastAPI:
        @app.get("/entities")
        def get_entities(db: Session = Depends(get_db)):
            return db.query(SanctionedEntity).all()
    """
    provider = get_db_provider()
    if not provider._initialized:
        provider.init()
    
    yield from provider.get_session()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting an async database session.
    
    Usage in FastAPI:
        @app.get("/entities")
        async def get_entities(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(SanctionedEntity))
            return result.scalars().all()
    """
    provider = get_db_provider()
    if not provider._initialized:
        provider.init()
    
    async for session in provider.get_async_session():
        yield session


def close_db() -> None:
    """
    Close the global database provider.
    
    Call this during application shutdown.
    """
    global _db_provider
    if _db_provider:
        _db_provider.close()
        _db_provider = None


def get_db_manager() -> DatabaseManager:
    """
    DEPRECATED: Get the global database manager instance.
    Use get_db_provider() instead.
    
    This function will be removed in version 2.0.
    See docs/MIGRATION_GUIDE.md for migration instructions.
    
    Returns:
        DatabaseManager instance
    """
    warnings.warn(
        "get_db_manager() is deprecated and will be removed in version 2.0. "
        "Use get_db_provider() instead. See docs/MIGRATION_GUIDE.md for details.",
        DeprecationWarning,
        stacklevel=2
    )
    return DatabaseManager()


# ============================================
# PYTEST FIXTURES SUPPORT
# ============================================

def create_test_provider(
    engine: Optional[Engine] = None,
    settings: Optional[DatabaseSettings] = None
) -> DatabaseSessionProvider:
    """
    Create a database provider for testing.
    
    Args:
        engine: Pre-created engine (e.g., SQLite for unit tests)
        settings: Custom settings for testing
    
    Returns:
        DatabaseSessionProvider configured for testing
    """
    provider = DatabaseSessionProvider(
        settings=settings,
        engine=engine
    )
    return provider
