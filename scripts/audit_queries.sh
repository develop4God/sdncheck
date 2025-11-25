#!/bin/bash
#
# SDNCheck N+1 Query Audit Script
#
# This script helps identify N+1 query patterns by:
# 1. Enabling PostgreSQL query logging
# 2. Running functional tests
# 3. Analyzing logs for repeated query patterns
#
# Usage: ./scripts/audit_queries.sh [options]
#
# Options:
#   --duration SECONDS   Duration to capture queries (default: 60)
#   --threshold MS       Minimum query duration to log (default: 0)
#   --analyze-only       Only analyze existing logs
#   --output FILE        Output report file (default: query_audit_report.txt)
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-sdn_user}"
DB_NAME="${DB_NAME:-sdn_database}"
PGPASSWORD="${DB_PASSWORD:-sdn_password}"
export PGPASSWORD

DURATION=60
THRESHOLD=0
ANALYZE_ONLY=false
OUTPUT_FILE="query_audit_report.txt"
LOG_FILE="/tmp/pg_query_audit_$(date +%Y%m%d_%H%M%S).log"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --threshold)
            THRESHOLD="$2"
            shift 2
            ;;
        --analyze-only)
            ANALYZE_ONLY=true
            shift
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING:${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ERROR:${NC} $1"
}

run_psql() {
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAq "$@"
}

# ============================================
# ENABLE QUERY LOGGING
# ============================================

enable_logging() {
    log "Enabling PostgreSQL query logging..."
    
    run_psql -c "ALTER SYSTEM SET log_min_duration_statement = $THRESHOLD;" || {
        log_warn "Could not set log_min_duration_statement (may require superuser)"
    }
    
    run_psql -c "ALTER SYSTEM SET log_statement = 'all';" || {
        log_warn "Could not set log_statement (may require superuser)"
    }
    
    run_psql -c "SELECT pg_reload_conf();" > /dev/null 2>&1 || true
    
    log "Query logging enabled (threshold: ${THRESHOLD}ms)"
}

disable_logging() {
    log "Disabling detailed query logging..."
    
    run_psql -c "ALTER SYSTEM RESET log_min_duration_statement;" 2>/dev/null || true
    run_psql -c "ALTER SYSTEM RESET log_statement;" 2>/dev/null || true
    run_psql -c "SELECT pg_reload_conf();" > /dev/null 2>&1 || true
}

# ============================================
# RUN TESTS
# ============================================

run_tests() {
    log "Running functional tests to generate queries..."
    
    cd "$(dirname "$0")/../python" || exit 1
    
    # Run functional tests
    if [ -f "functional_test_db.py" ]; then
        python functional_test_db.py 2>&1 | tee "$LOG_FILE" || {
            log_warn "Some tests may have failed, but continuing analysis"
        }
    fi
    
    # Also run repository tests if available
    if [ -f "tests/test_repositories_integration.py" ]; then
        pytest tests/test_repositories_integration.py -v 2>&1 | tee -a "$LOG_FILE" || true
    fi
}

# ============================================
# ANALYZE QUERIES
# ============================================

