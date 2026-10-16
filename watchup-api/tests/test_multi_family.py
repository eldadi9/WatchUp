"""Multi-Family isolation: parents, children, bridges, settings, and on-demand pairing.

Family A: eldad, moran -> child-1 (Yuli, production ids).
Family B: elad, anat   -> rotem, son-test.
"""
import base64
import http.client
import importlib.util
import json
import threading
import time
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory


APP_PATH = Path(__file__).parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("watchup_app_mf", APP_PATH)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)

PASSWORD = "synthetic local password"
SECRETS = {
    ("family-poc", "child-1"): "bridge-secret-yuli-0000000000000000",
    ("family-b", "rotem"): "bridge-secret-rotem-000000000000000",
    ("family-b", "son-test"): "bridge-secret-son-test-000000000000",
}
FAMILIES = {
    "family-poc": {"children": {"child-1": {"name": "יולי", "bridge_secret": SECRETS[("family-poc", "child-1")]}}},
    "family-b": {"children": {
        "rotem": {"name": "רותם", "bridge_secret": SECRETS[("family-b", "rotem")]},
        "son-test": {"name": "בן בדיקה", "bridge_secret": SECRETS[("family-b", "son-test")]},
    }},
}
PARENT_FAMILY = {"eldad": "family-poc", "moran": "family-poc", "elad": "family-b", "anat": "family-b"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class RegistryValidationTests(unittest.TestCase):
    def test_valid_registry_lists_children_in_order(self):
        registry = app.FamilyRegistry.validate(json.loads(json.dumps(FAMILIES)))
        self.assertEqual([c["child_id"] for c in registry.children("family-b")], ["rotem", "son-test"])
        self.assertEqual(registry.children("family-unknown"), [])

    def test_invalid_registries_fail_closed(self):
        bad = [
            {},
            {"family-a": {"children": {}}},
            {"Family A": {"children": {"x": {"bridge_secret": "s" * 32}}}},
            {"family-a": {"children": {"x": {"bridge_secret": "short"}}}},
            {"family-a": {"children": {"x": {"bridge_secret": "s" * 32}, "y": {"bridge_secret": "s" * 32}}}},
            {"family-a": {"children": {"x": {"bridge_secret": "s" * 32}}},
             "family-b": {"children": {"y": {"bridge_secret": "s" * 32}}}},
        ]
        for families in bad:
            with self.subTest(families=families), self.assertRaises(ValueError):
                app.FamilyRegistry.validate(families)

    def test_parent_without_known_family_fails_startup(self):
        registry = app.FamilyRegistry.validate(json.loads(json.dumps(FAMILIES)))
        registry.check_parents({"eldad": {"tenant_id": "family-poc"}})
        for parents in ({"ghost": {}}, {"ghost": {"tenant_id": "family-x"}}):
            with self.subTest(parents=parents), self.assertRaises(ValueError):
                registry.check_parents(parents)

    def test_main_refuses_multi_family_without_parent_accounts(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "families.json"
            path.write_text(json.dumps(FAMILIES), encoding="utf-8")
            env = {"WATCHUP_FAMILIES_FILE": str(path), "WATCHUP_EVENT_STORE": "sqlite",
                   "WATCHUP_EVENTS_DB": str(Path(tmp) / "e.db")}
            with unittest.mock.patch.dict(app.os.environ, env, clear=True), self.assertRaises(SystemExit):
                app.main()

    def test_main_refuses_duplicate_bridge_secret_in_families_file(self):
        secret = "s" * 32
        families = {"fam-a": {"children": {"x": {"bridge_secret": secret}, "y": {"bridge_secret": secret}}}}
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "families.json"
            path.write_text(json.dumps(families), encoding="utf-8")
            env = {"WATCHUP_FAMILIES_FILE": str(path), "WATCHUP_EVENT_STORE": "sqlite",
                   "WATCHUP_EVENTS_DB": str(Path(tmp) / "e.db")}
            with unittest.mock.patch.dict(app.os.environ, env, clear=True), self.assertRaises(SystemExit):
                app.main()

    def _main_postgres(self, missing):
        record = app.ParentAuth.password_record(PASSWORD)
        parents = {name: {**record, "tenant_id": tenant} for name, tenant in PARENT_FAMILY.items()}
        auth = app.ParentAuth(parents, "s" * 32, ttl_seconds=600, require_totp=False)
        store = unittest.mock.MagicMock()
        store.missing_tables.return_value = missing
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "families.json"
            path.write_text(json.dumps(FAMILIES), encoding="utf-8")
            env = {"WATCHUP_FAMILIES_FILE": str(path), "WATCHUP_EVENT_STORE": "postgres",
                   "WATCHUP_PARENTS_FILE": "parents.json", "WATCHUP_SESSION_SECRET_FILE": "session.secret"}
            with unittest.mock.patch.dict(app.os.environ, env, clear=True), \
                    unittest.mock.patch.object(app.PostgresEventStore, "from_environment", return_value=store), \
                    unittest.mock.patch.object(app.ParentAuth, "from_files", return_value=auth), \
                    unittest.mock.patch.object(app, "PostgresAuthStore"), \
                    unittest.mock.patch.object(app, "ThreadingHTTPServer") as server:
                try:
                    app.main()
                finally:
                    constructed = server.called
        return store, constructed

    def test_main_refuses_postgres_multi_family_without_migration(self):
        with self.assertRaises(SystemExit):
            self._main_postgres(["watchup.child_profiles"])

    def test_main_starts_postgres_multi_family_when_tables_exist(self):
        store, constructed = self._main_postgres([])
        store.missing_tables.assert_called_once_with(("watchup.child_profiles", "watchup.family_onboarding"))
        self.assertTrue(constructed)


class PairingBoardTests(unittest.TestCase):
    def test_lifecycle_request_qr_expiry_timeout_and_cancel(self):
        board = app.PairingBoard()
        key = ("family-b", "rotem")
        self.assertEqual(board.view(key, 0)["state"], "not_connected")
        self.assertFalse(board.bridge_report(key, "unpaired", "", 1))
        board.request(key, 10)
        self.assertEqual(board.view(key, 11)["state"], "requested")
        self.assertEqual(board.view(key, 10 + board.BRIDGE_STALE + 1)["state"], "bridge_unavailable")
        self.assertTrue(board.bridge_report(key, "qr", "code-1", 20))
        self.assertEqual(board.view(key, 21), {"state": "waiting", "code": "code-1"})
        self.assertEqual(board.view(key, 20 + board.QR_TTL + 1)["state"], "bridge_unavailable")
        self.assertFalse(board.bridge_report(key, "timeout", "", 200))
        self.assertEqual(board.view(key, 201)["state"], "timeout")
        board.request(key, 300)
        board.cancel(key)
        self.assertFalse(board.bridge_report(key, "unpaired", "", 301))
        self.assertEqual(board.view(key, 302)["state"], "not_connected")
        board.request(key, 400)
        self.assertEqual(board.view(key, 400 + board.REQUEST_TTL + 1)["state"], "not_connected")

    def test_unrequested_qr_is_dropped(self):
        board = app.PairingBoard()
        self.assertFalse(board.bridge_report(("family-b", "rotem"), "qr", "unsolicited", 1))
        self.assertEqual(board.view(("family-b", "rotem"), 2)["state"], "not_connected")


class MultiFamilyApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = app.EventStore(str(Path(self.tmp.name) / "events.db"))
        record = app.ParentAuth.password_record(PASSWORD)
        parents = {name: {**record, "tenant_id": tenant} for name, tenant in PARENT_FAMILY.items()}
        self.auth = app.ParentAuth(parents, "s" * 32, ttl_seconds=600, require_totp=False)
        self.families = app.FamilyRegistry.validate(json.loads(json.dumps(FAMILIES)))
        self.families.check_parents(parents)
        self.pairing = app.PairingBoard()
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            app.make_handler(self.store, "", "", "", parent_auth=self.auth,
                             families=self.families, pairing=self.pairing),
        )
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.sessions = {}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.db.close()
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    def request(self, method, path, payload=None, headers=None, raw=None):
        if raw is None and payload is not None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        all_headers = dict(headers or {})
        if raw is not None:
            all_headers["Content-Length"] = str(len(raw))
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, raw, all_headers)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            data = None
        return response.status, data, response.getheader("Set-Cookie")

    def login(self, username):
        if username not in self.sessions:
            status, data, cookie = self.request("POST", "/watchup/session", {"username": username, "password": PASSWORD})
            self.assertEqual(status, 200, username)
            self.sessions[username] = (cookie.split(";", 1)[0], data["csrf_token"])
        return self.sessions[username]

    def as_parent(self, username, method, path, payload=None):
        cookie, csrf = self.login(username)
        return self.request(method, path, payload, {"Cookie": cookie, "X-WatchUp-CSRF": csrf})

    def bridge_post(self, path, body, secret):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        return self.request("POST", path, raw=raw, headers={"X-WatchUp-Signature": app.signature_for(secret, raw)})

    def send_event(self, signer, tenant, child, event_id="msg-1", event_type="message.received", account=None):
        event = {
            "event_id": event_id, "type": event_type, "source": "whatsapp-bridge",
            "source_timestamp": now_iso(), "tenant_id": tenant, "child_id": child,
            "account": account or {"chat_jid": "group-1@g.us"}, "payload": {"content": "בדיקה"},
        }
        return self.bridge_post("/watchup/events", event, SECRETS[signer])[0]

    def report(self, signer, state, code="", tenant=None, child=None, sent_at=None):
        body = {"tenant_id": tenant or signer[0], "child_id": child or signer[1], "state": state,
                "code": code, "sent_at": sent_at or now_iso()}
        return self.bridge_post("/watchup/bridge/pairing", body, SECRETS[signer])

    def dashboard(self, username, child=None):
        path = "/watchup/dashboard" + (f"?child_id={child}" if child is not None else "")
        return self.as_parent(username, "GET", path)

    def event_ids(self, username, child):
        status, data, _ = self.dashboard(username, child)
        self.assertEqual(status, 200)
        return sorted(item["event_id"] for item in data["events"])

    # -- parent isolation -----------------------------------------------
    def test_each_parent_sees_only_their_family_children(self):
        expected = {"eldad": ["child-1"], "moran": ["child-1"], "elad": ["rotem", "son-test"], "anat": ["rotem", "son-test"]}
        for username, children in expected.items():
            status, data, _ = self.dashboard(username)
            self.assertEqual(status, 200)
            self.assertEqual([c["child_id"] for c in data["children"]], children, username)
            self.assertEqual(data["child_id"], children[0])

    def test_foreign_unknown_and_malformed_child_requests_are_rejected(self):
        for username, child in (("eldad", "rotem"), ("eldad", "son-test"), ("moran", "rotem"),
                                ("elad", "child-1"), ("anat", "child-1"), ("elad", "nobody"), ("elad", "")):
            with self.subTest(username=username, child=child):
                self.assertEqual(self.dashboard(username, child)[0], 403)
        self.assertEqual(self.as_parent("elad", "GET", "/watchup/dashboard?child_id=rotem&child_id=child-1")[0], 403)
        self.assertEqual(self.request("GET", "/watchup/dashboard?child_id=rotem")[0], 401)

    def test_parent_whose_family_mapping_disappears_is_rejected(self):
        self.login("elad")
        del self.auth.parents["elad"]["tenant_id"]
        self.assertEqual(self.dashboard("elad")[0], 403)
        self.assertEqual(self.as_parent("elad", "POST", "/watchup/today?child_id=rotem")[0], 403)

    def test_parent_audit_is_family_scoped(self):
        self.dashboard("eldad")
        self.dashboard("elad")
        status, data, _ = self.as_parent("elad", "GET", "/watchup/audit")
        self.assertEqual(status, 200)
        self.assertEqual({entry["username"] for entry in data["entries"]}, {"elad"})

    # -- bridge isolation -----------------------------------------------
    def test_each_bridge_writes_only_its_own_child(self):
        self.assertEqual(self.send_event(("family-poc", "child-1"), "family-poc", "child-1", "y-1"), 202)
        self.assertEqual(self.send_event(("family-b", "rotem"), "family-b", "rotem", "r-1"), 202)
        self.assertEqual(self.send_event(("family-b", "son-test"), "family-b", "son-test", "s-1"), 202)
        cross = [
            (("family-b", "rotem"), "family-poc", "child-1"),   # cross-tenant
            (("family-b", "rotem"), "family-b", "son-test"),    # cross-child, same family
            (("family-b", "son-test"), "family-b", "rotem"),
            (("family-poc", "child-1"), "family-b", "rotem"),
        ]
        for signer, tenant, child in cross:
            with self.subTest(signer=signer, claims=(tenant, child)):
                self.assertEqual(self.send_event(signer, tenant, child, "evil"), 403)
        self.assertEqual(self.event_ids("eldad", "child-1"), ["y-1"])
        self.assertEqual(self.event_ids("elad", "rotem"), ["r-1"])
        self.assertEqual(self.event_ids("anat", "son-test"), ["s-1"])

    def test_invalid_or_legacy_secret_is_rejected(self):
        event = {"event_id": "x", "type": "message.received", "source": "s", "source_timestamp": now_iso(),
                 "tenant_id": "family-b", "child_id": "rotem", "account": {}, "payload": {}}
        raw = json.dumps(event).encode()
        for signature in ("", "sha256=" + "0" * 64, app.signature_for("some-other-secret-value", raw), "sha256=é"):
            with self.subTest(signature=signature[:12]):
                self.assertEqual(self.request("POST", "/watchup/events", raw=raw, headers={"X-WatchUp-Signature": signature})[0], 401)

    def test_siblings_in_one_group_keep_their_own_copy_of_a_message(self):
        self.assertEqual(self.send_event(("family-b", "rotem"), "family-b", "rotem", "wa-shared"), 202)
        self.assertEqual(self.send_event(("family-b", "son-test"), "family-b", "son-test", "wa-shared"), 202)
        self.assertEqual(self.event_ids("elad", "rotem"), ["wa-shared"])
        self.assertEqual(self.event_ids("elad", "son-test"), ["wa-shared"])

    # -- settings and data scoping --------------------------------------
    def test_child_settings_do_not_leak_between_children_or_families(self):
        words = self.as_parent("elad", "POST", "/watchup/tracking-words?child_id=rotem", {"words": ["סכין"]})
        self.assertEqual(words[0], 200)
        schedule = app.empty_schedule()
        schedule["sun"]["study"] = ["08:00", "13:00"]
        self.assertEqual(self.as_parent("anat", "POST", "/watchup/schedule?child_id=son-test", {"schedule": schedule})[0], 200)
        rotem = self.dashboard("anat", "rotem")[1]
        son = self.dashboard("elad", "son-test")[1]
        yuli = self.dashboard("eldad")[1]
        self.assertEqual(rotem["tracking_words"], ["סכין"])
        self.assertEqual(son["tracking_words"], [])
        self.assertEqual(yuli["tracking_words"], [])
        self.assertEqual(son["schedule"]["sun"]["study"], ["08:00", "13:00"])
        self.assertIsNone(rotem["schedule"]["sun"]["study"])
        self.assertIsNone(yuli["schedule"]["sun"]["study"])
        self.assertEqual(self.as_parent("eldad", "POST", "/watchup/tracking-words?child_id=rotem", {"words": ["x"]})[0], 403)

    def test_reset_today_only_clears_the_selected_child(self):
        for signer, event_id in ((("family-b", "rotem"), "r-old"), (("family-b", "son-test"), "s-old")):
            self.send_event(signer, *signer, event_id)
        day_start = app.jerusalem_day_start()
        self.store.db.execute("UPDATE events SET received_at = ?", ((day_start - timedelta(hours=1)).isoformat(),))
        self.store.db.commit()
        status, data, _ = self.as_parent("elad", "POST", "/watchup/today?child_id=rotem")
        self.assertEqual((status, data["deleted_events"]), (200, 1))
        self.assertEqual(self.store.db.execute("SELECT child_id FROM events").fetchall(), [("son-test",)])

    def test_family_deletion_is_family_scoped(self):
        self.send_event(("family-poc", "child-1"), "family-poc", "child-1", "y-1")
        self.send_event(("family-b", "rotem"), "family-b", "rotem", "r-1")
        self.login("eldad")
        self.login("elad")
        self.assertEqual(self.as_parent("anat", "POST", "/watchup/family")[0], 200)
        self.assertEqual(self.store.db.execute("SELECT tenant_id FROM events").fetchall(), [("family-poc",)])
        self.assertEqual(self.dashboard("eldad")[0], 200)
        self.assertEqual(self.dashboard("elad")[0], 401)

    def test_connection_status_is_independent_per_child(self):
        self.send_event(("family-b", "rotem"), "family-b", "rotem", "c-1", "connection.status", {"status": "connected"})
        rotem = self.dashboard("elad", "rotem")[1]
        son = self.dashboard("elad", "son-test")[1]
        self.assertEqual(rotem["connection"]["account"]["status"], "connected")
        self.assertIsNone(son["connection"])
        self.assertEqual(self.as_parent("elad", "GET", "/watchup/pairing?child_id=rotem")[1]["state"], "connected")
        self.assertEqual(self.as_parent("elad", "GET", "/watchup/pairing?child_id=son-test")[1]["state"], "not_connected")

    # -- QR / pairing ----------------------------------------------------
    def test_qr_flow_reaches_only_the_requested_childs_bridge_and_family(self):
        son, rotem, yuli = ("family-b", "son-test"), ("family-b", "rotem"), ("family-poc", "child-1")
        for signer in (son, rotem, yuli):
            self.assertFalse(self.report(signer, "unpaired")[1]["pairing_requested"])
        self.assertEqual(self.as_parent("eldad", "POST", "/watchup/pairing?child_id=son-test")[0], 403)
        status, data, _ = self.as_parent("elad", "POST", "/watchup/pairing?child_id=son-test")
        self.assertEqual((status, data["state"]), (202, "requested"))
        self.assertTrue(self.report(son, "unpaired")[1]["pairing_requested"])
        self.assertFalse(self.report(rotem, "unpaired")[1]["pairing_requested"])
        self.assertFalse(self.report(yuli, "unpaired")[1]["pairing_requested"])
        self.assertTrue(self.report(son, "qr", "2@synthetic-son-code")[1]["pairing_requested"])
        for username in ("elad", "anat"):
            status, data, _ = self.as_parent(username, "GET", "/watchup/pairing?child_id=son-test")
            self.assertEqual((status, data["state"]), (200, "waiting"))
            self.assertTrue(data["svg"].startswith("data:image/svg+xml;base64,"))
            svg = base64.b64decode(data["svg"].split(",", 1)[1]).decode()
            self.assertIn('xmlns="http://www.w3.org/2000/svg"', svg)
        for username, child in (("eldad", "son-test"), ("moran", "son-test"), ("elad", "child-1")):
            self.assertEqual(self.as_parent(username, "GET", f"/watchup/pairing?child_id={child}")[0], 403)
        self.assertEqual(self.as_parent("elad", "GET", "/watchup/pairing?child_id=rotem")[1]["state"], "not_connected")
        self.assertEqual(self.as_parent("eldad", "GET", "/watchup/pairing")[1]["state"], "not_connected")
        self.assertFalse(self.report(son, "paired")[1]["pairing_requested"])
        self.send_event(son, *son, "c-1", "connection.status", {"status": "connected"})
        self.assertEqual(self.as_parent("anat", "GET", "/watchup/pairing?child_id=son-test")[1]["state"], "connected")

    def test_bridge_reports_are_bound_fresh_and_well_formed(self):
        rotem = ("family-b", "rotem")
        self.as_parent("elad", "POST", "/watchup/pairing?child_id=son-test")
        self.assertEqual(self.report(rotem, "unpaired", child="son-test")[0], 403)
        self.assertEqual(self.report(rotem, "qr", "stolen", tenant="family-poc", child="child-1")[0], 403)
        stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.assertEqual(self.report(rotem, "unpaired", sent_at=stale)[0], 401)
        for state, code in (("qr", ""), ("unpaired", "x"), ("hack", ""), ("qr", "a\nb")):
            with self.subTest(state=state, code=code):
                self.assertEqual(self.report(rotem, state, code)[0], 400)
        raw = json.dumps({"tenant_id": "family-b", "child_id": "son-test", "state": "unpaired", "sent_at": now_iso()}).encode()
        self.assertEqual(self.request("POST", "/watchup/bridge/pairing", raw=raw,
                                      headers={"X-WatchUp-Signature": "sha256=" + "0" * 64})[0], 401)

    def test_connected_child_cannot_be_repaired_and_cancel_stops_the_bridge(self):
        rotem = ("family-b", "rotem")
        self.send_event(rotem, *rotem, "c-1", "connection.status", {"status": "connected"})
        self.assertEqual(self.as_parent("elad", "POST", "/watchup/pairing?child_id=rotem")[0], 409)
        self.assertFalse(self.report(rotem, "unpaired")[1]["pairing_requested"])
        son = ("family-b", "son-test")
        self.as_parent("anat", "POST", "/watchup/pairing?child_id=son-test")
        self.assertTrue(self.report(son, "qr", "code-a")[1]["pairing_requested"])
        status, data, _ = self.as_parent("anat", "DELETE", "/watchup/pairing?child_id=son-test")
        self.assertEqual((status, data["state"]), (200, "not_connected"))
        self.assertFalse(self.report(son, "qr", "code-b")[1]["pairing_requested"])
        self.assertEqual(self.as_parent("eldad", "DELETE", "/watchup/pairing?child_id=son-test")[0], 403)

    def test_pairing_without_a_live_bridge_and_after_timeout(self):
        self.as_parent("elad", "POST", "/watchup/pairing?child_id=rotem")
        self.pairing.state[("family-b", "rotem")]["seen_at"] = time.time() - 600
        self.assertEqual(self.as_parent("elad", "GET", "/watchup/pairing?child_id=rotem")[1]["state"], "bridge_unavailable")
        self.report(("family-b", "rotem"), "timeout")
        self.assertEqual(self.as_parent("elad", "GET", "/watchup/pairing?child_id=rotem")[1]["state"], "timeout")

    def test_pairing_mutations_require_csrf(self):
        cookie, _csrf = self.login("elad")
        for method in ("POST", "DELETE"):
            self.assertEqual(self.request(method, "/watchup/pairing?child_id=rotem", headers={"Cookie": cookie})[0], 403)

    # -- onboarding / parent-added children -------------------------------
    def add_child(self, username="elad", name="חדש", age=7, **extra):
        return self.as_parent(username, "POST", "/watchup/children", {"display_name": name, "age": age, "has_whatsapp": True, **extra})

    def test_parent_added_child_gets_server_id_and_is_family_scoped(self):
        status, child, _ = self.add_child(child_id="rotem")
        self.assertEqual(status, 200)
        cid = child["child_id"]
        self.assertRegex(cid, r"^child-[0-9a-f]{8}$")
        for username in ("elad", "anat"):
            ids = [c["child_id"] for c in self.dashboard(username)[1]["children"]]
            self.assertEqual(ids, ["rotem", "son-test", cid], username)
        for username in ("eldad", "moran"):
            self.assertEqual(self.dashboard(username, cid)[0], 403)
            self.assertEqual(self.as_parent(username, "POST", f"/watchup/children?child_id={cid}",
                                            {"display_name": "x", "age": 7, "has_whatsapp": True})[0], 403)
            self.assertEqual(self.as_parent(username, "GET", f"/watchup/pairing?child_id={cid}")[0], 403)
        status, _, _ = self.as_parent("anat", "POST", f"/watchup/children?child_id={cid}",
                                      {"display_name": "שונה", "age": 9, "has_whatsapp": False})
        self.assertEqual(status, 200)

    def test_children_post_rejects_malformed_child_id_query(self):
        body = {"display_name": "x", "age": 7, "has_whatsapp": True}
        for query in ("?child_id=", "?child_id=rotem&child_id=son-test", "?child_id=nobody"):
            with self.subTest(query=query):
                self.assertEqual(self.as_parent("elad", "POST", "/watchup/children" + query, body)[0], 403)

    def test_children_post_rejects_invalid_profiles(self):
        good = {"display_name": "x", "age": 7, "has_whatsapp": True}
        bad = [{**good, "age": True}, {**good, "age": 0}, {**good, "age": 19}, {**good, "age": "7"},
               {**good, "display_name": ""}, {**good, "display_name": "a‮b"},
               {**good, "display_name": "a‏b"},
               {**good, "has_whatsapp": "yes"}, [good]]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.as_parent("elad", "POST", "/watchup/children", body)[0], 400)

    def test_child_id_collision_regenerates(self):
        first = self.add_child(name="ראשון")[1]["child_id"]
        with unittest.mock.patch.object(app.secrets, "token_hex", side_effect=[first[6:], "deadbeef"]):
            status, second, _ = self.add_child(name="שני")
        self.assertEqual((status, second["child_id"]), (200, "child-deadbeef"))
        names = {c["child_id"]: c["name"] for c in self.dashboard("elad")[1]["children"]}
        self.assertEqual(names[first], "ראשון")

    def test_children_cap_is_eight_per_family(self):
        for _ in range(6):
            self.assertEqual(self.add_child()[0], 200)
        self.assertEqual(len(self.dashboard("elad")[1]["children"]), 8)
        self.assertEqual(self.add_child()[0], 409)
        self.assertEqual(self.add_child("eldad")[0], 200)

    def test_onboarding_requires_ages_and_is_per_family(self):
        cid = self.add_child()[1]["child_id"]
        status, data, _ = self.as_parent("elad", "POST", "/watchup/onboarding", {})
        self.assertEqual(status, 409)
        self.assertEqual(sorted(data["missing"]), ["rotem", "son-test"])
        self.assertFalse(self.as_parent("anat", "GET", "/watchup/onboarding")[1]["completed"])
        self.assertFalse(self.dashboard("anat")[1]["onboarding_completed"])
        for child in ("rotem", "son-test"):
            self.assertEqual(self.as_parent("elad", "POST", f"/watchup/children?child_id={child}",
                                            {"display_name": child, "age": 8, "has_whatsapp": True})[0], 200)
        status, data, _ = self.as_parent("elad", "POST", "/watchup/onboarding", {})
        self.assertEqual((status, data["completed"]), (200, True))
        status, data, _ = self.as_parent("anat", "GET", "/watchup/onboarding")
        self.assertEqual(status, 200)
        self.assertTrue(data["completed"])
        self.assertEqual([c["child_id"] for c in data["children"]], ["rotem", "son-test", cid])
        self.assertTrue(self.dashboard("anat")[1]["onboarding_completed"])
        self.assertFalse(self.as_parent("eldad", "GET", "/watchup/onboarding")[1]["completed"])
        self.assertFalse(self.dashboard("eldad")[1]["onboarding_completed"])

    def test_child_without_bridge_reports_no_bridge(self):
        cid = self.add_child()[1]["child_id"]
        status, data, _ = self.as_parent("elad", "POST", f"/watchup/pairing?child_id={cid}")
        self.assertEqual((status, data["state"]), (409, "no_bridge"))
        status, data, _ = self.as_parent("anat", "GET", f"/watchup/pairing?child_id={cid}")
        self.assertEqual((status, data["state"]), (200, "no_bridge"))
        children = {c["child_id"]: c for c in self.dashboard("elad")[1]["children"]}
        self.assertFalse(children[cid]["has_bridge"])
        self.assertTrue(children["rotem"]["has_bridge"])

    def test_connected_flag_is_independent_per_child(self):
        cid = self.add_child()[1]["child_id"]
        self.send_event(("family-b", "rotem"), "family-b", "rotem", "c-1", "connection.status", {"status": "connected"})
        children = {c["child_id"]: c["connected"] for c in self.dashboard("anat")[1]["children"]}
        self.assertEqual(children, {"rotem": True, "son-test": False, cid: False})

    def test_children_and_onboarding_posts_require_csrf(self):
        cookie, _csrf = self.login("elad")
        body = {"display_name": "x", "age": 7, "has_whatsapp": True}
        self.assertEqual(self.request("POST", "/watchup/children", body, {"Cookie": cookie})[0], 403)
        self.assertEqual(self.request("POST", "/watchup/onboarding", {}, {"Cookie": cookie})[0], 403)


