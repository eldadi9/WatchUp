"""Simulated child bridges for local WatchUp. No WhatsApp: same signed contract as the Go bridge.

    python watchup-local/sim.py bridge family-b/rotem   # unpaired bridge; shows a fake QR when a parent asks
    python watchup-local/sim.py event family-b/rotem "טקסט"   # one signed message event
    python watchup-local/sim.py connected family-b/rotem    # connection.status=connected heartbeat
"""
import hashlib
import hmac
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FAMILIES_FILE = Path(__file__).resolve().parent / ".runtime" / "secrets" / "families.json"
BASE = "http://127.0.0.1:8765/api"


def bridge_secret(tenant, child):
    families = json.loads(FAMILIES_FILE.read_text(encoding="utf-8"))
    return families[tenant]["children"][child]["bridge_secret"]


def signed_post(path, body, secret):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    request = urllib.request.Request(BASE + path, data=raw, method="POST",
                                     headers={"Content-Type": "application/json", "X-WatchUp-Signature": signature})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, None


def now():
    return datetime.now(timezone.utc).isoformat()


def event(tenant, child, secret, event_id=None, event_type="message.received", account=None, payload=None,
          claim_tenant=None, claim_child=None):
    body = {
        "event_id": event_id or f"sim-{secrets.token_hex(6)}", "type": event_type, "source": "whatsapp-bridge",
        "source_timestamp": now(), "tenant_id": claim_tenant or tenant, "child_id": claim_child or child,
        "account": account or {"chat_jid": "972500000001@s.whatsapp.net", "chat_type": "direct",
                               "sender": "972500000001", "display_name": "מספר לא מוכר", "is_recognized": False},
        "payload": payload or {"content": "הודעת בדיקה מקומית", "message_id": event_id},
    }
    return signed_post("/watchup/events", body, secret)


def report(tenant, child, secret, state, code="", claim_child=None, sent_at=None):
    body = {"tenant_id": tenant, "child_id": claim_child or child, "state": state, "code": code, "sent_at": sent_at or now()}
    return signed_post("/watchup/bridge/pairing", body, secret)


def run_bridge(tenant, child, poll_seconds=3, codes=3, code_seconds=8):
    """The Go bridge's on-demand loop: idle until asked, then rotate codes, then pair."""
    secret = bridge_secret(tenant, child)
    print(f"simulated bridge {tenant}/{child}: unpaired, waiting for a parent request")
    while True:
        status, body = report(tenant, child, secret, "unpaired")
        if status != 200:
            print("report rejected", status)
        elif body["pairing_requested"]:
            for index in range(codes):
                code = f"2@SIMULATED-{child}-{index}-{secrets.token_hex(8)}"
                status, body = report(tenant, child, secret, "qr", code)
                print(f"QR code {index + 1} pushed")
                if not body or not body["pairing_requested"]:
                    print("pairing cancelled by parent")
                    break
                time.sleep(code_seconds)
            else:
                report(tenant, child, secret, "paired")
                event(tenant, child, secret, event_type="connection.status", account={"status": "connected"}, payload={})
                print("paired (simulated scan) and connected")
                return
        time.sleep(poll_seconds)


if __name__ == "__main__":
    command, target = sys.argv[1], sys.argv[2]
    tenant, child = target.split("/")
    if command == "bridge":
        run_bridge(tenant, child)
    elif command == "event":
        print(event(tenant, child, bridge_secret(tenant, child), payload={"content": sys.argv[3]}))
    elif command == "connected":
        print(event(tenant, child, bridge_secret(tenant, child), event_type="connection.status",
                    account={"status": "connected"}, payload={}))
    else:
        sys.exit(__doc__)
