# WatchUp — Backup and Restore Runbook

Verified 18/10/2026 (Israel time) on the Production VPS with an isolated throwaway Postgres (`--network none`). The live database was only read.

## What is backed up

| Item | Backed up? | Where / how |
|---|---|---|
| Schema `watchup` (data, RLS policies, FORCE RLS, constraints) | Yes | cron `30 2 * * *` (UTC) `/opt/watchup/postgres/bin/run-backup.sh` → `/opt/watchup/backups/watchup-<UTC ts>.dump.gpg`. `pg_dump --format=custom --no-owner --no-privileges`, then GPG AES256 with `/opt/watchup/postgres/secrets/backup_passphrase`. 14 days kept. |
| **Object owners and GRANTs** | **No** — `--no-owner --no-privileges` | Re-applied from [restore_grants.sql](restore_grants.sql) (below). |
| Roles | No | Exist in the live cluster; created by hand on a fresh cluster (below). |
| `parents.json`, `families.json`, secrets | No | Manual copy only (`/opt/watchup/backups/pre-mf-20261017/` is the legacy state). |
| WhatsApp sessions | No, on purpose | A lost session is re-paired with the QR flow. |

Last verified backup: `watchup-20261017T210416Z.dump.gpg` (18/10/2026 00:04 IL), restored and fingerprinted below.

## Why the GRANTs step is mandatory

A restored schema has no owners and no privileges. Without the step below the API role `watchup_app` gets `permission denied` on every table, and tables stay owned by the restoring superuser instead of `watchup_owner` (so FORCE RLS would behave differently).

The exact permissions that Production has, and that [restore_grants.sql](restore_grants.sql) recreates:

| Object | Owner | `watchup_app` privileges |
|---|---|---|
| schema `watchup` | `watchup_owner` | USAGE |
| `events`, `parent_sessions`, `parent_totp_steps`, `child_settings`, `child_profiles`, `family_onboarding` | `watchup_owner` | SELECT, INSERT, UPDATE, DELETE |
| `parent_audit` | `watchup_owner` | SELECT, INSERT |
| `tracking_words` | `watchup_owner` | SELECT, INSERT, DELETE |
| sequence `parent_audit_id_seq` | `watchup_owner` | USAGE, SELECT |

Role membership: `watchup_migrator` ∈ `watchup_owner`; `watchup_api_login` ∈ `watchup_app`. None of the `watchup_*` roles except `watchup_admin` has BYPASSRLS or superuser.

If a table is added by a future migration, add its GRANT to `restore_grants.sql` in the same commit.

## A. Verify a backup without touching Production (verified)

Run on the VPS as root. Nothing here writes to the live database. First copy the two SQL files from this folder to the VPS: `ssh hostinger-vps 'mkdir -p /root/rt && chmod 700 /root/rt'`, then `scp docs/ops/restore_*.sql hostinger-vps:/root/rt/`; remove `/root/rt` afterwards.

```bash
DUMP=$(ls -t /opt/watchup/backups/watchup-*.dump.gpg | head -1)   # or run-backup.sh first for a fresh one
C=watchup-restore-proof; docker rm -f $C 2>/dev/null
docker run -d --rm --name $C --network none -e POSTGRES_USER=postgres -e POSTGRES_DB=watchup \
  -e POSTGRES_PASSWORD="$(openssl rand -hex 24)" postgres:16.15
until docker exec $C pg_isready -U postgres -d watchup; do sleep 1; done; sleep 2
P="docker exec -i $C psql -U postgres -d watchup -v ON_ERROR_STOP=1 -qAt"

# 1. roles (fresh cluster only)
$P <<'SQL'
CREATE ROLE watchup_owner NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE ROLE watchup_migrator NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE ROLE watchup_app NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE ROLE watchup_api_login LOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER;
GRANT watchup_owner TO watchup_migrator;
GRANT watchup_app TO watchup_api_login;
SQL

# 2. data
gpg --batch --quiet --pinentry-mode loopback --passphrase-file /opt/watchup/postgres/secrets/backup_passphrase -d "$DUMP" \
  | docker exec -i $C pg_restore --exit-on-error --no-owner --no-privileges -U postgres -d watchup

# 3. owners and GRANTs
$P < /root/rt/restore_grants.sql

# 4. compare with the live database: the two outputs must be identical
$P < /root/rt/restore_verify.sql > /tmp/restored.fp
docker exec -i watchup-postgres psql -U watchup_admin -d watchup -qAt < /root/rt/restore_verify.sql > /tmp/live.fp
diff /tmp/live.fp /tmp/restored.fp && echo FINGERPRINT_IDENTICAL
rm -f /tmp/restored.fp /tmp/live.fp
docker rm -f $C
```

Result on 18/10/2026: before step 3 the restored DB had **0** `watchup_app` grants; after it the 28-line fingerprint (grants, sequence ACL, schema owner and ACL, table owners with RLS flags, 12 policies, primary key `(tenant_id, child_id, event_id)`) was **identical** to Production. The app role, through `SET ROLE watchup_app` and `set_config('watchup.tenant_id', …)`, saw `family-poc` and `family-b` data only under its own tenant and **0 rows with no tenant**.

The same SQL files are used for recovery in section B.

## B. Recover Production from a backup

Not executed in Production (it would write to the live cluster). It follows the verified steps above; **needs Eldad's explicit approval**.

1. Take a fresh backup of what is left: `/opt/watchup/postgres/bin/run-backup.sh`.
2. Choose the dump (`ls -lt /opt/watchup/backups`). Note the loss window: events newer than the dump are gone; the bridges re-send nothing.
3. Restore into a **new** database name, never over `watchup`:
   `docker exec watchup-postgres createdb -U watchup_admin watchup_restore`, then step 2 above with `-d watchup_restore`, then run `restore_grants.sql` as `-U watchup_admin -d watchup_restore` (the roles already exist; skip step 1).
4. Run `restore_verify.sql` on `watchup_restore` and on the intact `watchup` (if it still exists) and compare.
5. Only after approval: stop the API (`docker stop watchup-api`), rename the databases (`ALTER DATABASE watchup RENAME TO watchup_old; ALTER DATABASE watchup_restore RENAME TO watchup;` — connected sessions must be gone), start the API, then run the checks in the operations runbook.
6. Keep `watchup_old` until the stabilization checks pass.

Do not restart the bridges for a database restore. They reconnect on their own through the API.

## C. Backup health

- Daily: `ls -lt /opt/watchup/backups/watchup-*.dump.gpg | head -3` — the newest must be under 26 hours old (the stabilization check does this).
- A backup failure is an alert-worthy event (see the operations runbook).
- Re-run section A after any migration or any change to roles or GRANTs.
