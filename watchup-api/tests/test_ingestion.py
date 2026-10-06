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

    def test_dashboard_includes_latest_connection_status_outside_recent_window(self):
        self.store.insert(
            {
                "event_id": "conn-connected",
                "type": "connection.status",
                "source": "bridge",
                "source_timestamp": "2026-10-06T00:00:00+00:00",
                "tenant_id": "tenant-a",
                "child_id": "child-a",
                "account": {"status": "connected"},
                "payload": {},
            },
            datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc),
        )
        for index in range(55):
            self.store.insert(
                {
                    "event_id": f"msg-{index}",
                    "type": "message.received",
                    "source": "bridge",
                    "source_timestamp": "2026-10-06T01:00:00+00:00",
                    "tenant_id": "tenant-a",
                    "child_id": "child-a",
                    "account": {"sender": "972501234567"},
                    "payload": {"content": "x"},
                },
                datetime(2026, 10, 6, 1, index, tzinfo=timezone.utc),
            )
        status, _, raw = self.get_dashboard(self.dashboard_token)
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["connection"]["account"]["status"], "connected")
        self.assertEqual(len(payload["events"]), 50)

    def test_dashboard_keeps_groups_outside_the_recent_event_window(self):
        group = self.event(event_id="group-old")
        group["type"] = "group.snapshot"
        group["account"] = {"chat_jid": "group@g.us"}
        group["payload"] = {"name": "קבוצה", "participants": []}
        self.store.insert(group, datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
        for index in range(55):
            self.store.insert(self.event(event_id=f"recent-{index}"), datetime(2026, 10, 6, 1, index, tzinfo=timezone.utc))
        status, _, raw = self.get_dashboard(self.dashboard_token)
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertNotIn("group-old", [event["event_id"] for event in payload["events"]])
        self.assertEqual([group["event_id"] for group in payload["groups"]], ["group-old"])

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


class ParentAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = app.EventStore(str(Path(self.tmp.name) / "events.db"))
        parent = app.ParentAuth.password_record("correct horse battery staple", bytes.fromhex("11" * 16))
        parent["totp_secret"] = "JBSWY3DPEHPK3PXP"
        self.auth = app.ParentAuth({"eldad": parent, "parent-two": parent}, "s" * 32, ttl_seconds=60)
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            app.make_handler(
                self.store, "synthetic-test-secret", "tenant-a", "child-a",
                dashboard_token="", parent_auth=self.auth,
            ),
        )
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.db.close()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, cookie="", csrf="", extra_headers=None):
        raw = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
        headers = {}
        if raw is not None:
            headers.update({"Content-Type": "application/json", "Content-Length": str(len(raw))})
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-WatchUp-CSRF"] = csrf
        headers.update(extra_headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        body = response.read()
        result = response.status, response.getheader("Set-Cookie"), body
        connection.close()
        return result

    def credentials(self, username="eldad", password="correct horse battery staple"):
        return {"username": username, "password": password,
                "totp": self.auth._totp("JBSWY3DPEHPK3PXP", int(__import__("time").time() // 30))}

    def test_parent_session_uses_secure_http_only_cookie_and_can_logout(self):
        status, cookie, _ = self.request(
            "POST", "/watchup/session",
            self.credentials(),
        )
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Strict", cookie)
        session_cookie = cookie.split(";", 1)[0]
        self.assertEqual(self.request("GET", "/watchup/dashboard", cookie=session_cookie)[0], 200)
        csrf = json.loads(_)["csrf_token"]
        status, _, session_body = self.request("GET", "/watchup/session", cookie=session_cookie)
        self.assertEqual(status, 200)
        restored_csrf = json.loads(session_body)["csrf_token"]
        self.assertNotEqual(csrf, restored_csrf)
        self.assertEqual(self.request("DELETE", "/watchup/session", cookie=session_cookie, csrf=csrf)[0], 403)
        csrf = restored_csrf
        self.assertEqual(self.request("DELETE", "/watchup/session", cookie=session_cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.request("GET", "/watchup/dashboard", cookie=session_cookie)[0], 401)
        self.assertEqual(self.request("GET", "/watchup/session", cookie=session_cookie)[0], 401)

    def test_failed_logins_are_rate_limited_without_logging_passwords(self):
        for _ in range(5):
            self.assertEqual(
                self.request("POST", "/watchup/session", {"username": "eldad", "password": "wrong"})[0],
                401,
            )
        self.assertEqual(
            self.request("POST", "/watchup/session", {"username": "eldad", "password": "wrong"})[0],
            429,
        )
        self.assertNotIn("wrong", json.dumps(self.auth.audit_log))

    def test_untrusted_forwarded_for_cannot_choose_the_rate_limit_identity(self):
        self.assertEqual(self.request(
            "POST", "/watchup/session", {"username": "eldad", "password": "wrong"},
            extra_headers={"X-Forwarded-For": "198.51.100.9"},
        )[0], 401)
        self.assertIn("127.0.0.1", self.auth.attempts)
        self.assertNotIn("198.51.100.9", self.auth.attempts)

    def test_trusted_proxy_rejects_multi_hop_forwarded_for(self):
        self.server.shutdown()
        self.server.server_close()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(
            self.store, "synthetic-test-secret", "tenant-a", "child-a",
            parent_auth=self.auth, trusted_proxy_ips=("127.0.0.1",),
        ))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.assertEqual(self.request("POST", "/watchup/session", {"username": "eldad", "password": "wrong"},
                                      extra_headers={"X-Forwarded-For": "198.51.100.9, 203.0.113.7"})[0], 401)
        self.assertIn("127.0.0.1", self.auth.attempts)
        self.assertNotIn("198.51.100.9", self.auth.attempts)
        self.assertEqual(self.request("POST", "/watchup/session", {"username": "eldad", "password": "wrong"},
                                      extra_headers={"X-Forwarded-For": "198.51.100.9"})[0], 401)
        self.assertIn("198.51.100.9", self.auth.attempts)

    def test_totp_replay_csrf_and_family_deletion_are_rejected_or_enforced(self):
        payload = self.credentials()
        status, cookie, body = self.request("POST", "/watchup/session", payload)
        self.assertEqual(status, 200)
        self.assertEqual(self.request("POST", "/watchup/session", payload)[0], 401)
        session_cookie = cookie.split(";", 1)[0]
        self.assertEqual(self.request("DELETE", "/watchup/session", cookie=session_cookie)[0], 403)
        event = {"event_id": "delete-me", "type": "message.received", "source": "synthetic", "source_timestamp": datetime.now(timezone.utc).isoformat(), "tenant_id": "tenant-a", "child_id": "child-a", "account": {}, "payload": {}}
        self.store.insert(event, datetime.now(timezone.utc))
        csrf = json.loads(body)["csrf_token"]
        self.store.set_tracking_words("tenant-a", "child-a", ["בדיקה"])
        self.assertEqual(self.request("POST", "/watchup/family", cookie=session_cookie, csrf=csrf)[0], 200)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events").fetchone()[0], 0)
        self.assertEqual(self.store.list_tracking_words("tenant-a", "child-a"), [])

    def test_tracking_words_are_validated_persisted_and_shared_between_parents(self):
        first = self.request("POST", "/watchup/session", self.credentials("eldad"))
        second = self.request("POST", "/watchup/session", self.credentials("parent-two"))
        first_cookie = first[1].split(";", 1)[0]
        second_cookie = second[1].split(";", 1)[0]
        first_csrf = json.loads(first[2])["csrf_token"]
        self.assertEqual(self.request(
            "POST", "/watchup/tracking-words", {"words": [" חיים שלי ", "חיים שלי", "\u202eאהבה"]},
            cookie=first_cookie, csrf=first_csrf,
        )[0], 200)
        status, _, dashboard = self.request("GET", "/watchup/dashboard", cookie=second_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(dashboard)["tracking_words"], ["חיים שלי", "אהבה"])
        self.assertEqual(self.request(
            "POST", "/watchup/tracking-words", {"words": ["x" * 41]},
            cookie=first_cookie, csrf=first_csrf,
        )[0], 400)
        self.assertEqual(self.request(
            "POST", "/watchup/tracking-words", {"words": ["מילה"]}, cookie=first_cookie,
        )[0], 403)

    def test_both_parents_see_the_same_child_and_cannot_read_another_tenant(self):
        event = {
            "event_id": "shared-child",
            "type": "message.received",
            "source": "synthetic",
            "source_timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": "tenant-a",
            "child_id": "child-a",
            "account": {},
            "payload": {"content": "בדיקה"},
        }
        self.store.insert(event, datetime.now(timezone.utc))
        first = self.request("POST", "/watchup/session", self.credentials("eldad"))
        second = self.request("POST", "/watchup/session", self.credentials("parent-two"))
        self.assertEqual(first[0], 200)
        self.assertEqual(second[0], 200)
        first_cookie = first[1].split(";", 1)[0]
        second_cookie = second[1].split(";", 1)[0]
        self.assertNotEqual(first_cookie, second_cookie)
        for cookie in (first_cookie, second_cookie):
            status, _, body = self.request("GET", "/watchup/dashboard", cookie=cookie)
            payload = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(payload["child_id"], "child-a")
            self.assertEqual([item["event_id"] for item in payload["events"]], ["shared-child"])
            self.assertNotIn("tenant-b", body.decode("utf-8"))

    def test_durable_parent_audit_on_login_dashboard_and_audit_endpoint(self):
        status, cookie, body = self.request("POST", "/watchup/session", self.credentials())
        self.assertEqual(status, 200)
        session_cookie = cookie.split(";", 1)[0]
        csrf = json.loads(body)["csrf_token"]
        self.assertEqual(self.request("GET", "/watchup/dashboard", cookie=session_cookie)[0], 200)
        status, _, audit_body = self.request("GET", "/watchup/audit", cookie=session_cookie)
        self.assertEqual(status, 200)
        entries = json.loads(audit_body)["entries"]
        actions = {entry["action"] for entry in entries}
        self.assertIn("login_succeeded", actions)
        self.assertIn("view_dashboard", actions)
        self.assertIn("view_audit", actions)
        self.assertEqual(self.request("DELETE", "/watchup/session", cookie=session_cookie, csrf=csrf)[0], 200)
        stored = self.store.list_parent_audit("tenant-a")
        self.assertIn("logout", {row["action"] for row in stored})

    def test_owner_approved_poc_can_use_password_only_with_long_session(self):
        auth = app.ParentAuth(
            {"eldad": self.auth.parents["eldad"]},
            "s" * 32,
            ttl_seconds=2592000,
            require_totp=False,
        )
        session, result = auth.login(
            "Eldad", "correct horse battery staple", "", "127.0.0.1", now=1000,
        )
        self.assertEqual(result, "ok")
        self.assertIsNotNone(session)
        token, _csrf = session
        self.assertTrue(auth.validate(token, now=2592999))
        self.assertFalse(auth.validate(token, now=2593001))

    def test_sqlite_session_survives_auth_reconstruction_and_retention_purges_old_events(self):
        auth_db = str(Path(self.tmp.name) / "auth.db")
        store = app.SQLiteAuthStore(auth_db)
        parents = self.auth.parents
        first = app.ParentAuth(parents, "s" * 32, session_store=store)
        token, _csrf = first.login("parent-two", "correct horse battery staple", first._totp("JBSWY3DPEHPK3PXP", int(__import__("time").time() // 30)), "127.0.0.1")[0]
        restarted = app.ParentAuth(parents, "s" * 32, session_store=app.SQLiteAuthStore(auth_db))
        self.assertTrue(restarted.validate(token))
        self.store.insert({"event_id": "old", "type": "x", "source": "x", "source_timestamp": "2026-01-01T00:00:00+00:00", "tenant_id": "tenant-a", "child_id": "child-a", "account": {}, "payload": {}}, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(self.store.purge_before(datetime(2026, 2, 1, tzinfo=timezone.utc), "tenant-a"), 1)
        store.close()
        restarted.session_store.close()


if __name__ == "__main__":
    unittest.main()
