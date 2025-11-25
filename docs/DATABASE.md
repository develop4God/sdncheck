# SDNCheck Database Documentation

This document provides comprehensive documentation for the SDNCheck database layer, including setup, migrations, and deployment procedures.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Database Setup](#database-setup)
4. [Migrations with Alembic](#migrations-with-alembic)
5. [Testing](#testing)
6. [Production Deployment](#production-deployment)
7. [Backup and Recovery](#backup-and-recovery)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- PostgreSQL 15+ (via Docker or native)

### 1. Start the Database

```bash
# Start PostgreSQL container
docker-compose up -d db

# Wait for database to be ready
docker-compose exec db pg_isready -U sdn_user -d sdn_database
```

### 2. Install Python Dependencies

```bash
cd python
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
# Run automated setup script
./scripts/setup_database.sh

# Or manually:
cd python
python -m alembic upgrade head
python load_initial_data.py
```

### 4. Verify Setup

```bash
cd python
python test_db_connection.py
```

---

## Architecture Overview

### Database Schema

The SDNCheck database follows a normalized design (3NF) with the following main components:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CORE ENTITIES                                │
├─────────────────────────────────────────────────────────────────────┤
│  sanctioned_entities   ←→  entity_aliases                          │
│         ↓                     ↓                                     │
│  identity_documents    entity_addresses    entity_features          │
│         ↓                                                           │
│  entity_programs  ←→  sanctions_programs                            │
├─────────────────────────────────────────────────────────────────────┤
│                        SCREENING                                    │
├─────────────────────────────────────────────────────────────────────┤
│  screening_requests  →  screening_results  →  screening_matches    │
├─────────────────────────────────────────────────────────────────────┤
│                        AUDIT & SYSTEM                               │
├─────────────────────────────────────────────────────────────────────┤
│  audit_logs            data_sources  →  data_updates                │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Features

- **UUID Primary Keys**: For distributed systems compatibility
- **Soft Delete**: `is_deleted` flag with `deleted_at` timestamp
- **Full-Text Search**: PostgreSQL trigram similarity (pg_trgm)
- **Audit Trail**: Immutable audit logs for compliance
- **Timestamps**: Automatic `created_at` and `updated_at`

### SQLAlchemy Models

All models are defined in `python/database/models.py`:

| Model | Table | Description |
|-------|-------|-------------|
| `SanctionedEntity` | `sanctioned_entities` | Core entity (individual, organization, vessel) |
| `EntityAlias` | `entity_aliases` | Alternative names |
| `IdentityDocument` | `identity_documents` | Passports, IDs, etc. |
| `EntityAddress` | `entity_addresses` | Physical addresses |
| `EntityFeature` | `entity_features` | Key-value attributes |
| `SanctionsProgram` | `sanctions_programs` | SDGT, OFAC, UN programs |
| `EntityProgram` | `entity_programs` | Entity-program junction |
| `ScreeningRequest` | `screening_requests` | API screening requests |
| `ScreeningResult` | `screening_results` | Screening outcomes |
| `ScreeningMatch` | `screening_matches` | Individual matches |
| `AuditLog` | `audit_logs` | System audit trail |
| `DataSource` | `data_sources` | OFAC, UN configurations |
| `DataUpdate` | `data_updates` | Data refresh logs |

---

## Database Setup

### Development Environment

```bash
# 1. Start PostgreSQL
docker-compose up -d db

# 2. Run setup script
./scripts/setup_database.sh --dev

# 3. Load sample data (optional)
cd python
python load_initial_data.py --with-samples
```

### Test Environment

```bash
# Setup test database
./scripts/setup_database.sh --test

# The test database (sdn_test_database) is created automatically
# by the init scripts in docker/init/
```

### Environment Variables

Configure via `.env` file or environment variables:

```bash
# Database Connection
DB_HOST=localhost
DB_PORT=5432
DB_NAME=sdn_database
DB_USER=sdn_user
DB_PASSWORD=sdn_password

# Connection Pool
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# For testing
DB_TEST_NAME=sdn_test_database
```

---

## Migrations with Alembic

### Running Migrations

```bash
# Apply all pending migrations
./scripts/migrate.sh upgrade

# Or directly:
cd python
python -m alembic upgrade head
```

### Creating New Migrations

```bash
# Auto-generate migration from model changes
./scripts/migrate.sh create "Add new column to entities"

# Review generated file in python/alembic/versions/
# Then apply:
./scripts/migrate.sh upgrade
```

### Migration Commands

| Command | Description |
|---------|-------------|
| `./scripts/migrate.sh upgrade` | Apply all pending migrations |
| `./scripts/migrate.sh downgrade` | Rollback last migration |
| `./scripts/migrate.sh status` | Show current migration status |
| `./scripts/migrate.sh history` | Show migration history |
| `./scripts/migrate.sh create "msg"` | Create new migration |

### For Existing Databases

If you have an existing database created from `01_init_schema.sql`:

```bash
# Mark current state as baseline (don't run migrations)
python -m alembic stamp 001_initial

# Then apply future migrations normally
python -m alembic upgrade head
```

---

## Testing

### Unit Tests

```bash
cd python
pytest tests/test_database.py -v
```

### Integration Tests

Integration tests require a running PostgreSQL database:

```bash
# Start database
docker-compose up -d db

# Run integration tests
cd python
pytest tests/test_repositories_integration.py -v
```

### All Tests

```bash
cd python
pytest tests/ -v --ignore=tests/test_performance.py
```

---

## Data Migration Strategy

This section outlines how to migrate data for different deployment scenarios.

### Scenario A: Greenfield (No Production Data)

For new installations with no existing data:

```bash
# 1. Start PostgreSQL
docker-compose up -d db

# 2. Apply migrations
./scripts/migrate.sh upgrade

# 3. Load initial reference data
cd python
python load_initial_data.py

# 4. (Optional) Load sample data for development
python load_initial_data.py --with-samples
```

### Scenario B: Brownfield (Existing Production Data)

For systems with existing production data:

#### 1. Pre-Migration (1 week before)

```bash
# Backup current production
./scripts/backup_database.sh

# Verify backup integrity
./scripts/test_backup_restore.sh
```

#### 2. Staging Validation

```bash
# Clone production to staging
pg_dump -h prod-host -U sdn_user sdn_database | \
    psql -h staging-host -U sdn_user sdn_database

# Test migration in staging
./scripts/migrate.sh upgrade

# Validate data integrity
python functional_test_db.py

# Test rollback
./scripts/migrate.sh downgrade
# Verify data restored correctly
```

#### 3. Production Deployment

```bash
# Schedule maintenance window
# Notify stakeholders

# Create backup before migration
./scripts/backup_database.sh --tag pre-migration

# Apply migration with monitoring
./scripts/migrate.sh upgrade

# Validate critical queries
python functional_test_db.py

# Verify performance
python -c "from database.monitoring import get_db_metrics; print(get_db_metrics())"
```

### Data Validation Checklist

After any migration, verify:

- [ ] **Row counts match** before/after for all tables
- [ ] **Foreign key constraints** are satisfied
- [ ] **No orphaned records** in child tables
- [ ] **Index integrity** (run `REINDEX DATABASE sdn_database;` if needed)
- [ ] **Query performance** within SLA (P95 < 500ms)
- [ ] **Application smoke tests** pass

### Validation Script

```bash
# Run full validation
cd python

# Count rows in critical tables
python -c "
from database.connection import get_db_provider
from sqlalchemy import text

provider = get_db_provider()
provider.init()

with provider.session_scope() as session:
    tables = ['sanctioned_entities', 'entity_aliases', 'screening_requests', 'audit_logs']
    for table in tables:
        count = session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
        print(f'{table}: {count} rows')
"

# Test search performance
python -c "
import time
from database.connection import get_db_provider
from database.repositories import SanctionedEntityRepository

provider = get_db_provider()
provider.init()

with provider.session_scope() as session:
    repo = SanctionedEntityRepository(session)
    start = time.time()
    results = repo.search_by_name('John Smith', threshold=0.3, limit=100)
    duration = (time.time() - start) * 1000
    print(f'Search returned {len(results)} results in {duration:.2f}ms')
"
```

---

## Production Deployment

### Security Checklist

1. **Change Default Credentials**
   ```bash
   # Generate strong password
   openssl rand -base64 32
   
   # Update docker-compose.yml or .env
   DB_PASSWORD=<generated_password>
   ```

2. **Enable SSL/TLS**
   ```yaml
   # docker-compose.prod.yml
   db:
     command: >
       postgres
       -c ssl=on
       -c ssl_cert_file=/etc/ssl/server.crt
       -c ssl_key_file=/etc/ssl/server.key
   ```

3. **Network Isolation**
   - Do not expose port 5432 publicly
   - Use internal Docker networks
   - Configure firewall rules

4. **Connection Limits**
   ```sql
   ALTER USER sdn_user CONNECTION LIMIT 100;
   ```

### Deployment Steps

```bash
# 1. Configure production environment
cp .env.example .env.production
# Edit .env.production with production values

# 2. Start database
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d db

# 3. Run migrations
./scripts/migrate.sh upgrade

# 4. Load initial data
cd python
python load_initial_data.py

# 5. Verify
python test_db_connection.py
```

---

## Backup and Recovery

### Automated Backups

```bash
# Create backup
./scripts/backup_database.sh

# Create backup and upload to S3
S3_BUCKET=my-bucket ./scripts/backup_database.sh --s3
```

### Manual Backup

```bash
# Full backup (custom format for pg_restore)
pg_dump -h localhost -U sdn_user -d sdn_database \
    --format=custom --compress=9 \
    --file=backup_$(date +%Y%m%d).dump

# SQL format backup
pg_dump -h localhost -U sdn_user -d sdn_database \
    --format=plain | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore from Backup

```bash
# Restore from custom format
pg_restore -h localhost -U sdn_user -d sdn_database \
    --clean --if-exists backup_20240101.dump

# Restore from SQL
gunzip -c backup_20240101.sql.gz | psql -h localhost -U sdn_user -d sdn_database
```

### Backup Schedule (Cron)

```bash
# Add to crontab
0 2 * * * /path/to/scripts/backup_database.sh >> /var/log/sdncheck_backup.log 2>&1
```

---

## Troubleshooting

### Common Issues

#### Cannot Connect to Database

```bash
# Check if container is running
docker-compose ps

# Check container logs
docker-compose logs db

# Verify port is accessible
pg_isready -h localhost -p 5432 -U sdn_user
```

#### Migration Errors

```bash
# Check current state
python -m alembic current

# View history
python -m alembic history

# If stuck, stamp and retry
python -m alembic stamp head
```

#### Connection Pool Exhausted

```python
# Increase pool settings in .env
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

#### Slow Queries

```bash
# Enable query logging in PostgreSQL
docker-compose exec db psql -U sdn_user -d sdn_database -c \
    "ALTER SYSTEM SET log_min_duration_statement = 1000;"

# Reload config
docker-compose exec db psql -U sdn_user -d sdn_database -c \
    "SELECT pg_reload_conf();"
```

### Health Checks

```python
# Python health check
from database.connection import init_db

db = init_db()
print("Health:", db.health_check())
```

```bash
# Bash health check
docker-compose exec db pg_isready -U sdn_user -d sdn_database
```

---

## API Integration

### FastAPI Dependency Injection

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from database.connection import get_db

@app.get("/entities")
def list_entities(db: Session = Depends(get_db)):
    repo = SanctionedEntityRepository(db)
    return repo.list_all()
```

### Unit of Work Pattern

```python
from database.connection import get_db_provider

provider = get_db_provider()

with provider.get_unit_of_work() as uow:
    repo = SanctionedEntityRepository(uow.session)
    entity = repo.create(data)
    uow.commit()  # Explicit commit
```

---

## Contact

For questions or issues:
- Create an issue in the GitHub repository
- Contact the development team

---

*Last updated: December 2024*
