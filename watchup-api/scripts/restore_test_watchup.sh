#!/usr/bin/env bash
set -euo pipefail

: "${WATCHUP_DB_CONTAINER:?set the exact PostgreSQL container name}"
: "${WATCHUP_RESTORE_DB:?set a disposable database name ending in _restore_test}"
: "${WATCHUP_RESTORE_DB_USER:?set the database role allowed to create disposable databases}"
: "${WATCHUP_BACKUP_PASSPHRASE_FILE:?set the protected backup passphrase file}"
: "${1:?pass the custom-format backup file}"
: "${2:?pass the expected synthetic event id}"

backup=$1
expected_event_id=$2
case "$WATCHUP_RESTORE_DB" in *_restore_test) ;; *) echo 'WATCHUP_RESTORE_DB must end in _restore_test' >&2; exit 2 ;; esac
test -f "$backup"
test -r "$WATCHUP_BACKUP_PASSPHRASE_FILE"
cleanup() { docker exec "$WATCHUP_DB_CONTAINER" dropdb --if-exists --username "$WATCHUP_RESTORE_DB_USER" "$WATCHUP_RESTORE_DB"; }
trap cleanup EXIT
cleanup
docker exec "$WATCHUP_DB_CONTAINER" createdb --username "$WATCHUP_RESTORE_DB_USER" "$WATCHUP_RESTORE_DB"
gpg --batch --quiet --pinentry-mode loopback \
  --passphrase-file "$WATCHUP_BACKUP_PASSPHRASE_FILE" --decrypt "$backup" \
  | docker exec -i "$WATCHUP_DB_CONTAINER" pg_restore --exit-on-error --no-owner --no-privileges \
      --username "$WATCHUP_RESTORE_DB_USER" --dbname "$WATCHUP_RESTORE_DB"
restored_count=$(printf '%s\n' "SELECT count(*) FROM watchup.events WHERE event_id = :'expected_event_id';" \
  | docker exec -i "$WATCHUP_DB_CONTAINER" psql --no-psqlrc --tuples-only --no-align --quiet \
      --set=ON_ERROR_STOP=1 --set=expected_event_id="$expected_event_id" \
      --username "$WATCHUP_RESTORE_DB_USER" --dbname "$WATCHUP_RESTORE_DB")
test "$restored_count" = "1"
