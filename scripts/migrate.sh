#!/bin/bash
# ============================================
# SDNCheck Database Migration Script
# ============================================
# Manages Alembic migrations for database schema updates
#
# Usage: 
#   ./scripts/migrate.sh upgrade       - Run all pending migrations
#   ./scripts/migrate.sh downgrade     - Rollback last migration
#   ./scripts/migrate.sh create "msg"  - Create new migration
#   ./scripts/migrate.sh status        - Show migration status
#   ./scripts/migrate.sh history       - Show migration history
#
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to python directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT/python"

# Command
CMD="${1:-status}"
shift || true

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  SDNCheck Database Migration${NC}"
echo -e "${GREEN}  Command: ${CMD}${NC}"
echo -e "${GREEN}================================================${NC}"

case "$CMD" in
    upgrade)
        echo -e "\n${GREEN}Running database migrations...${NC}"
        python -m alembic upgrade head
        echo -e "${GREEN}Migrations complete.${NC}"
        ;;
    
    downgrade)
        STEPS="${1:-1}"
        echo -e "\n${YELLOW}Rolling back ${STEPS} migration(s)...${NC}"
        python -m alembic downgrade -${STEPS}
        echo -e "${GREEN}Rollback complete.${NC}"
        ;;
    
    create|revision)
        MESSAGE="$*"
        if [ -z "$MESSAGE" ]; then
            echo -e "${RED}Error: Please provide a migration message${NC}"
            echo "Usage: ./scripts/migrate.sh create \"your migration message\""
            exit 1
        fi
        echo -e "\n${GREEN}Creating new migration: ${MESSAGE}${NC}"
        python -m alembic revision --autogenerate -m "$MESSAGE"
        echo -e "${GREEN}Migration created. Review the generated file before applying.${NC}"
        ;;
    
    status|current)
        echo -e "\n${GREEN}Current migration status:${NC}"
        python -m alembic current
        ;;
    
    history)
        echo -e "\n${GREEN}Migration history:${NC}"
        python -m alembic history --verbose
        ;;
    
    heads)
        echo -e "\n${GREEN}Migration heads:${NC}"
        python -m alembic heads
        ;;
    
    stamp)
        REVISION="${1:-head}"
        echo -e "\n${YELLOW}Stamping database with revision: ${REVISION}${NC}"
        python -m alembic stamp "$REVISION"
        echo -e "${GREEN}Database stamped.${NC}"
        ;;
    
    *)
        echo -e "${RED}Unknown command: ${CMD}${NC}"
        echo ""
        echo "Available commands:"
        echo "  upgrade       - Run all pending migrations"
        echo "  downgrade [n] - Rollback n migrations (default: 1)"
        echo "  create \"msg\"  - Create new migration with message"
        echo "  status        - Show current migration status"
        echo "  history       - Show migration history"
        echo "  heads         - Show migration heads"
        echo "  stamp [rev]   - Mark database at specific revision"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Done.${NC}"
