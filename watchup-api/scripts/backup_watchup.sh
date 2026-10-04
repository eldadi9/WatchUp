#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${WATCHUP_DB_CONTAINER:?set the exact PostgreSQL container name}"
: "${WATCHUP_DB_NAME:?set the source database name}"
: "${WATCHUP_DB_USER:?set the backup database role}"
: "${WATCHUP_BACKUP_DIR:?set an absolute backup directory}"
: "${WATCHUP_BACKUP_PASSPHRASE_FILE:?set the protected backup passphrase file}"
: "${WATCHUP_BACKUP_RETENTION_DAYS:=14}"

case "$WATCHUP_BACKUP_DIR" in /*) ;; *) echo 'WATCHUP_BACKUP_DIR must be absolute' >&2; exit 2 ;; esac
mkdir -p "$WATCHUP_BACKUP_DIR"
test -r "$WATCHUP_BACKUP_PASSPHRASE_FILE"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="$WATCHUP_BACKUP_DIR/watchup-$timestamp.dump.gpg"
plain="$WATCHUP_BACKUP_DIR/.watchup-$timestamp.dump.tmp"
encrypted="$backup.tmp"
trap 'rm -f "$plain" "$encrypted"' EXIT
docker exec "$WATCHUP_DB_CONTAINER" pg_dump --format=custom --no-owner --no-privileges \
  --schema=watchup --username "$WATCHUP_DB_USER" --dbname "$WATCHUP_DB_NAME" > "$plain"
gpg --batch --yes --quiet --pinentry-mode loopback \
  --passphrase-file "$WATCHUP_BACKUP_PASSPHRASE_FILE" \
  --symmetric --cipher-algo AES256 --output "$encrypted" "$plain"
rm -f "$plain"
mv "$encrypted" "$backup"
find "$WATCHUP_BACKUP_DIR" -maxdepth 1 -type f -name 'watchup-*.dump.gpg' -mtime +"$WATCHUP_BACKUP_RETENTION_DAYS" -delete
trap - EXIT
printf '%s\n' "$backup"
