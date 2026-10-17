#!/bin/bash
# WatchUp read-only health check. Run on the VPS as root: bash /opt/watchup/ops/stabilization_check.sh
# Prints OK/WARN/FAIL per item and never writes, restarts or sends anything.
# A quiet child (no messages) is OK while its 2-minute connection heartbeat is fresh; a stale heartbeat is FAIL.
PSQL="docker exec -i watchup-postgres psql -U watchup_admin -d watchup -qAt"
say() { printf '%-5s %s\n' "$1" "$2"; }

for c in watchup-api watchup-web watchup-postgres watchup-whatsapp-bridge watchup-bridge-rotem; do
  info=$(docker inspect -f '{{.State.Running}} {{.RestartCount}} {{.State.StartedAt}}' "$c" 2>/dev/null) || { say FAIL "$c missing"; continue; }
  set -- $info
  if [ "$1" != true ]; then say FAIL "$c not running"; elif [ "$2" -gt 0 ]; then say WARN "$c restarts=$2 since $3"; else say OK "$c running (started $3)"; fi
done

for try in 1 2 3; do  # one blip is not an incident
  code=$(curl -sS -m 12 -o /dev/null -w '%{http_code}' https://watchup.srv1282987.hstgr.cloud/api/watchup/session 2>/dev/null)
  case "$code" in 200|401) break ;; esac; sleep 3
done
case "$code" in 200|401) say OK "site/API via Traefik HTTP $code" ;; *) say FAIL "site/API HTTP $code" ;; esac
$PSQL -c 'select 1' >/dev/null 2>&1 && say OK "database reachable" || say FAIL "database unreachable"

$PSQL -F ' ' -c "
select tenant_id||'/'||child_id,
  coalesce(extract(epoch from now()-max(received_at) filter (where event_type='connection.status'))::int, 999999),
  coalesce(extract(epoch from now()-max(received_at) filter (where event_type<>'connection.status'))::int, 999999)
from watchup.events group by tenant_id, child_id order by 1" | while read child hb ev; do
  status=$($PSQL -c "select coalesce(account->>'status','?') from watchup.events where event_type='connection.status' and tenant_id||'/'||child_id='$child' order by received_at desc limit 1" </dev/null)
  if [ "$status" = connected ] && [ "$hb" -le 360 ]; then say OK "$child connected, heartbeat ${hb}s ago, last event ${ev}s ago (quiet is normal)"
  else say FAIL "$child status=$status heartbeat ${hb}s ago"; fi
done

n5xx=$(docker logs --since 1h watchup-web 2>&1 | grep -c -E '" 5[0-9][0-9] ')
[ "$n5xx" -eq 0 ] && say OK "nginx 5xx last hour: 0" || say WARN "nginx 5xx last hour: $n5xx"
nerr=$(docker logs --since 1h watchup-api 2>&1 | grep -c -i -E 'traceback|error')
[ "$nerr" -eq 0 ] && say OK "API errors last hour: 0" || say WARN "API error lines last hour: $nerr"

use=$(df --output=pcent / | tail -1 | tr -dc 0-9)
[ "$use" -lt 85 ] && say OK "disk ${use}% used" || say WARN "disk ${use}% used"
avail=$(free -m | awk '/Mem:/{print $7}')
[ "$avail" -gt 500 ] && say OK "memory available ${avail} MB" || say WARN "memory available ${avail} MB"

newest=$(ls -t /opt/watchup/backups/watchup-*.dump.gpg 2>/dev/null | head -1)
if [ -z "$newest" ]; then say FAIL "no backup file found"; else
  age=$(( ( $(date +%s) - $(stat -c %Y "$newest") ) / 3600 ))
  [ "$age" -le 26 ] && say OK "newest backup ${age}h old" || say FAIL "newest backup ${age}h old"
fi
