import http.client
import importlib.util
import json
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer


APP_PATH = Path(__file__).parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("watchup_app", APP_PATH)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class IngestionTests(unittest.TestCase):
    secret = "synthetic-test-secret"
    dashboard_token = "synthetic-dashboard-token-123"

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = app.EventStore(str(Path(self.tmp.name) / "events.db"))
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            app.make_handler(
                self.store, self.secret, "tenant-a", "child-a", 512, self.dashboard_token
            ),
        )
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.db.close()
        self.tmp.cleanup()

    def event(self, tenant="tenant-a", child="child-a", event_id="event-1"):
        return {
            "event_id": event_id,
            "type": "message.received",
            "source": "whatsapp-bridge",
            "source_timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant,
            "child_id": child,
            "account": {"chat_jid": "synthetic@example.test"},
            "payload": {"content": "בדיקה"},
        }

    def post(self, body, signature=True):
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "Content-Length": str(len(raw))}
        if signature is True:
            headers["X-WatchUp-Signature"] = app.signature_for(self.secret, raw)
        elif signature == "bad":
            headers["X-WatchUp-Signature"] = "sha256=" + "0" * 64
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("POST", "/watchup/events", raw, headers)
        response = conn.getresponse()
        response.read()
        conn.close()
        return response.status

    def get_dashboard(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("GET", "/watchup/dashboard", headers=headers)
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response.status, response.getheader("Cache-Control"), body

    def test_valid_event_is_stored_with_latency(self):
        event = self.event()
        self.assertEqual(self.post(event), 202)
        row = self.store.db.execute("SELECT latency_ms, received_at FROM events").fetchone()
        self.assertIsNotNone(row)
        self.assertGreaterEqual(row[0], 0)
        self.assertTrue(row[1])

    def test_missing_or_bad_signature_is_rejected(self):
        self.assertEqual(self.post(self.event(), signature=False), 401)
        self.assertEqual(self.post(self.event(event_id="bad"), signature="bad"), 401)

    def test_duplicate_is_idempotent_within_tenant(self):
        event = self.event()
        self.assertEqual(self.post(event), 202)
        self.assertEqual(self.post(event), 200)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)

    def test_server_identity_rejects_payload_mismatch_before_storage(self):
        self.assertEqual(self.post(self.event("tenant-b", "child-a", "wrong-tenant")), 403)
        self.assertEqual(self.post(self.event("tenant-a", "child-b", "wrong-child")), 403)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events").fetchone()[0], 0)

    def test_payload_limit_is_rejected_before_processing(self):
        event = self.event(event_id="large")
        event["payload"] = {"content": "x" * 600}
        self.assertEqual(self.post(event), 413)

    def test_dashboard_requires_token_and_returns_only_current_child_events(self):
        self.assertEqual(self.post(self.event(event_id="visible")), 202)
        self.assertEqual(self.get_dashboard()[0], 401)
        self.assertEqual(self.get_dashboard("wrong-token")[0], 401)
        status, cache_control, raw = self.get_dashboard(self.dashboard_token)
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(cache_control, "no-store")
        self.assertEqual(payload["child_id"], "child-a")
        self.assertEqual([event["event_id"] for event in payload["events"]], ["visible"])


if __name__ == "__main__":
    unittest.main()
