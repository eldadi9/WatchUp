#!/usr/bin/env bash
set -euo pipefail

: "${WATCHUP_API_CONTAINER:?set the exact API container name}"
: "${WATCHUP_API_IMAGE:?set the built image reference}"
: "${WATCHUP_INTERNAL_NETWORK:?set the pre-created internal Docker network}"
: "${WATCHUP_ENV_FILE:?set the protected application environment file}"
: "${WATCHUP_DB_PASSWORD_FILE_HOST:?set the protected host password-file path}"
: "${WATCHUP_DB_PASSWORD_FILE:?set its in-container path}"
: "${WATCHUP_DB_SSLROOTCERT_HOST:?set the host CA certificate path}"
: "${WATCHUP_DB_SSLROOTCERT:?set its in-container path}"
: "${WATCHUP_WEBHOOK_SECRET_FILE_HOST:?set the protected host webhook-secret path}"
: "${WATCHUP_WEBHOOK_SECRET_FILE:?set its in-container path}"

test -f "$WATCHUP_ENV_FILE"
test -r "$WATCHUP_DB_PASSWORD_FILE_HOST"
test -r "$WATCHUP_DB_SSLROOTCERT_HOST"
test -r "$WATCHUP_WEBHOOK_SECRET_FILE_HOST"
docker rm -f "$WATCHUP_API_CONTAINER" 2>/dev/null || true
docker run --detach --name "$WATCHUP_API_CONTAINER" --restart unless-stopped \
  --network "$WATCHUP_INTERNAL_NETWORK" \
  --env-file "$WATCHUP_ENV_FILE" \
  --mount "type=bind,src=$WATCHUP_DB_PASSWORD_FILE_HOST,dst=$WATCHUP_DB_PASSWORD_FILE,readonly" \
  --mount "type=bind,src=$WATCHUP_DB_SSLROOTCERT_HOST,dst=$WATCHUP_DB_SSLROOTCERT,readonly" \
  --mount "type=bind,src=$WATCHUP_WEBHOOK_SECRET_FILE_HOST,dst=$WATCHUP_WEBHOOK_SECRET_FILE,readonly" \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  "$WATCHUP_API_IMAGE"
