# ADR 001: PostgreSQL Schema with Repository Pattern

## Status

**Accepted**

## Date

December 2024

## Context

The SDNCheck sanctions screening system needed persistent storage for:

1. **Sanctions data**: Individuals, organizations, vessels from OFAC, UN, EU, UK
2. **Screening operations**: Tracking requests, results, matches with audit trail
3. **Full-text search**: Fast fuzzy matching for name screening
4. **Compliance requirements**: Immutable audit logs, data retention policies
5. **Multi-environment support**: Development, testing, production deployments

### Requirements

- **Performance**: P95 search latency < 500ms for name matching
- **Scalability**: Support 100,000+ sanctioned entities
- **Compliance**: Full audit trail for regulatory requirements
- **Reliability**: ACID transactions for screening operations
- **Testability**: Support unit testing with mocks and integration testing

### Options Considered

1. **SQLite**: Simple, embedded, no setup required
2. **PostgreSQL**: Full-featured, production-grade RDBMS
3. **MongoDB**: Document-oriented, flexible schema
4. **Elasticsearch**: Optimized for full-text search

## Decision

We chose **PostgreSQL** with the following architecture:

### Database Design

- **Normalized schema (3NF)** for data integrity
- **UUID primary keys** for distributed compatibility
- **Soft delete** pattern for audit compliance
- **Trigram similarity** (pg_trgm) for fuzzy name matching

### Data Access Layer

- **SQLAlchemy ORM** with 2.0-style queries
- **Repository pattern** for clean data access abstraction
- **Unit of Work pattern** for explicit transaction boundaries
- **FastAPI Dependency Injection** for testable endpoints

### Migration Strategy

- **Alembic** for version-controlled schema migrations
- **Docker initialization scripts** for development setup
- **Backward-compatible changes** with deprecation notices

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                         │
├─────────────────────────────────────────────────────────────────┤
│  GET /entities         POST /screening        GET /health       │
│      │                      │                      │            │
│      ▼                      ▼                      ▼            │
│  Depends(get_db)       Depends(get_db)       Health Check       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               Repository Layer (repositories.py)                │
├─────────────────────────────────────────────────────────────────┤
│  SanctionedEntityRepository   ScreeningRepository               │
│      - search_by_name()           - create_request()            │
│      - get_by_id()                - add_result()                │
│      - search_by_document()       - complete_request()          │
│                                                                 │
│  AuditRepository              DataSourceRepository              │
│      - log()                      - record_update()             │
│      - search()                   - list_active()               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Connection Layer (connection.py)                   │
├─────────────────────────────────────────────────────────────────┤
│  DatabaseSessionProvider                                        │
│      - get_session()      → FastAPI Dependency Injection        │
│      - get_unit_of_work() → Explicit transaction control        │
│      - session_scope()    → Context manager with auto-commit    │
│                                                                 │
│  Features:                                                      │
│      - Connection pooling (QueuePool)                           │
│      - Health checks with retry (tenacity)                      │
│      - Async support (asyncpg)                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                          │
├─────────────────────────────────────────────────────────────────┤
│  Tables:                   Extensions:                          │
│    sanctioned_entities       pg_trgm (trigram similarity)       │
│    entity_aliases            uuid-ossp (UUID generation)        │
│    identity_documents                                           │
│    screening_requests      Indexes:                             │
│    audit_logs                GIN trigram on normalized_name     │
│                              B-tree on foreign keys             │
└─────────────────────────────────────────────────────────────────┘
```

## Consequences

### Positive

1. **Type-safe ORM**: SQLAlchemy provides compile-time type hints and IDE support
2. **Testable architecture**: Dependency injection enables easy mocking
3. **Automated migrations**: Alembic tracks schema changes in version control
4. **Fast fuzzy search**: PostgreSQL trigram similarity provides sub-500ms name matching
5. **Compliance ready**: Immutable audit logs satisfy regulatory requirements
6. **Production proven**: PostgreSQL is battle-tested for high-volume applications

### Negative

1. **Increased complexity**: Repository + Unit of Work adds abstraction layers
2. **Learning curve**: Team needs SQLAlchemy 2.0 and Alembic knowledge
3. **Migration overhead**: Schema changes require Alembic migrations
4. **PostgreSQL dependency**: Requires PostgreSQL-specific features (pg_trgm)

### Neutral

1. **Docker required**: Development environment needs Docker for PostgreSQL
2. **Connection pool tuning**: May need adjustment for production load

## Alternatives Not Chosen

### SQLite

- ✅ Simple, no server required
- ❌ No trigram extension for fuzzy search
- ❌ Limited concurrency
- ❌ Not suitable for production

### MongoDB

- ✅ Flexible schema for varying entity structures
- ❌ Weaker transaction guarantees
- ❌ Additional infrastructure complexity
- ❌ Less mature Python ORM support

### Elasticsearch

- ✅ Excellent full-text search
- ❌ Eventual consistency model
- ❌ Not suitable as primary data store
- ❌ Additional operational complexity

**Note**: Elasticsearch could be added later as a search index alongside PostgreSQL.

## Compliance

This architecture satisfies:

- **SOC 2**: Audit logging of all data access
- **GDPR**: Soft delete enables right-to-erasure compliance
- **PCI DSS**: Encryption at rest (PostgreSQL TDE) and in transit (SSL)

## References

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [PostgreSQL Trigram Extension](https://www.postgresql.org/docs/current/pgtrgm.html)
- [Alembic Migrations](https://alembic.sqlalchemy.org/en/latest/)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [Unit of Work Pattern](https://martinfowler.com/eaaCatalog/unitOfWork.html)

---

## Revision History

| Date | Author | Description |
|------|--------|-------------|
| 2024-12 | Development Team | Initial ADR created |