class ChildProfileTests(unittest.TestCase):
    def test_child_without_bridge_secret(self):
        registry = app.FamilyRegistry.validate({"fam-a": {"children": {"kid": {"name": "K"}}}})
        self.assertEqual(registry.children("fam-a")[0]["has_bridge"], False)
        self.assertEqual(registry.children("fam-a")[0]["has_whatsapp"], False)
        self.assertIsNone(registry.children("fam-a")[0]["age"])
        self.assertFalse(registry.has_bridge("fam-a", "kid"))

    def test_duplicate_secret_still_rejected(self):
        secret = "s" * 32
        with self.assertRaises(ValueError):
            app.FamilyRegistry.validate({"fam-a": {"children": {
                "x": {"bridge_secret": secret}, "y": {"bridge_secret": secret}, "z": {}}}})

    def test_no_bridge_child_never_bound(self):
        sibling = "sibling-secret-0000000000000000"
        registry = app.FamilyRegistry.validate({"fam-a": {"children": {
            "nobridge": {}, "sib": {"bridge_secret": sibling}}}})
        body = b"{}"
        for secret in ("another-random-secret-000000", "", "nobridge", sibling):
            binding = registry.binding_for_signature(body, app.signature_for(secret, body))
            self.assertNotEqual(binding, ("fam-a", "nobridge"))
        self.assertEqual(registry.binding_for_signature(body, app.signature_for(sibling, body)), ("fam-a", "sib"))

    def test_bad_age_and_whatsapp_rejected(self):
        for extra in ({"age": True}, {"age": 0}, {"age": 19}, {"age": "7"}, {"has_whatsapp": "yes"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                app.FamilyRegistry.validate({"fam-a": {"children": {"kid": extra}}})

    def test_sqlite_profile_and_onboarding_round_trip(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = app.EventStore(str(Path(tmp) / "e.db"))
            store.upsert_child_profile("fam-a", "kid", "Kid", 7, True, "eldad")
            store.upsert_child_profile("fam-b", "kid", "Other", None, False, "elad")
            self.assertEqual(store.list_child_profiles("fam-a"), {"kid": {"display_name": "Kid", "age": 7, "has_whatsapp": True}})
            self.assertIsNone(store.get_onboarding("fam-a"))
            store.complete_onboarding("fam-a", "eldad")
            self.assertIsNotNone(datetime.fromisoformat(store.get_onboarding("fam-a")))
            self.assertIsNone(store.get_onboarding("fam-b"))
            store.delete_family("fam-a")
            self.assertEqual(store.list_child_profiles("fam-a"), {})
            self.assertIsNone(store.get_onboarding("fam-a"))
            self.assertEqual(list(store.list_child_profiles("fam-b")), ["kid"])


if __name__ == "__main__":
    unittest.main()
