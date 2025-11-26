# SDNCheck Deployment Runbook

This document provides step-by-step instructions for deploying and validating the SDNCheck system.

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Staging Environment Setup](#staging-environment-setup)
3. [Testing Workflow](#testing-workflow)
4. [Production Deployment](#production-deployment)
5. [Post-Deployment Validation](#post-deployment-validation)
6. [Rollback Procedures](#rollback-procedures)
7. [Monitoring & Alerts](#monitoring--alerts)

---

## Pre-Deployment Checklist

Before deploying, ensure the following items are completed:

- [ ] All tests passing in CI/CD
- [ ] Code review completed by 2+ senior engineers
- [ ] Security review completed
- [ ] Database backup taken
- [ ] Stakeholders notified
- [ ] Maintenance window scheduled (if required)

---

## Staging Environment Setup

### 1. Create Staging Environment

```bash
# Start staging services
docker-compose -f docker-compose.staging.yml up -d

# Verify services are healthy
docker-compose -f docker-compose.staging.yml ps

# Check database connectivity
docker exec sdncheck_postgres_staging pg_isready -U sdn_user -d sdn_database_staging
```

### 2. Configure Environment Variables

Copy the staging environment template:

```bash
cp python/.env.staging.example python/.env.staging

# Edit with staging-specific values:
# DB_HOST=localhost
# DB_PORT=5433  # Staging uses port 5433
# DB_NAME=sdn_database_staging
# DB_USER=sdn_user
# DB_PASSWORD=<your_secure_staging_password>  # CHANGE THIS
# API_KEY=<your_secure_api_key>  # CHANGE THIS
```

---

## Testing Workflow

### Step 1: Run Unit Tests

```bash
cd python
pytest tests/ -v --cov --ignore=tests/test_performance.py

# Expected: All tests pass
# Coverage target: >= 80%
```

### Step 2: Run Integration Tests

```bash
cd python
pytest tests/test_repositories_integration.py -v

# Expected: All tests pass or skip gracefully if DB unavailable
```

### Step 3: Validate Migrations

```bash
# Apply migrations
./scripts/migrate.sh upgrade

# Test downgrade (CRITICAL - must work for rollback)
./scripts/migrate.sh downgrade

# Re-apply migrations
./scripts/migrate.sh upgrade

# Verify schema
psql -h localhost -p 5433 -U sdn_user -d sdn_database_staging -c "\dt"
```

### Step 4: Load Initial Data

```bash
cd python
python load_initial_data.py

# For development samples:
python load_initial_data.py --with-samples
```

### Step 5: Run Functional Tests

```bash
cd python
python functional_test_db.py

# Expected output:
# ✅ Database Connection: SUCCESS
# ✅ Entity CRUD: SUCCESS
# ✅ Screening Workflow: SUCCESS
# ✅ Audit Logging: SUCCESS
# ✅ Unit of Work: SUCCESS
```

### Step 6: Backup/Restore Testing

```bash
./scripts/test_backup_restore.sh

# Expected: "✅ Restore test PASSED"
```

### Step 7: Query Performance Audit

```bash
./scripts/audit_queries.sh

# Review output for:
# - N+1 query patterns
# - Slow queries (> 100ms)
# - Missing indexes
```

### Step 8: Load Testing

```bash
# Start load test (10 minutes, 100 users)
locust -f python/tests/load_test.py --host=http://localhost:8001 \
       --users 100 --spawn-rate 10 --run-time 10m --headless

# Performance targets:
# - P95 latency < 500ms
# - Error rate < 0.1%
# - No connection pool exhaustion
```

---

## Production Deployment

### 1. Pre-Deployment Backup

```bash
# Tag the backup for easy identification
./scripts/backup_database.sh --tag pre-pr5-deployment

# Verify backup created
ls -la backups/
```

### 2. Maintenance Window Preparation

```bash
# Notify stakeholders
echo "SDNCheck maintenance starting - estimated 30 minutes"

# Optional: Put API in read-only mode
# curl -X POST http://api:8000/admin/maintenance/enable
```

### 3. Apply Migrations

```bash
./scripts/migrate.sh upgrade

# Verify migration applied
./scripts/migrate.sh current
```

### 4. Load/Update Initial Data

```bash
cd python
python load_initial_data.py
```

### 5. Smoke Tests

```bash
cd python
python functional_test_db.py
```

### 6. End Maintenance Window

```bash
# Disable read-only mode
# curl -X POST http://api:8000/admin/maintenance/disable

# Notify stakeholders
echo "SDNCheck maintenance completed - system operational"
```

---

## Post-Deployment Validation

### Monitor Key Metrics (First 30 Minutes)

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| P95 query latency | < 200ms | < 500ms |
| Connection pool usage | < 70% | < 90% |
| Failed transactions | < 0.1% | < 1% |
| Database CPU | < 60% | < 80% |
| Error rate | 0 | < 0.01% |

### Monitoring Commands

```bash
# Check API health
curl http://localhost:8000/api/v1/health

# Check database connections
psql -h localhost -p 5432 -U sdn_user -d sdn_database -c \
  "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Check recent errors
tail -f /var/log/sdncheck/api.log | grep ERROR
```

---

## Rollback Procedures

### If Migration Fails

```bash
# Rollback to previous version
./scripts/migrate.sh downgrade

# Verify rollback
./scripts/migrate.sh current
```

### If Data Corruption Detected

```bash
# Stop services
docker-compose down

# Restore from backup
BACKUP_FILE="backups/sdn_database_pre-pr5-deployment.sql"
psql -h localhost -p 5432 -U sdn_user -d sdn_database < "$BACKUP_FILE"

# Verify restore
python functional_test_db.py

# Restart services
docker-compose up -d
```

### If Performance Degradation

1. Check slow query log
2. Identify problematic queries
3. Add indexes or optimize queries
4. If critical, rollback and investigate

---

## Monitoring & Alerts

### Prometheus Queries

```promql
# P95 query latency
histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m]))

# Error rate
rate(db_query_errors_total[5m])

# Connection pool usage
db_connection_pool_usage / db_connection_pool_size
```

### Alert Thresholds

- **P95 latency > 500ms for 5 minutes** → Page on-call
- **Error rate > 1% for 5 minutes** → Page on-call
- **Connection pool > 90% for 5 minutes** → Page on-call
- **Database CPU > 80% for 10 minutes** → Page on-call

### Grafana Dashboard

Access at: http://localhost:3000 (staging) or http://monitoring:3000 (production)

Default credentials: admin / admin_staging (change in production)

---

## Emergency Contacts

| Role | Contact |
|------|---------|
| On-call Engineer | See PagerDuty schedule |
| Database Admin | See internal directory |
| Security Team | security@company.com |

---

## Appendix: Common Issues

### Issue: Connection Pool Exhausted

**Symptoms:** API returns 503, "connection pool exhausted" errors

**Solution:**
1. Check for leaked connections: `SELECT * FROM pg_stat_activity;`
2. Increase pool size: `DB_POOL_SIZE=10 DB_MAX_OVERFLOW=20`
3. Verify connection closure in code

### Issue: Slow Queries

**Symptoms:** P95 latency exceeds 500ms

**Solution:**
1. Run `./scripts/audit_queries.sh`
2. Check for missing indexes
3. Verify eager loading in repositories
4. Consider caching for frequent queries

### Issue: Migration Conflict

**Symptoms:** Alembic reports head conflict

**Solution:**
1. `alembic merge heads` (if automerge safe)
2. Manual conflict resolution in migration files
3. Test migration cycle: upgrade → downgrade → upgrade
