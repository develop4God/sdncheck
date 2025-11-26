#!/bin/bash
#
# SDNCheck Backup/Restore Test Script
#
# This script validates the backup and restore workflow by:
# 1. Creating a backup
# 2. Inserting test data
# 3. Restoring from backup
# 4. Verifying test data is gone (restore successful)
#
# Usage: ./scripts/test_backup_restore.sh [options]
#
# Options:
#   --host HOST      Database host (default: localhost)
#   --port PORT      Database port (default: 5432)
#   --user USER      Database user (default: sdn_user)
#   --db DATABASE    Database name (default: sdn_database)
#   --verbose        Show detailed output
#   --keep-backup    Don't delete test backup after success
#
# Exit codes:
#   0 - Success
#   1 - Restore test failed
#   2 - Backup creation failed
#   3 - Database connection failed
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-sdn_user}"
DB_NAME="${DB_NAME:-sdn_database}"
PGPASSWORD="${DB_PASSWORD:-sdn_password}"
export PGPASSWORD

VERBOSE=false
KEEP_BACKUP=false
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TEST_BACKUP_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            DB_HOST="$2"
            shift 2
            ;;
        --port)
            DB_PORT="$2"
            shift 2
            ;;
        --user)
            DB_USER="$2"
            shift 2
            ;;
        --db)
            DB_NAME="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --keep-backup)
            KEEP_BACKUP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "  → $1"
    fi
}

cleanup() {
    local exit_code=$?
    
    if [ -n "$TEST_BACKUP_FILE" ] && [ -f "$TEST_BACKUP_FILE" ] && [ "$KEEP_BACKUP" = false ]; then
        verbose "Cleaning up test backup: $TEST_BACKUP_FILE"
        rm -f "$TEST_BACKUP_FILE"
        rm -f "${TEST_BACKUP_FILE}.sha256"
    fi
    
    exit $exit_code
}

trap cleanup EXIT

run_psql() {
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAq "$@"
}

# ============================================
# MAIN SCRIPT
# ============================================

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         SDNCheck Backup/Restore Test                       ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

log "🧪 Testing backup/restore workflow..."
verbose "Database: $DB_HOST:$DB_PORT/$DB_NAME"
verbose "User: $DB_USER"

# Step 0: Verify database connection
log "Step 0: Verifying database connection..."
if ! run_psql -c "SELECT 1" > /dev/null 2>&1; then
    log_error "Cannot connect to database at $DB_HOST:$DB_PORT"
    log_error "Ensure PostgreSQL is running and credentials are correct"
    exit 3
fi
verbose "Database connection successful"

# Step 1: Create backup
log "Step 1: Creating backup..."
mkdir -p "$BACKUP_DIR"
TEST_BACKUP_FILE="$BACKUP_DIR/test_backup_$(date +%Y%m%d_%H%M%S).sql"

if ! pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --format=plain \
    --clean \
    --if-exists \
    --file="$TEST_BACKUP_FILE" 2>/dev/null; then
    log_error "Backup creation failed"
    exit 2
fi

# Create checksum
sha256sum "$TEST_BACKUP_FILE" > "${TEST_BACKUP_FILE}.sha256"
BACKUP_SIZE=$(du -h "$TEST_BACKUP_FILE" | cut -f1)
verbose "Backup created: $TEST_BACKUP_FILE ($BACKUP_SIZE)"
verbose "Checksum: $(cat ${TEST_BACKUP_FILE}.sha256 | cut -d' ' -f1)"

# Step 2: Get initial count
log "Step 2: Recording initial state..."
INITIAL_COUNT=$(run_psql -c "SELECT COUNT(*) FROM data_sources WHERE name LIKE 'BACKUP_TEST_%';")
verbose "Initial test records: $INITIAL_COUNT"

# Step 3: Insert test data
log "Step 3: Inserting test data..."
TEST_ID=$(python3 -c 'import uuid; print(uuid.uuid4())' 2>/dev/null || uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)
TEST_NAME="BACKUP_TEST_$(date +%s)"

run_psql -c "INSERT INTO data_sources (id, code, name, description, url, source_type, is_active) VALUES ('$TEST_ID', 'TEST', '$TEST_NAME', 'Backup restore test record', 'http://test.example.com', 'OTHER', true);" > /dev/null

# Verify insert
NEW_COUNT=$(run_psql -c "SELECT COUNT(*) FROM data_sources WHERE name = '$TEST_NAME';")
if [ "$NEW_COUNT" != "1" ]; then
    log_error "Test data insert failed"
    exit 1
fi
verbose "Test record inserted: $TEST_NAME (ID: $TEST_ID)"

# Step 4: Verify checksum before restore
log "Step 4: Verifying backup integrity..."
if ! sha256sum -c "${TEST_BACKUP_FILE}.sha256" > /dev/null 2>&1; then
    log_error "Backup checksum verification failed"
    exit 2
fi
verbose "Backup checksum verified"

# Step 5: Restore from backup
log "Step 5: Restoring from backup..."
if ! run_psql -f "$TEST_BACKUP_FILE" > /dev/null 2>&1; then
    log_error "Restore failed"
    exit 1
fi
verbose "Restore completed"

# Step 6: Verify test data is gone
log "Step 6: Verifying restore..."
FINAL_COUNT=$(run_psql -c "SELECT COUNT(*) FROM data_sources WHERE name = '$TEST_NAME';")

if [ "$FINAL_COUNT" -eq "0" ]; then
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ BACKUP/RESTORE TEST PASSED                             ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log "Test data successfully removed after restore"
    log "Backup/restore workflow is working correctly"
else
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ BACKUP/RESTORE TEST FAILED                             ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log_error "Test data still exists after restore"
    log_error "Found $FINAL_COUNT records matching '$TEST_NAME'"
    log_error "The backup/restore workflow may not be working correctly"
    
    # Cleanup test data
    log_warn "Cleaning up orphaned test data..."
    run_psql -c "DELETE FROM data_sources WHERE name LIKE 'BACKUP_TEST_%';" > /dev/null 2>&1 || true
    
    exit 1
fi

# Step 7: Additional validation
log "Step 7: Additional validation..."

# Check row counts for critical tables
declare -A TABLES=(
    ["sanctioned_entities"]="Core entities"
    ["sanctions_programs"]="Sanctions programs"
    ["data_sources"]="Data sources"
)

for table in "${!TABLES[@]}"; do
    count=$(run_psql -c "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
    verbose "${TABLES[$table]} ($table): $count rows"
done

# Verify foreign key constraints
verbose "Checking foreign key constraints..."
FK_CHECK=$(run_psql -c "
    SELECT COUNT(*) 
    FROM information_schema.table_constraints 
    WHERE constraint_type = 'FOREIGN KEY' 
    AND table_schema = 'public';
")
verbose "Foreign key constraints: $FK_CHECK active"

echo ""
log "✨ All backup/restore tests completed successfully!"
echo ""

if [ "$KEEP_BACKUP" = true ]; then
    log "Test backup retained at: $TEST_BACKUP_FILE"
fi
