# WatchUp Multi-Family — Production Record

Status: **executed. Production runs two isolated Families (verdict `DOD_COMPLETE`, 17/10/2026).**
Post-DOD cleanup done 18/10/2026 (Israel time). Five-day stabilization freeze: **18/10/2026 → 23/10/2026.**
Code: `06f8f8b` (Local Multi-Family) + `e80272a` (mandatory first-entry onboarding). Production API image: `watchup-api:mf-e80272a`.

Companion documents:
- Operations (health, diagnosis, QR, restarts, escalation): [docs/ops/OPERATIONS_RUNBOOK.md](ops/OPERATIONS_RUNBOOK.md)
- Backup, restore and the GRANTs procedure: [docs/ops/RESTORE_RUNBOOK.md](ops/RESTORE_RUNBOOK.md)

No secret, password, token, session or message content appears in this document. Only file paths and structure.

## 1. What actually happened

| Step | What was done | Evidence |
|---|---|---|
| Preflight (17/10, 00:51 IL) | Read-only inspection of the legacy single-family Production (API `wp74-unstick`, migrations 001–005, `parents.json` mode 0644, no `families.json`). | Plan v1 preflight table (superseded by this record). |
| P1 backup (17/10 07:10Z) | Manual backup, config copies in `/opt/watchup/backups/pre-mf-20261017/` (legacy `parents.json`, `docker inspect` of API and Yuli's bridge, the old site, old `retain-events.sh` and `watch-connection.sh`, Yuli baseline). | Host file times. |
| Gate 1 | Migration **006** applied in the same command line as the API swap to the new code. New `onboarding.js` shipped to the web site. | `events` primary key is now `(tenant_id, child_id, event_id)`. |
| Gate 2 | Migration **007** applied; `families.json` written for `family-poc`; `parents.json` gained `tenant_id`; Multi-Family on. Retention and monitoring moved to the new image. | `child_profiles`, `family_onboarding` exist; onboarding completed for `family-poc`. |
| Gate 3 | `family-b` created: Rotem (own bridge secret), Ofir (no bridge), parents Elad and Anat with their own credentials. `watch-connection.sh` scoped to Yuli. | Cross-family 403 checks. |
| Gate 4 | Rotem's own bridge `watchup-bridge-rotem` started (07:42Z); Family B onboarding completed by the parent (20:03Z); Elad pressed Connect (20:06Z); **Rotem paired 17/10/2026 20:07Z**. | `connection.status=connected` for `family-b/rotem`; post-pairing probe 23/23. |
| Incident | VPS reboot 17/10 16:39Z (about 15 min outage). All containers returned by themselves; Yuli reconnected from her own session with no re-pairing. | Only heartbeat gap in the last 24 h: Yuli 16:26–16:41Z. |
| Post-DOD cleanup (18/10) | See §7. | Probe 21/21; restore proof identical. |

Exact per-gate clock times other than those above were not logged on the host. The image tag `mf-e80272a` shows that Production runs the final onboarding commit (the plan had `mf-06f8f8b`).

## 2. Final architecture

One web, one API, one Postgres. `tenant_id` is the family, `child_id` is the child. Each connected child has its own bridge, its own WhatsApp session and its own signing secret. Identity lives in two protected host files kept out of Git and out of the database:
- `/opt/watchup/api/secrets/parents.json` — each parent's `tenant_id`.
- `/opt/watchup/api/secrets/families.json` — family → children → name, age, `has_whatsapp`, optional `bridge_secret`, optional `qr_file`.

Both are `root:watchup-secrets` (gid 2001, the API user) with mode 0640. Multi-Family is on because `WATCHUP_FAMILIES_FILE` is set.

### Families (Production, 18/10/2026)

| Family (`tenant_id`) | Parents | Children |
|---|---|---|
| `family-poc` | Eldad (`eldad`), Moran (`moran`) | Yuli `child-1` — **Connected** (legacy QR file path). Emy `emy` — Not Connected, no bridge. |
| `family-b` | Elad (`elad`), Anat (`anat`) | Rotem `rotem` — **Connected**. Ofir `ofir` — Not Connected, no bridge. |

TOTP exists only for `eldad` (`WATCHUP_REQUIRE_TOTP=false`); sessions last 30 days. All five containers use `restart: unless-stopped`. Onboarding is complete for both families.

### Components

| Component | Container / image | Notes |
|---|---|---|
| Web | `watchup-web` (`nginx:alpine`) | Serves `/opt/watchup-web/site`. Traefik terminates TLS. |
| API | `watchup-api` = `watchup-api:mf-e80272a` | Env `/opt/watchup/api/app.env`; networks `watchup-internal`. Secrets mounted read-only from `/opt/watchup/api/secrets/` plus the DB CA and Yuli's QR file. |
| Database | `watchup-postgres` (`postgres:16.15`) | Schema `watchup`. Roles `watchup_owner` (owns objects), `watchup_migrator` (member of owner), `watchup_app` (NOLOGIN, DML grants), `watchup_api_login` (member of app), `watchup_admin` (superuser, maintenance only). |
| Yuli's bridge | `watchup-whatsapp-bridge` = `watchup/whatsapp-bridge:wp53-pairing` | Session `/opt/watchup/bridge/session`; secret `/opt/watchup-secrets/bridge_webhook_secret`. **Never rebuilt or restarted by this programme.** |
| Rotem's bridge | `watchup-bridge-rotem` = `watchup/whatsapp-bridge:child-rotem` | Session `/opt/watchup/bridges/rotem/store`; secret `/opt/watchup/secrets/bridge-rotem.secret`; env `/opt/watchup/bridges/rotem/bridge.env`; compose project `watchup-bridge-rotem`. |

## 3. Migrations

| | 006 `006_child_event_key.sql` | 007 `007_child_profiles.sql` |
|---|---|---|
| Purpose | Widens the events key to `(tenant_id, child_id, event_id)`. | Adds `child_profiles` and `family_onboarding` with FORCE RLS. |
| State in Production | **Applied.** | **Applied.** |
| Check | `SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='watchup.events'::regclass AND contype='p'` → `PRIMARY KEY (tenant_id, child_id, event_id)` | `SELECT to_regclass('watchup.child_profiles'), to_regclass('watchup.family_onboarding')` → both non-NULL |

**006 coupling:** the new API uses `ON CONFLICT (tenant_id, child_id, event_id)` in every mode, and the old images use `(tenant_id, event_id)`. Postgres only accepts a matching unique index, so the old and new API cannot share one schema. **Consequence: the legacy images (`wp53`…`wp74`) can no longer run against this database** (see §8).

RLS: 12 policies in schema `watchup`; FORCE RLS on `events`, `child_settings`, `tracking_words`, `parent_audit`, `child_profiles`, `family_onboarding`. `parent_sessions` and `parent_totp_steps` have no RLS (keyed by token hash / username).

## 4. Authorization (what the code enforces)

| Rule | Where |
|---|---|
| A parent's family comes from `parents.json` on the server. Unknown family → 403, no fallback in Multi-Family mode. The API refuses to start if any parent lacks a known family. | `scope_for`, `check_parents` |
| `?child_id=` must be one of the parent's family children. Foreign, unknown, empty or duplicated ids → 403. | `scope_for` |
| A bridge is identified by which registered secret verifies the HMAC. A payload `tenant_id/child_id` that differs from that binding → 403; an unknown signature → 401. Duplicate secrets make startup fail. | `binding_for_signature` |
| Profiles and onboarding live in the 007 tables under tenant RLS. Multi-Family refuses to start without 007. | `main()` |

Verified in Production on 18/10/2026 (probe `post-pairing`, 21/21): Elad and Anat see Rotem and Ofir only; Eldad and Moran see Yuli and Emy only; every cross-family dashboard and pairing request → 403; a forged signature → 401; Rotem's secret claiming Yuli, Emy or Ofir → 403.

## 5. QR on demand and session isolation

- A QR is created only when a parent presses Connect for a child that has a bridge. It is held in API memory for at most 65 s, never written to the database.
- Only the requested child's bridge is asked (it polls every ≤10 s). A connected child cannot be re-paired (409). A child with no bridge answers `no_bridge`.
- A code is valid about 60 s, then 20 s codes follow (~160 s in total). Make at most 2 attempts per hour.
- Each child's WhatsApp session is a separate directory mounted only into that child's bridge. No API, probe or tool reads a session directory.
- Pairing state is in API memory: an API restart cancels a pending pairing.
- Yuli keeps the legacy QR file path; moving her to on-demand pairing needs a bridge restart and a separate GO.

## 6. Retention, monitoring, backups (Production)

| Item | Setting |
|---|---|
| Retention | cron `10 0 * * *` `/opt/watchup/bin/retain-events.sh` on image `watchup-api:mf-e80272a`, all families, `WATCHUP_RETENTION_DAYS=3`. Event counts therefore fall as old events are purged (no event loss is implied by a lower count). |
| Connection alerts | cron `*/2` `watch-connection.sh` (Yuli: `family-poc/child-1`) and, since 18/10, `watch-connection-rotem.sh` (`family-b/rotem`, own state file `connection-alert-rotem`). Both post to the same n8n `watchup-status` webhook, so a Rotem alert looks like a Yuli alert (the payload has no child name). |
| Site | cron `1-59/2` `watch-site-health.sh`: HTTP 200/401 from `…/api/watchup/session` is healthy. |
| Backups | cron `30 2 * * *` `run-backup.sh` → encrypted `watchup-<ts>.dump.gpg`, 14 days kept. See the restore runbook. |
| Read-only check | `bash /opt/watchup/ops/stabilization_check.sh` (source: `docs/ops/stabilization_check.sh`). |

## 7. Post-DOD cleanup (18/10/2026)

| Item | Result |
|---|---|
| `/root/wv` | Removed. `creds.json` and `rotem.secret` were byte-identical copies of the authoritative files; they, the probe output files and the empty session folder were shredded. The four secret-free tools (`config.py`, `mint.py`, `probe.py`, `probe.sh`) moved to `/opt/watchup/ops/` (root, 0700) with paths updated. |
| `parents.json.pre-login-fix` | Shredded. It held only an old `eldad` hash that matches neither the live file nor the pre-Multi-Family backup. |
| Initial credentials | `/opt/watchup/secrets/family-b-initial-credentials.json` (root, 0600) kept: it holds Elad's and Anat's initial passwords and there is no secure handover or replacement method yet. |
| Active secrets | `parents.json`, `families.json`, `session_secret`, `webhook_secret`, `db_password`, `bridge-rotem.secret`, `bridge_webhook_secret`, `watchup-status-secret`, `bridge.env`: SHA-256 identical before and after. No rotation. |
| Rollback containers `wp74`, `g1`, `g2` | **Already absent** on the host at the start of this cleanup (no container with those names, running or stopped). Nothing to remove. |
| Old images | Kept on purpose (five API images of ≈210 MB each with shared layers; no running container uses them): `watchup-api:wp53/65/66/73/74`. The host's other 4 GB of reclaimable images belong to other projects and were not touched. No broad prune was run. |
| Sessions | Neither WhatsApp session was touched. Temporary 20-minute verification sessions were created and revoked. |

Intentionally retained sensitive recovery assets (all in `/opt/watchup/backups/`, root-only): `pre-mf-20261017/` (legacy `parents.json` with password hashes and TOTP seed, `g2-*.json`), plus the encrypted dumps.

## 8. Rollback procedure (what is actually possible now)

The Gate-era rollback (rename the old API back) is **closed**: the legacy images cannot insert into the 006 schema, and Family B has data.

| Situation | Action |
|---|---|
| API misbehaves after a new image | Redeploy the last known-good image `watchup-api:mf-e80272a` (kept) with `watchup-api/scripts/deploy_watchup_api.sh`, using the env of the running container (`docker inspect watchup-api`). Source for that image: `/opt/watchup/releases/mf-e80272a`. Gap ≈3–5 s; a pending pairing is cancelled. |
| Database damaged or lost | Restore from the latest dump, then re-apply ownership and GRANTs — see the restore runbook. |
| `parents.json` / `families.json` damaged | No automatic backup exists (see §9). `pre-mf-20261017/` holds only the legacy state. Restore from a manual copy, or rebuild with `/opt/watchup/ops/config.py` (needs owner approval). |
| A bridge session is lost | Sessions are intentionally not backed up. The parent re-pairs with the QR flow; the child's phone is required. |
| Web broken | Re-copy the static site from `/opt/watchup/releases/mf-e80272a/watchup-web/` into `/opt/watchup-web/site/` (no web restart). |

Never touch another tenant's directory (`kitabrief-*`, `eldo-*`, and so on).

## 9. Known limitations (accepted)

- Pairing state lives in API memory; an API restart cancels a pending pairing.
- Each query opens a new Postgres connection (~1.5 s dashboard). Upgrade path: a connection pool.
- Isolation between children inside one family is enforced by the API; RLS is per family.
- Yuli keeps the legacy QR file path.
- Backups cover the `watchup` schema only (no roles, no `parents.json`/`families.json`, no sessions). The restore runbook adds the roles and GRANTs; config files are a manual copy.
- A Rotem alert is indistinguishable from a Yuli alert in the n8n message.
- `pre-mf-20261017/` and `family-b-initial-credentials.json` stay until a secure handover exists.
- Go: 3 LID-migration tests fail on Windows only (TempDir cleanup); the bridge builds and runs on Linux.
- Old release sources remain under `/opt/watchup/releases/` (`20261005-*`, `mf-e80272a`).

## 10. Stabilization (18/10 → 23/10/2026)

Allowed: read-only monitoring and evidence-based critical fixes that are validated separately.
Frozen: features, migrations, bridge rebuilds, session changes, QR regeneration, architecture changes, refactors, unnecessary restarts.
Alert Eldad only for: a persistent bridge disconnect, ingestion failure with evidence, API or database down, backup failure, an isolation regression, repeated unexpected restarts.
No messages during quiet hours is **not** an incident while the 2-minute heartbeat is fresh.
This period is a separate milestone and is **not complete** until 23/10/2026 with daily evidence.
