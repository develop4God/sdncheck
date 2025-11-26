#!/bin/bash
# ============================================
# SDNCheck Database Setup Script
# ============================================
# This script automates the complete database setup including:
# - Starting PostgreSQL container
# - Running migrations
# - Loading initial data
# - Verifying the setup
#
# Usage: ./scripts/setup_database.sh [--prod|--dev|--test]
#
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default environment
ENV="${1:-dev}"

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  SDNCheck Database Setup Script${NC}"
echo -e "${GREEN}  Environment: ${ENV}${NC}"
echo -e "${GREEN}================================================${NC}"

# Change to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Load environment-specific configuration
case "$ENV" in
    --prod|prod)
        ENV_FILE=".env.production"
        COMPOSE_FILE="docker-compose.yml -f docker-compose.prod.yml"
        echo -e "${YELLOW}Warning: Running in PRODUCTION mode${NC}"
        ;;
    --test|test)
        ENV_FILE=".env.test"
        COMPOSE_FILE="docker-compose.yml"
        echo -e "${GREEN}Running in TEST mode${NC}"
        ;;
    --dev|dev|*)
        ENV_FILE=".env"
        COMPOSE_FILE="docker-compose.yml"
        echo -e "${GREEN}Running in DEVELOPMENT mode${NC}"
        ;;
esac

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Step 1: Start PostgreSQL container
echo -e "\n${GREEN}[1/5] Starting PostgreSQL container...${NC}"
docker-compose -f $COMPOSE_FILE up -d db

# Wait for PostgreSQL to be ready
echo -e "${GREEN}Waiting for PostgreSQL to be ready...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0
until docker-compose -f $COMPOSE_FILE exec -T db pg_isready -U sdn_user -d sdn_database > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo -e "${RED}Error: PostgreSQL did not become ready in time${NC}"
        exit 1
    fi
    echo "  Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo -e "${GREEN}PostgreSQL is ready!${NC}"

# Step 2: Run Alembic migrations
echo -e "\n${GREEN}[2/5] Running database migrations...${NC}"
cd python
if [ -f "alembic.ini" ]; then
    # Check if database has any tables
    TABLE_COUNT=$(docker-compose -f ../$COMPOSE_FILE exec -T db psql -U sdn_user -d sdn_database -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
    
    if [ "$TABLE_COUNT" -gt "0" ]; then
        echo -e "${YELLOW}Database already has tables. Checking migration status...${NC}"
        # Stamp the database with the initial migration if not already done
        python -m alembic stamp head 2>/dev/null || python -m alembic upgrade head
    else
        echo -e "${GREEN}Running initial migration...${NC}"
        python -m alembic upgrade head
    fi
else
    echo -e "${YELLOW}Alembic not configured, using init SQL scripts...${NC}"
fi
cd ..

# Step 3: Load initial data
echo -e "\n${GREEN}[3/5] Loading initial data...${NC}"
cd python
python -c "
from database.connection import init_db
from database.repositories import DataSourceRepository, SanctionedEntityRepository
from database.models import DataSourceType

db = init_db()
with db.session_scope() as session:
    ds_repo = DataSourceRepository(session)
    
    # Verify data sources exist
    ofac = ds_repo.get_by_code('OFAC')
    un = ds_repo.get_by_code('UN')
    
    if ofac:
        print(f'  OFAC data source: OK (ID: {ofac.id})')
    else:
        print('  Warning: OFAC data source not found')
    
    if un:
        print(f'  UN data source: OK (ID: {un.id})')
    else:
        print('  Warning: UN data source not found')

print('Initial data verification complete.')
"
cd ..

# Step 4: Verify database connection from API
echo -e "\n${GREEN}[4/5] Verifying database connection...${NC}"
cd python
python test_db_connection.py
cd ..

# Step 5: Run quick integration test
echo -e "\n${GREEN}[5/5] Running quick integration test...${NC}"
cd python
python -c "
from database.connection import init_db, close_db

db = init_db()
health = db.health_check()
if health:
    print('  Database health check: PASSED')
else:
    print('  Database health check: FAILED')
    exit(1)

close_db()
print('Integration test passed.')
"
cd ..

echo -e "\n${GREEN}================================================${NC}"
echo -e "${GREEN}  Database Setup Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo -e ""
echo -e "Next steps:"
echo -e "  1. Run the API: cd python && uvicorn api.server:app --reload"
echo -e "  2. Run tests: cd python && pytest tests/ -v"
echo -e "  3. Download OFAC/UN data: cd python && python downloader.py"
echo -e ""
