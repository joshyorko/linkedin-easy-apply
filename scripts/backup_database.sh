#!/bin/bash
# Backup SQLite database before migration

set -e

DB_PATH="${SQLITE_PATH:-./src/linkedin_jobs.sqlite}"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/linkedin_jobs_${TIMESTAMP}.sqlite"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Check if database exists
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database not found at: $DB_PATH"
    exit 1
fi

echo "📦 Backing up database..."
echo "   Source: $DB_PATH"
echo "   Backup: $BACKUP_FILE"

# Use SQLite's backup command for safe backup (even if db is in use)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Verify backup
ORIGINAL_SIZE=$(stat -f%z "$DB_PATH" 2>/dev/null || stat -c%s "$DB_PATH" 2>/dev/null)
BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null)

echo "   Original size: $ORIGINAL_SIZE bytes"
echo "   Backup size:   $BACKUP_SIZE bytes"

if [ "$BACKUP_SIZE" -gt 0 ]; then
    echo "✅ Backup completed successfully!"
    echo ""
    echo "To restore from backup:"
    echo "   cp $BACKUP_FILE $DB_PATH"
    echo ""
    echo "Recent backups:"
    ls -lh "$BACKUP_DIR" | tail -5
else
    echo "❌ Backup failed - file is empty!"
    exit 1
fi
