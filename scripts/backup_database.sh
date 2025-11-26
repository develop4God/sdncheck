#!/bin/bash
# ============================================
# SDNCheck Database Backup Script
# ============================================
# Creates database backups with retention policy
# Supports local and S3 backup destinations
#
# Usage: ./scripts/backup_database.sh [--s3|--local]
#
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_MODE="${1:-local}"

# Database configuration (from environment or defaults)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-sdn_database}"
DB_USER="${DB_USER:-sdn_user}"
DB_PASSWORD="${DB_PASSWORD:-sdn_password}"

# S3 Configuration (optional)
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-sdncheck/backups}"

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  SDNCheck Database Backup Script${NC}"
echo -e "${GREEN}  Mode: ${BACKUP_MODE}${NC}"
echo -e "${GREEN}================================================${NC}"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup filename
BACKUP_FILE="${BACKUP_DIR}/sdncheck_backup_${TIMESTAMP}.sql.gz"

# Step 1: Create database dump
echo -e "\n${GREEN}[1/4] Creating database backup...${NC}"

export PGPASSWORD="$DB_PASSWORD"
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --verbose --format=custom --compress=9 \
    --file="${BACKUP_DIR}/sdncheck_backup_${TIMESTAMP}.dump" 2>&1

# Also create SQL format for portability
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --verbose --format=plain | gzip > "$BACKUP_FILE" 2>&1

unset PGPASSWORD

echo -e "${GREEN}Backup created: ${BACKUP_FILE}${NC}"

# Step 2: Calculate backup checksum
echo -e "\n${GREEN}[2/4] Calculating checksum...${NC}"
CHECKSUM=$(sha256sum "$BACKUP_FILE" | cut -d ' ' -f 1)
echo "$CHECKSUM" > "${BACKUP_FILE}.sha256"
echo -e "${GREEN}Checksum: ${CHECKSUM}${NC}"

# Step 3: Upload to S3 (if configured)
if [ "$BACKUP_MODE" = "--s3" ] || [ "$BACKUP_MODE" = "s3" ]; then
    echo -e "\n${GREEN}[3/4] Uploading to S3...${NC}"
    if [ -z "$S3_BUCKET" ]; then
        echo -e "${RED}Error: S3_BUCKET not configured${NC}"
        exit 1
    fi
    
    aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$BACKUP_FILE")"
    aws s3 cp "${BACKUP_FILE}.sha256" "s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$BACKUP_FILE").sha256"
    echo -e "${GREEN}Uploaded to S3: s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$BACKUP_FILE")${NC}"
else
    echo -e "\n${GREEN}[3/4] Skipping S3 upload (local mode)${NC}"
fi

# Step 4: Clean old backups
echo -e "\n${GREEN}[4/4] Cleaning old backups (older than ${RETENTION_DAYS} days)...${NC}"
find "$BACKUP_DIR" -name "sdncheck_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "sdncheck_backup_*.dump" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "*.sha256" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true

# Count remaining backups
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/sdncheck_backup_*.sql.gz 2>/dev/null | wc -l)
echo -e "${GREEN}Backups retained: ${BACKUP_COUNT}${NC}"

echo -e "\n${GREEN}================================================${NC}"
echo -e "${GREEN}  Backup Complete!${NC}"
echo -e "${GREEN}  File: ${BACKUP_FILE}${NC}"
echo -e "${GREEN}  Size: $(du -h "$BACKUP_FILE" | cut -f1)${NC}"
echo -e "${GREEN}================================================${NC}"
