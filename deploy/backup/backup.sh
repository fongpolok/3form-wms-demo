#!/usr/bin/env bash
# Daily backup of both databases + the latest Excel export.
#   ./deploy/backup/backup.sh            (run from the project folder)
# Schedule it nightly with cron / launchd (see docs/install/README.md).
# Output folder and retention come from config/settings.yaml (backup.*).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a

OUT_DIR=$(python3 -c "import yaml;print(yaml.safe_load(open('config/settings.yaml'))['backup']['output_dir'])")
KEEP_DAYS=$(python3 -c "import yaml;print(yaml.safe_load(open('config/settings.yaml'))['backup']['keep_days'])")
PG_CONTAINER=${PG_CONTAINER:-threeform-postgres}
MONGO_CONTAINER=${MONGO_CONTAINER:-threeform-mongo}
STAMP=$(date +%Y%m%d-%H%M%S)
DEST="$OUT_DIR/$STAMP"
mkdir -p "$DEST" logs

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')][backup] $*" | tee -a logs/backup.log; }

log "Backup started -> $DEST"
docker exec "$PG_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DEST/postgres_${POSTGRES_DB}.dump"
log "PostgreSQL dump: $(du -h "$DEST/postgres_${POSTGRES_DB}.dump" | cut -f1)"
docker exec "$MONGO_CONTAINER" mongodump --quiet --db "$MONGO_DB" --archive --gzip > "$DEST/mongo_${MONGO_DB}.archive.gz"
log "MongoDB dump: $(du -h "$DEST/mongo_${MONGO_DB}.archive.gz" | cut -f1)"

find "$OUT_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -print -exec rm -rf {} + | while read -r old; do
  log "Removed old backup $old"
done
log "Backup finished"

# Restore (manual, when needed):
#   docker exec -i threeform-postgres pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean < backups/<stamp>/postgres_*.dump
#   docker exec -i threeform-mongo mongorestore --drop --archive --gzip < backups/<stamp>/mongo_*.archive.gz
