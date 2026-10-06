# WhatsApp Bridge VPS runbook

The bridge publishes no host ports. It joins the existing internal-only `watchup-internal` network for signed events to `http://watchup-api:8769/watchup/events`, plus a dedicated `watchup-bridge-egress` network for the outbound WhatsApp Web connection. The API and PostgreSQL remain attached only to `watchup-internal`.

## Deploy

Create the internal `watchup-internal` network and the dedicated outbound `watchup-bridge-egress` network if they do not already exist. Do not attach the API or PostgreSQL to the egress network. Create a root-readable secret file outside the repository and set `WATCHUP_WEBHOOK_SECRET_FILE_HOST` to that absolute host path. Set `WATCHUP_TENANT_ID` and `WATCHUP_CHILD_ID` in the protected deployment environment. The secret must be the same value supplied to WatchUp API. Set `WATCHUP_BRIDGE_SESSION_DIR_HOST` to a directory on encrypted host storage, owned by UID 10001 and inaccessible to other users. This directory holds the WhatsApp session database; the bridge does not encrypt it itself.

From this directory, run `docker compose -f compose.watchup-vps.yml up -d --build`. Do not expose a bridge port and do not put credentials in the compose file. Pairing or session recovery is owner-operated; this runbook does not create or copy a session.

## Verify

Confirm the container is running, attached only to `watchup-internal`, has no published ports, and uses a read-only root filesystem. The explicit privacy mode sends live messages through the signed API path without a bridge message database, media downloads, history sync persistence, or generic webhooks. An inbound test message produces one signed `message.received` event. Connection changes produce `connection.status` events (`connected`, `disconnected`, or `relink_required`) for parent alerts. Do not inspect message content in logs. Existing files in a reused session directory are not removed automatically.

## Rollback

Stop and remove only the bridge container: `docker compose -f compose.watchup-vps.yml down`. This preserves the protected session directory. Restore the last known-good bridge image/configuration and start it with the same session directory and secret mount. WatchUp family deletion and retention cover API events and parent sessions only; they do not erase this WhatsApp session directory or external backups.

## Full family deletion

The dashboard deletion action removes WatchUp events and parent sessions only. A full deletion that also disconnects WhatsApp is an explicit owner-operated procedure: stop the WatchUp bridge, verify the exact value of `WATCHUP_BRIDGE_SESSION_DIR_HOST`, remove only that protected WatchUp session directory, and delete any WatchUp backup copies according to the retention policy. Never reuse or remove a session directory belonging to another project. Restarting the bridge after this procedure requires a new QR pairing.