analyze_queries() {
    log "Analyzing query patterns..."
    
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║              N+1 Query Audit Report                        ║"
    echo "╠════════════════════════════════════════════════════════════╣"
    echo "║  Generated: $(date '+%Y-%m-%d %H:%M:%S')                         ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Get recent queries from pg_stat_statements if available
    log "Checking for N+1 patterns in pg_stat_statements..."
    
    PG_STAT_EXISTS=$(run_psql -c "SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_stat_statements';" 2>/dev/null || echo "0")
    
    if [ "$PG_STAT_EXISTS" = "1" ]; then
        echo ""
        echo "=== Top 10 Most Frequent Queries ==="
        run_psql -c "
            SELECT 
                calls,
                round(total_exec_time::numeric, 2) as total_ms,
                round((total_exec_time/calls)::numeric, 2) as avg_ms,
                left(query, 100) as query_preview
            FROM pg_stat_statements 
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = '$DB_NAME')
            ORDER BY calls DESC 
            LIMIT 10;
        " 2>/dev/null || log_warn "pg_stat_statements query failed"
        
        echo ""
        echo "=== Potential N+1 Patterns (high call count, low avg time) ==="
        run_psql -c "
            SELECT 
                calls,
                round((total_exec_time/calls)::numeric, 2) as avg_ms,
                left(query, 80) as query_pattern
            FROM pg_stat_statements 
            WHERE 
                dbid = (SELECT oid FROM pg_database WHERE datname = '$DB_NAME')
                AND calls > 10
                AND total_exec_time/calls < 10
                AND query LIKE '%SELECT%'
            ORDER BY calls DESC 
            LIMIT 10;
        " 2>/dev/null || log_warn "N+1 pattern detection failed"
    else
        log_warn "pg_stat_statements extension not installed"
        echo ""
        echo "To enable detailed query analysis, install pg_stat_statements:"
        echo "  CREATE EXTENSION pg_stat_statements;"
    fi
    
    echo ""
    echo "=== Query Patterns to Review ==="
    echo ""
    
    # Check for common N+1 patterns in codebase
    echo "Checking repository code for lazy loading patterns..."
    
    REPO_FILE="database/repositories.py"
    if [ ! -f "$REPO_FILE" ]; then
        log_warn "Repository file not found at $REPO_FILE"
        return
    fi
    
    echo ""
    echo "--- Methods without eager loading ---"
    grep -n "session.query\|self.session.execute" "$REPO_FILE" 2>/dev/null | \
        grep -v "joinedload\|selectinload\|subqueryload" | head -20 || echo "None found"
    
    echo ""
    echo "--- Loops that may cause N+1 ---"
    grep -n "for.*in.*:" "$REPO_FILE" 2>/dev/null | head -10 || echo "None found"
    
    echo ""
    echo "=== Recommendations ==="
    echo ""
    echo "1. Review methods listed above for missing eager loading"
    echo "2. Add joinedload() for one-to-many relationships accessed in loops"
    echo "3. Add selectinload() for many-to-many relationships"
    echo "4. Use contains_eager() when joining with explicit queries"
    echo ""
    echo "Example fix:"
    echo "  # Before (N+1)"
    echo "  entities = session.query(Entity).all()"
    echo "  for e in entities:"
    echo "      print(e.aliases)  # Triggers additional query per entity"
    echo ""
    echo "  # After (eager loading)"
    echo "  entities = session.query(Entity).options(joinedload(Entity.aliases)).all()"
    echo ""
}

# ============================================
# GENERATE REPORT
# ============================================

generate_report() {
    log "Generating report: $OUTPUT_FILE"
    
    {
        echo "SDNCheck N+1 Query Audit Report"
        echo "================================"
        echo "Generated: $(date)"
        echo "Database: $DB_HOST:$DB_PORT/$DB_NAME"
        echo ""
        
        analyze_queries
        
        echo ""
        echo "=== Fixed N+1 Queries in Repository ==="
        echo ""
        echo "The following methods already use eager loading:"
        grep -n "joinedload\|selectinload" database/repositories.py 2>/dev/null | head -20 || echo "None found"
        
    } | tee "$OUTPUT_FILE"
    
    echo ""
    log "Report saved to: $OUTPUT_FILE"
}

# ============================================
# MAIN
# ============================================

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         SDNCheck N+1 Query Audit                           ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Verify database connection
if ! run_psql -c "SELECT 1" > /dev/null 2>&1; then
    log_error "Cannot connect to database at $DB_HOST:$DB_PORT"
    exit 1
fi

if [ "$ANALYZE_ONLY" = true ]; then
    generate_report
else
    # Trap to ensure we disable logging on exit
    trap disable_logging EXIT
    
    # Enable logging
    enable_logging
    
    # Run tests
    run_tests
    
    # Wait for logs to be written
    log "Waiting for logs to flush..."
    sleep 2
    
    # Analyze and generate report
    generate_report
    
    # Disable logging
    disable_logging
fi

echo ""
log "✨ Query audit complete!"
