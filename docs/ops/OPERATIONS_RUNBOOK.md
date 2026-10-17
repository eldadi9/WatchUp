# WatchUp — Operations Runbook

For the person on call. Everything here is read-only unless a step says **needs owner approval**.
Access: `ssh hostinger-vps` (root). Containers: `watchup-web`, `watchup-api`, `watchup-postgres`, `watchup-whatsapp-bridge` (Yuli), `watchup-bridge-rotem` (Rotem). Architecture: [../MULTI_FAMILY_PRODUCTION_PLAN.md](../MULTI_FAMILY_PRODUCTION_PLAN.md).

Golden rules:
1. No WhatsApp messages are needed to test anything. Never send, edit or delete WhatsApp content.
2. Never create a pairing request, delete a session directory, or run `docker system prune` / `docker compose down -v`.
3. **No messages is not an incident.** The bridges send a `connection.status` heartbeat every ~2 minutes. Fresh heartbeat + status `connected` = healthy, even with no messages for hours.

## 0. One-command overview

```bash
bash /opt/watchup/ops/stabilization_check.sh      # source: docs/ops/stabilization_check.sh
```
It prints `OK` / `WARN` / `FAIL` for containers and restart counts, the public site, the database, each child's heartbeat and last event, nginx 5xx, API errors, disk, memory and backup age. It changes nothing.

## 1. Web and API health

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://watchup.srv1282987.hstgr.cloud/api/watchup/session   # 401 = healthy, 200 also fine
docker ps --filter name=watchup --format '{{.Names}} {{.Status}}'
docker logs --since 1h watchup-web 2>&1 | grep -c -E '" 5[0-9][0-9] '      # expect 0
docker logs --since 1h watchup-api  2>&1 | grep -i -E 'traceback|error' | tail
```
A single `000` from curl is a network blip; retry three times before calling it an outage. `watch-site-health.sh` (cron, every 2 min) alerts on a persistent failure and may restart Traefik by design. That automatic Traefik restart is a standing, owner-approved exception to the freeze in §11.

## 2. Is Yuli connected?  3. Is Rotem connected?

```bash
docker exec -i watchup-postgres psql -U watchup_admin -d watchup -qAt -c "
select tenant_id||'/'||child_id, account->>'status', round(extract(epoch from now()-received_at)) as age_s
from (select distinct on (tenant_id, child_id) * from watchup.events where event_type='connection.status'
      order by tenant_id, child_id, received_at desc) t"
```
Healthy: `connected` with `age_s` ≤ 360. Yuli is `family-poc/child-1`, Rotem is `family-b/rotem`. Emy and Ofir have no bridge and no row — "Not Connected" is correct for them.

Also useful (does not print message content; do not paste logs into tickets):
`docker logs --since 10m watchup-whatsapp-bridge 2>&1 | grep -c .` — the bridge is alive if it keeps writing lines.

## 4. Ingestion freshness

```bash
docker exec -i watchup-postgres psql -U watchup_admin -d watchup -qAt -c "
select tenant_id||'/'||child_id,
  round(extract(epoch from now()-max(received_at) filter (where event_type='connection.status'))) as heartbeat_age_s,
  round(extract(epoch from now()-max(received_at) filter (where event_type<>'connection.status'))) as last_event_age_s
