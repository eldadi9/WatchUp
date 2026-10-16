"""End-to-end Local acceptance matrix: browser path (web :8765 -> API -> private Postgres).

    python watchup-local/acceptance.py      # requires `local.py up`; exits non-zero on any failure
"""
import json
import re
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sim

RUNTIME = Path(__file__).resolve().parent / ".runtime"
LOGINS = json.loads((RUNTIME / "secrets" / "local-logins.json").read_text(encoding="utf-8"))
YULI, EMY = ("family-poc", "child-1"), ("family-poc", "emy")
ROTEM, OFIR = ("family-b", "rotem"), ("family-b", "ofir")
RUN = secrets.token_hex(4)
DAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
results = []

assert sim.BASE.startswith("http://127.0.0.1:"), "acceptance only runs against the local stack"


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("PASS " if condition else "FAIL ") + name + ("" if condition else f"  [{detail}]"))


class Parent:
    def __init__(self, username):
        self.username = username
        status, body, headers = self.call("POST", "/watchup/session", {"username": username, "password": LOGINS[username]})
        if status != 200:
            sys.exit(f"login failed for {username}: {status}")
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = body["csrf_token"]

    def call(self, method, path, payload=None, auth=False, csrf=True):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Cookie"] = self.cookie
            if csrf:
                headers["X-WatchUp-CSRF"] = self.csrf
        request = urllib.request.Request(sim.BASE + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.loads(response.read() or b"null"), response.headers
        except urllib.error.HTTPError as error:
            body = error.read()
            try:
                body = json.loads(body or b"null")
            except ValueError:
                body = None
            return error.code, body, error.headers

    def get(self, path):
        return self.call("GET", path, auth=True)[:2]

    def post(self, path, payload=None):
        return self.call("POST", path, payload, auth=True)[:2]

    def delete(self, path):
        return self.call("DELETE", path, auth=True)[:2]

    def children(self):
        return [child["child_id"] for child in self.get("/watchup/dashboard")[1]["children"]]

    def child(self, child_id):
        return next(c for c in self.get("/watchup/dashboard")[1]["children"] if c["child_id"] == child_id)

    def view(self, child_id):
        return self.get(f"/watchup/dashboard?child_id={child_id}")[1]

    def event_ids(self, child):
        return {item["event_id"] for item in self.view(child)["events"]}

    def pairing(self, child):
        return self.get(f"/watchup/pairing?child_id={child}")[1]["state"]


def secret(pair):
    return sim.bridge_secret(*pair)


def blank_schedule():
    return {day: {"study": None, "evening": None} for day in DAYS}


def heartbeat(pair, status):
    sim.event(*pair, secret(pair), event_type="connection.status", account={"status": status}, payload={})


def main():
    eldad, moran, elad, anat = (Parent(name) for name in ("eldad", "moran", "elad", "anat"))
    poc, fam_b = (eldad, moran), (elad, anat)

    print("\n== A Visibility")
    for parent in poc:
        check(f"{parent.username} sees Yuli + Emy", parent.children() == ["child-1", "emy"], parent.children())
    for parent in fam_b:
        kids = parent.children()
        check(f"{parent.username} sees Rotem + Ofir first", kids[:2] == ["rotem", "ofir"], kids)
        check(f"{parent.username} sees no family-poc child", "child-1" not in kids and "emy" not in kids, kids)
    emy = eldad.child("emy")
    check("Emy has no bridge / whatsapp, age 7",
          emy["has_bridge"] is False and emy["has_whatsapp"] is False and emy["age"] == 7, emy)
    check("Ofir has no bridge", elad.child("ofir")["has_bridge"] is False)

    print("\n== B Cross-family access")
    foreign = {"eldad": ("rotem", "ofir"), "moran": ("rotem", "ofir"), "elad": ("child-1", "emy"), "anat": ("child-1", "emy")}
    schedule = blank_schedule()
    profile = {"display_name": "x", "age": 8, "has_whatsapp": False}
    for parent in poc + fam_b:
        for child in foreign[parent.username]:
            q = f"?child_id={child}"
            attempts = (("GET", "/watchup/dashboard" + q, None), ("GET", "/watchup/pairing" + q, None),
                        ("POST", "/watchup/pairing" + q, None), ("POST", "/watchup/tracking-words" + q, {"words": ["x"]}),
                        ("POST", "/watchup/schedule" + q, {"schedule": schedule}), ("POST", "/watchup/today" + q, None),
                        ("POST", "/watchup/children" + q, profile))
            bad = [(m, p.split("?")[0], s) for m, p, b in attempts if (s := parent.call(m, p, b, auth=True)[0]) != 403]
            check(f"{parent.username} -> {child}: all 7 requests 403", not bad, bad)
    check("No session -> 401", Parent.__new__(Parent).call("GET", "/watchup/dashboard")[0] == 401)
    for label, q in (("empty", "?child_id="), ("duplicated", "?child_id=a&child_id=b"),
                     ("traversal", "?child_id=..%2Fchild-1"), ("unknown", "?child_id=unknown")):
        status = eldad.call("GET", "/watchup/dashboard" + q, auth=True)[0]
        check(f"malformed child_id ({label}) -> 403", status == 403, status)

    print("\n== C Bridge auth")
    ids = {pair: f"acc-{RUN}-{pair[1]}" for pair in (YULI, ROTEM)}
    for pair in (YULI, ROTEM):
        check(f"bridge {pair[1]} writes own child", sim.event(*pair, secret(pair), ids[pair])[0] == 202)
    check("Yuli event only on Yuli", ids[YULI] in eldad.event_ids("child-1") and ids[YULI] not in eldad.event_ids("emy")
          and ids[YULI] not in elad.event_ids("rotem"))
    check("Rotem event only on Rotem", ids[ROTEM] in elad.event_ids("rotem") and ids[ROTEM] not in elad.event_ids("ofir")
          and ids[ROTEM] not in eldad.event_ids("child-1"))
    for claim in (YULI, EMY, OFIR):
        status = sim.event(*ROTEM, secret(ROTEM), f"evil-{RUN}", claim_tenant=claim[0], claim_child=claim[1])[0]
        check(f"Rotem secret claiming {claim[1]} -> 403", status == 403, status)
    status = sim.event(*YULI, secret(YULI), f"evil-{RUN}", claim_tenant=ROTEM[0], claim_child=ROTEM[1])[0]
    check("Yuli secret claiming rotem -> 403", status == 403, status)
    check("unknown secret -> 401", sim.event(*ROTEM, "not-a-registered-secret-value-123")[0] == 401)
    shared = f"wa-shared-{RUN}"
    sim.event(*YULI, secret(YULI), shared)
    sim.event(*ROTEM, secret(ROTEM), shared)
    check("same event_id stored for both children", shared in eldad.event_ids("child-1") and shared in elad.event_ids("rotem"))

    print("\n== D Connection status")
    heartbeat(YULI, "connected")
    heartbeat(ROTEM, "disconnected")
    check("dashboard connected: Yuli True, Emy False", eldad.child("child-1")["connected"] is True and eldad.child("emy")["connected"] is False)
    check("dashboard connected: Rotem False, Ofir False", elad.child("rotem")["connected"] is False and elad.child("ofir")["connected"] is False)
    check("pairing Yuli connected", eldad.pairing("child-1") == "connected")
    check("pairing Emy no_bridge", eldad.pairing("emy") == "no_bridge")
    check("pairing Ofir no_bridge", elad.pairing("ofir") == "no_bridge")
    check("pairing Rotem not connected", elad.pairing("rotem") == "not_connected", elad.pairing("rotem"))

    print("\n== E QR / pairing")
    for pair in (YULI, ROTEM):
        sim.report(*pair, secret(pair), "unpaired")
    check("eldad POST pairing rotem 403", eldad.post("/watchup/pairing?child_id=rotem")[0] == 403)
    check("eldad POST pairing child-1 409", eldad.post("/watchup/pairing?child_id=child-1")[0] == 409)
    status, body = eldad.post("/watchup/pairing?child_id=emy")
    check("eldad POST pairing emy 409 no_bridge", status == 409 and body and body.get("state") == "no_bridge", (status, body))
    status, body = elad.post("/watchup/pairing?child_id=ofir")
    check("elad POST pairing ofir 409 no_bridge", status == 409 and body and body.get("state") == "no_bridge", (status, body))
    status, body = elad.post("/watchup/pairing?child_id=rotem")
    check("elad POST pairing rotem 202 requested", status == 202 and body["state"] == "requested", (status, body))
    check("Rotem bridge is asked", sim.report(*ROTEM, secret(ROTEM), "unpaired")[1]["pairing_requested"] is True)
    check("Yuli bridge is not asked", sim.report(*YULI, secret(YULI), "unpaired")[1]["pairing_requested"] is False)
    check("Rotem secret reporting for ofir -> 403", sim.report(*ROTEM, secret(ROTEM), "qr", "x", claim_child="ofir")[0] == 403)
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    check("replayed report (10 min old) -> 401", sim.report(*ROTEM, secret(ROTEM), "unpaired", sent_at=stale)[0] == 401)
    sim.report(*ROTEM, secret(ROTEM), "qr", f"2@SIMULATED-{RUN}")
    for parent in fam_b:
        view = parent.get("/watchup/pairing?child_id=rotem")[1]
        check(f"{parent.username} sees Rotem QR", view["state"] == "waiting" and view["svg"].startswith("data:image/svg+xml"), view)
    for parent in poc:
        check(f"{parent.username} GET rotem pairing 403", parent.get("/watchup/pairing?child_id=rotem")[0] == 403)
    check("anat cancels", anat.delete("/watchup/pairing?child_id=rotem")[1]["state"] == "not_connected")
    check("cancel stops the Rotem bridge", sim.report(*ROTEM, secret(ROTEM), "unpaired")[1]["pairing_requested"] is False)
    elad.post("/watchup/pairing?child_id=rotem")
    sim.report(*ROTEM, secret(ROTEM), "qr", f"2@SIMULATED-{RUN}-b")
    sim.report(*ROTEM, secret(ROTEM), "timeout")
    check("QR timeout surfaces as timeout", elad.pairing("rotem") == "timeout", elad.pairing("rotem"))
    elad.post("/watchup/pairing?child_id=rotem")
    sim.report(*ROTEM, secret(ROTEM), "qr", f"2@SIMULATED-{RUN}-c")
    sim.report(*ROTEM, secret(ROTEM), "paired")
    heartbeat(ROTEM, "connected")
    check("Rotem paired -> connected", elad.pairing("rotem") == "connected", elad.pairing("rotem"))
    check("Yuli still connected", eldad.pairing("child-1") == "connected", eldad.pairing("child-1"))
    check("Emy / Ofir not connected", eldad.pairing("emy") != "connected" and elad.pairing("ofir") != "connected")
    check("Rotem re-pair 409", elad.post("/watchup/pairing?child_id=rotem")[0] == 409)
    heartbeat(ROTEM, "disconnected")
    check("Rotem disconnected again", elad.pairing("rotem") == "not_connected", elad.pairing("rotem"))

    print("\n== F Onboarding")
    check("eldad onboarding lists Yuli + Emy",
          [c["child_id"] for c in eldad.get("/watchup/onboarding")[1]["children"]] == ["child-1", "emy"])
    emy_profile = {"display_name": "אמי", "age": 7, "has_whatsapp": False}
    check("eldad saves Emy profile", eldad.post("/watchup/children?child_id=emy", emy_profile)[0] == 200)
    emy_word = f"test-emy-{RUN}"
    emy_schedule = blank_schedule()
    emy_schedule["sun"]["study"] = ["08:00", "13:00"]
    check("eldad saves Emy words", eldad.post("/watchup/tracking-words?child_id=emy", {"words": [emy_word]})[0] == 200)
    check("eldad saves Emy schedule", eldad.post("/watchup/schedule?child_id=emy", {"schedule": emy_schedule})[0] == 200)
    emy_view = eldad.view("emy")
    check("Emy has its own words + schedule",
          emy_view["tracking_words"] == [emy_word] and emy_view["schedule"]["sun"]["study"] == ["08:00", "13:00"])
    for parent, child in ((eldad, "child-1"), (elad, "rotem"), (elad, "ofir")):
        view = parent.view(child)
        check(f"Emy settings absent on {child}",
              emy_word not in view["tracking_words"] and view["schedule"]["sun"]["study"] != ["08:00", "13:00"])
    elad_completed_before = elad.get("/watchup/onboarding")[1]["completed"]
    check("eldad completes onboarding", eldad.post("/watchup/onboarding")[0] == 200)
    check("elad onboarding unchanged by eldad completing",
          elad.get("/watchup/onboarding")[1]["completed"] == elad_completed_before, elad_completed_before)
    check("moran sees onboarding completed", moran.get("/watchup/onboarding")[1]["completed"] is True)
    check("families have different names",
          elad.get("/watchup/onboarding")[1]["family_name"] != eldad.get("/watchup/onboarding")[1]["family_name"])
    status, body = elad.post("/watchup/children", {"display_name": "בדיקה", "age": 5, "has_whatsapp": False})
    if status == 409:
        print("SKIP new-child checks: id format, eldad cannot read/update/pair new child (child cap reached)")
    else:
        new_id = body["child_id"] if status == 200 and body else ""
        check("elad creates child -> 200 with id child-<8hex>", status == 200 and re.fullmatch(r"child-[0-9a-f]{8}", new_id), (status, body))
        check("anat sees the new child", new_id in anat.children())
        check("eldad cannot read new child", eldad.get(f"/watchup/dashboard?child_id={new_id}")[0] == 403)
        check("eldad cannot update new child", eldad.post(f"/watchup/children?child_id={new_id}", profile)[0] == 403)
        check("eldad cannot pair new child", eldad.get(f"/watchup/pairing?child_id={new_id}")[0] == 403)
    check("anat saves Ofir profile",
          anat.post("/watchup/children?child_id=ofir", {"display_name": "אופיר", "age": 9, "has_whatsapp": False})[0] == 200)
    status, body = elad.post("/watchup/onboarding")
    check("elad completes onboarding", status == 200, (status, body))
    check("invalid profile (age 19) -> 400",
          eldad.post("/watchup/children?child_id=emy", {"display_name": "אמי", "age": 19, "has_whatsapp": False})[0] == 400)
    check("POST children without CSRF -> 403",
          eldad.call("POST", "/watchup/children?child_id=emy", emy_profile, auth=True, csrf=False)[0] == 403)

    print("\n== G Settings isolation")
    for parent, child in ((eldad, "child-1"), (elad, "rotem"), (elad, "ofir")):
        parent.post(f"/watchup/tracking-words?child_id={child}", {"words": []})
        parent.post(f"/watchup/schedule?child_id={child}", {"schedule": blank_schedule()})
    word = f"סכין-{RUN}"
    ofir_schedule = blank_schedule()
    ofir_schedule["sun"]["study"] = ["09:00", "14:00"]
    check("elad saves Rotem word", elad.post("/watchup/tracking-words?child_id=rotem", {"words": [word]})[0] == 200)
    check("anat saves Ofir schedule", anat.post("/watchup/schedule?child_id=ofir", {"schedule": ofir_schedule})[0] == 200)
    rotem_view, ofir_view, yuli_view = anat.view("rotem"), anat.view("ofir"), eldad.view("child-1")
    check("Rotem word on Rotem only", rotem_view["tracking_words"] == [word] and ofir_view["tracking_words"] == []
          and yuli_view["tracking_words"] == [])
    check("Ofir schedule on Ofir only", ofir_view["schedule"]["sun"]["study"] == ["09:00", "14:00"]
          and rotem_view["schedule"]["sun"]["study"] is None and yuli_view["schedule"]["sun"]["study"] is None)
    elad.post("/watchup/tracking-words?child_id=rotem", {"words": []})
    anat.post("/watchup/schedule?child_id=ofir", {"schedule": blank_schedule()})
    marker = f"reset-{RUN}"
    sim.event(*YULI, secret(YULI), marker)
    check("Elad resets Rotem today", elad.post("/watchup/today?child_id=rotem")[0] == 200)
    check("Yuli event untouched by Rotem reset", marker in eldad.event_ids("child-1"))

    print("\n== H Database RLS (direct, as the app login)")
    import psycopg  # noqa: E402
    password = (RUNTIME / "secrets" / "db_password").read_text().strip()
    with psycopg.connect(host="127.0.0.1", port=55432, dbname="watchup", user="watchup_api_local",
                         password=password, sslmode="disable") as connection, connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE watchup_app")
        cursor.execute("SELECT set_config('watchup.tenant_id', 'family-poc', true)")
        cursor.execute("SELECT DISTINCT tenant_id FROM watchup.events")
        tenants = {row[0] for row in cursor.fetchall()}
        check("RLS: family-poc context sees only family-poc events", tenants <= {"family-poc"} and tenants, tenants)
        cursor.execute("SELECT DISTINCT tenant_id FROM watchup.child_profiles")
        tenants = {row[0] for row in cursor.fetchall()}
        check("RLS: family-poc context sees only family-poc profiles", tenants <= {"family-poc"}, tenants)
        try:
            cursor.execute("INSERT INTO watchup.events (tenant_id, child_id, event_id, event_type, source, source_timestamp,"
                           " account, payload, latency_ms) VALUES ('family-b','rotem','rls-x','t','s',now(),'{}','{}',0)")
            check("RLS: cross-tenant insert blocked", False)
        except psycopg.Error:
            check("RLS: cross-tenant insert blocked", True)

    print("\n== Local only")
    import local  # noqa: E402
    env = local.api_env()
    check("API env DB host is 127.0.0.1", env["WATCHUP_DB_HOST"] == "127.0.0.1", env["WATCHUP_DB_HOST"])
    check("API env APP_ENV is development", env["APP_ENV"] == "development", env["APP_ENV"])
    families_path = Path(env["WATCHUP_FAMILIES_FILE"]).resolve()
    check("families file under watchup-local/.runtime", (Path(local.__file__).resolve().parent / ".runtime") in families_path.parents,
          families_path)

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
