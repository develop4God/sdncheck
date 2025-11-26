"""
Database Performance Monitoring for SDNCheck

This module provides:
- Query timing context manager for slow query detection
- Prometheus metrics integration (optional)
- Database connection pool monitoring
- Query performance logging

Usage:
    from database.monitoring import query_timer, get_db_metrics

    with query_timer("search_by_name"):
        results = repo.search_by_name("John Doe")
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from functools import wraps
import threading

logger = logging.getLogger(__name__)

# Optional Prometheus integration
try:
    from prometheus_client import Histogram, Counter, Gauge, Info
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


# ============================================
# CONFIGURATION
# ============================================

@dataclass
class MonitoringConfig:
    """Configuration for database monitoring."""
    slow_query_threshold_ms: float = 1000.0  # Log queries slower than this
    warning_threshold_ms: float = 500.0       # Warn for queries slower than this
    enable_prometheus: bool = True             # Enable Prometheus metrics
    enable_logging: bool = True                # Enable logging
    sample_rate: float = 1.0                   # 1.0 = log all, 0.1 = log 10%


# Default configuration
_config = MonitoringConfig()


def configure_monitoring(
    slow_query_threshold_ms: float = 1000.0,
    warning_threshold_ms: float = 500.0,
    enable_prometheus: bool = True,
    enable_logging: bool = True,
    sample_rate: float = 1.0
) -> None:
    """
    Configure monitoring settings.
    
    Args:
        slow_query_threshold_ms: Log queries slower than this (ms)
        warning_threshold_ms: Warn for queries slower than this (ms)
        enable_prometheus: Enable Prometheus metrics
        enable_logging: Enable logging
        sample_rate: Fraction of queries to log (0.0-1.0)
    """
    global _config
    _config = MonitoringConfig(
        slow_query_threshold_ms=slow_query_threshold_ms,
        warning_threshold_ms=warning_threshold_ms,
        enable_prometheus=enable_prometheus,
        enable_logging=enable_logging,
        sample_rate=sample_rate
    )


# ============================================
# PROMETHEUS METRICS
# ============================================

if HAS_PROMETHEUS:
    # Query duration histogram
    db_query_duration = Histogram(
        'sdncheck_db_query_duration_seconds',
        'Database query duration in seconds',
        ['operation', 'status'],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    )
    
    # Query counter
    db_query_total = Counter(
        'sdncheck_db_query_total',
        'Total number of database queries',
        ['operation', 'status']
    )
    
    # Slow query counter
    db_slow_queries_total = Counter(
        'sdncheck_db_slow_queries_total',
        'Total number of slow database queries',
        ['operation']
    )
    
    # Connection pool gauges
    db_pool_size = Gauge(
        'sdncheck_db_pool_size',
        'Current database connection pool size'
    )
    
    db_pool_checked_out = Gauge(
        'sdncheck_db_pool_checked_out',
        'Number of connections currently checked out'
    )
    
    db_pool_overflow = Gauge(
        'sdncheck_db_pool_overflow',
        'Number of overflow connections in use'
    )
    
    # Database info
    db_info = Info(
        'sdncheck_db',
        'Database information'
    )


# ============================================
# QUERY STATS TRACKING
# ============================================

@dataclass
class QueryStats:
    """Statistics for a single query type."""
    operation: str
    count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float('inf')  # Using float('inf') for simplicity
    max_time_ms: float = 0.0
    errors: int = 0
    slow_queries: int = 0
    last_executed: Optional[datetime] = None
    
    @property
    def avg_time_ms(self) -> float:
        """Average query time in milliseconds."""
        return self.total_time_ms / self.count if self.count > 0 else 0.0
    
    def record(self, duration_ms: float, error: bool = False, slow: bool = False) -> None:
        """Record a query execution."""
        self.count += 1
        self.total_time_ms += duration_ms
        self.min_time_ms = min(self.min_time_ms, duration_ms)
        self.max_time_ms = max(self.max_time_ms, duration_ms)
        self.last_executed = datetime.now()
        
        if error:
            self.errors += 1
        if slow:
            self.slow_queries += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'operation': self.operation,
            'count': self.count,
            'total_time_ms': round(self.total_time_ms, 2),
            'avg_time_ms': round(self.avg_time_ms, 2),
            'min_time_ms': round(self.min_time_ms, 2) if self.min_time_ms != float('inf') else 0.0,
            'max_time_ms': round(self.max_time_ms, 2),
            'errors': self.errors,
            'slow_queries': self.slow_queries,
            'last_executed': self.last_executed.isoformat() if self.last_executed else None
        }


class QueryStatsCollector:
    """Thread-safe collector for query statistics."""
    
    def __init__(self):
        self._stats: Dict[str, QueryStats] = {}
        self._lock = threading.Lock()
        self._start_time = datetime.now()
    
    def record(self, operation: str, duration_ms: float, error: bool = False, slow: bool = False) -> None:
        """Record a query execution."""
        with self._lock:
            if operation not in self._stats:
                self._stats[operation] = QueryStats(operation=operation)
            self._stats[operation].record(duration_ms, error, slow)
    
    def get_stats(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """Get query statistics."""
        with self._lock:
            if operation:
                stat = self._stats.get(operation)
                return stat.to_dict() if stat else {}
            
            return {
                'uptime_seconds': (datetime.now() - self._start_time).total_seconds(),
                'operations': {
                    op: stats.to_dict() for op, stats in self._stats.items()
                }
            }
    
    def get_slow_queries(self) -> List[Dict[str, Any]]:
        """Get operations with slow queries."""
        with self._lock:
            return [
                stats.to_dict()
                for stats in self._stats.values()
                if stats.slow_queries > 0
            ]
    
    def reset(self) -> None:
        """Reset all statistics."""
        with self._lock:
            self._stats.clear()
            self._start_time = datetime.now()


# Global stats collector
_stats_collector = QueryStatsCollector()


def get_db_metrics() -> Dict[str, Any]:
    """
    Get current database metrics.
    
    Returns:
        Dictionary with query statistics
    """
    return _stats_collector.get_stats()


def get_slow_query_report() -> List[Dict[str, Any]]:
    """
    Get report of operations with slow queries.
    
    Returns:
        List of operations with slow query counts
    """
    return _stats_collector.get_slow_queries()


def reset_metrics() -> None:
    """Reset all collected metrics."""
    _stats_collector.reset()


# ============================================
# QUERY TIMER
# ============================================

@contextmanager
def query_timer(operation: str):
    """
    Context manager to time and monitor database queries.
    
    Logs slow queries and records metrics for monitoring.
    
    Args:
        operation: Name of the operation (e.g., 'search_by_name', 'get_by_id')
    
    Usage:
        with query_timer("search_by_name"):
            results = session.query(SanctionedEntity)...
    """
    start_time = time.perf_counter()
    error_occurred = False
    
    try:
        yield
    except Exception as e:
        error_occurred = True
        raise
    finally:
        duration = time.perf_counter() - start_time
        duration_ms = duration * 1000
        
        # Determine if slow
        is_slow = duration_ms > _config.slow_query_threshold_ms
        is_warning = duration_ms > _config.warning_threshold_ms
        
        # Record stats
        _stats_collector.record(
            operation=operation,
            duration_ms=duration_ms,
            error=error_occurred,
            slow=is_slow
        )
        
        # Prometheus metrics
        if HAS_PROMETHEUS and _config.enable_prometheus:
            status = "error" if error_occurred else "success"
            db_query_duration.labels(operation=operation, status=status).observe(duration)
            db_query_total.labels(operation=operation, status=status).inc()
            
            if is_slow:
                db_slow_queries_total.labels(operation=operation).inc()
        
        # Logging
        if _config.enable_logging:
            if is_slow:
                logger.warning(
                    f"SLOW QUERY: {operation} took {duration_ms:.2f}ms "
                    f"(threshold: {_config.slow_query_threshold_ms}ms)"
                )
            elif is_warning and not error_occurred:
                logger.info(f"Query {operation} took {duration_ms:.2f}ms")


def timed_query(operation: str):
    """
    Decorator to time and monitor database query methods.
    
    Args:
        operation: Name of the operation
    
    Usage:
        @timed_query("search_by_name")
        def search_by_name(self, name: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with query_timer(operation):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def async_timed_query(operation: str):
    """
    Decorator to time and monitor async database query methods.
    
    Args:
        operation: Name of the operation
    
    Usage:
        @async_timed_query("search_by_name")
        async def search_by_name(self, name: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            error_occurred = False
            
            try:
                return await func(*args, **kwargs)
            except Exception:
                error_occurred = True
                raise
            finally:
                duration = time.perf_counter() - start_time
                duration_ms = duration * 1000
                is_slow = duration_ms > _config.slow_query_threshold_ms
                
                _stats_collector.record(
                    operation=operation,
                    duration_ms=duration_ms,
                    error=error_occurred,
                    slow=is_slow
                )
                
                if is_slow and _config.enable_logging:
                    logger.warning(
                        f"SLOW ASYNC QUERY: {operation} took {duration_ms:.2f}ms"
                    )
        return wrapper
    return decorator


# ============================================
# CONNECTION POOL MONITORING
# ============================================

def update_pool_metrics(engine) -> None:
    """
    Update connection pool metrics from SQLAlchemy engine.
    
    Args:
        engine: SQLAlchemy Engine instance
    """
    if not HAS_PROMETHEUS or not _config.enable_prometheus:
        return
    
    try:
        pool = engine.pool
        
        # Get pool stats
        db_pool_size.set(pool.size())
        db_pool_checked_out.set(pool.checkedout())
        db_pool_overflow.set(pool.overflow())
        
    except Exception as e:
        logger.debug(f"Failed to update pool metrics: {e}")


def set_db_info(version: str, host: str, database: str) -> None:
    """
    Set database info metrics.
    
    Args:
        version: PostgreSQL version
        host: Database host
        database: Database name
    """
    if not HAS_PROMETHEUS or not _config.enable_prometheus:
        return
    
    db_info.info({
        'version': version,
        'host': host,
        'database': database
    })


# ============================================
# HEALTH CHECK METRICS
# ============================================

@dataclass
class HealthStatus:
    """Database health status."""
    healthy: bool
    latency_ms: float
    pool_size: int = 0
    pool_checked_out: int = 0
    pool_overflow: int = 0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'healthy': self.healthy,
            'latency_ms': round(self.latency_ms, 2),
            'pool': {
                'size': self.pool_size,
                'checked_out': self.pool_checked_out,
                'overflow': self.pool_overflow
            },
            'error': self.error,
            'timestamp': self.timestamp.isoformat()
        }


def check_health(engine, session_factory) -> HealthStatus:
    """
    Perform database health check with metrics.
    
    Args:
        engine: SQLAlchemy Engine
        session_factory: SQLAlchemy session factory
    
    Returns:
        HealthStatus with check results
    """
    from sqlalchemy import text
    
    start_time = time.perf_counter()
    
    try:
        # Execute health check query
        session = session_factory()
        try:
            session.execute(text("SELECT 1"))
            latency = (time.perf_counter() - start_time) * 1000
            
            # Get pool stats
            pool = engine.pool
            
            # Update Prometheus metrics
            update_pool_metrics(engine)
            
            return HealthStatus(
                healthy=True,
                latency_ms=latency,
                pool_size=pool.size(),
                pool_checked_out=pool.checkedout(),
                pool_overflow=pool.overflow()
            )
        finally:
            session.close()
            
    except Exception as e:
        latency = (time.perf_counter() - start_time) * 1000
        logger.error(f"Database health check failed: {e}")
        
        return HealthStatus(
            healthy=False,
            latency_ms=latency,
            error=str(e)
        )