from watchup.events group by 1 order by 1"
```

| heartbeat age | last event age | Verdict |
|---|---|---|
| ≤ 360 s | any | Healthy. Old events = quiet hours. |
| > 360 s, bridge container running | any | Bridge or API→DB path broken: go to §5. |
| > 360 s, bridge container not running | any | Container down: §7. |

Event retention is 3 days, so event totals shrink over time by design.

## 5. Diagnose "Disconnected" (decision order)

1. `docker ps -a --filter name=watchup` — is the bridge running? Restart count (`docker inspect -f '{{.RestartCount}}' <name>`)?
2. Latest status (§2/§3):
   - `connected` and fresh → nothing is wrong; the parent screen may be cached (reload).
   - `disconnected` → temporary network loss; the bridge reconnects by itself. Wait 5 minutes.
   - `relink_required` → WhatsApp logged the linked device out. **Needs a new pairing** with the child's phone (§6). Do not try to fix it from the server.
   - stale heartbeat → `docker logs --tail 50 <bridge>` (errors only), then `curl` the site (§1). If the API is down, bridges cannot deliver.
3. Is the API healthy and the database reachable? (`stabilization_check.sh`.)
4. If events arrive for one child but not the other, compare the two children's heartbeats; do not touch the healthy bridge.
5. Alerts: `watch-connection.sh` (Yuli) and `watch-connection-rotem.sh` (Rotem) post to the same n8n webhook when the state changes. The message does not name the child — check §2/§3 to see which one.

## 6. An expired QR

A pairing code lives about 60 s, then 20 s codes follow (~160 s in total). It is held only in API memory.
- Expired or never scanned: the parent presses **Connect** again in the app. The new code appears within ~10 s. Maximum 2 attempts per hour.
- Do **not** restart the bridge or the API to refresh a QR. An API restart cancels any pending pairing.
- A connected child answers 409 to Connect. A child without a bridge answers `no_bridge`.
- Pairing needs the child's phone (WhatsApp → Linked devices → Link a device). Only the owning family sees the QR.

## 7. Restart only the right service (needs owner approval in production)

| Symptom | Restart | Impact |
|---|---|---|
| Rotem's bridge down or wedged | `docker restart watchup-bridge-rotem` | Rotem only. Its session volume is kept; it reconnects from its own session. |
| Yuli's bridge down or wedged | `docker restart watchup-whatsapp-bridge` | Yuli only; same behaviour. Her image `wp53-pairing` must not be rebuilt. |
| API wedged (5xx, DB errors) | `docker restart watchup-api` | 3–5 s ingestion gap (events inside it are lost; heartbeats recover), pending pairing cancelled. |
| Site unreachable but containers healthy | `watch-site-health.sh` restarts Traefik by itself | Affects every project on the host — prefer to wait for it. |
| Database | Avoid. Check disk/memory first. | Every container depends on it. |

Never restart both bridges, or anything, "to see if it helps". After any restart run §0 and §4 and record the time.

## 8. Recover from a backup

See [RESTORE_RUNBOOK.md](RESTORE_RUNBOOK.md): section A verifies a backup safely; section B (needs owner approval) restores. The GRANTs step is mandatory.

## 9. Escalate

Notify Eldad for: a bridge that stays disconnected or stale > 30 minutes with the container running; events missing while heartbeats show an ingestion failure; API or database down; backup older than 26 h; any sign a parent can see another family (treat as a security incident, stop and report); repeated unexpected restarts (restart count rising).
Do not notify for: no messages, one network blip, a single connection flap that heals.
Include: UTC time, which child, §0 output, the last heartbeat age, container restart counts. Never include passwords, tokens, secrets or message text.

## 10. Daily stabilization checklist (18/10 → 23/10/2026)

1. §0 overview — all `OK`.
2. Yuli and Rotem `connected`, heartbeats fresh; Emy and Ofir absent.
3. Restart counts: 0 expected (baseline 18/10: all five containers 0, started 16:39Z). A rise is a WARN to investigate.
4. Newest backup < 26 h and the `backup.log` shows a new file.
5. Disk < 85 %, memory available > 500 MB.
6. Write the result (one line, UTC time) in `.ai/andy/current.json` `validation` or the stabilization log. Do not call the period complete before 23/10/2026.

## 11. Freeze

During the five days: no features, migrations, bridge rebuilds, session changes, QR regeneration, architecture changes, refactors or unnecessary restarts. A critical fix needs evidence, owner approval and its own validation.
