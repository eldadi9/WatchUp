"""Isolated local WatchUp: private PostgreSQL cluster + real API + nginx-equivalent web proxy.

    python watchup-local/local.py init    # one time: cluster, migrations 001-006, synthetic families/parents
    python watchup-local/local.py up      # Postgres + API (127.0.0.1:8769) + web (http://127.0.0.1:8765)
    python watchup-local/local.py down
    python watchup-local/local.py reset   # down + delete .runtime (local data only)

Touches nothing outside watchup-local/.runtime. No production host, secret, session, or WhatsApp account.
"""
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
RUNTIME = ROOT / ".runtime"
PGDATA = RUNTIME / "pgdata"
SECRETS = RUNTIME / "secrets"
PG_BIN = Path(os.environ.get("WATCHUP_LOCAL_PG_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
PG_PORT = 55432
API_PORT = 8769
WEB_PORT = 8765
HOST = "127.0.0.1"
DB = "watchup"
MIGRATIONS = sorted((REPO / "watchup-api" / "migrations").glob("00[0-9]_*.sql"))

# Synthetic local identities. Production ids are reused for Family A to prove backward compatibility.
FAMILIES = {
    "family-poc": {"name": "משפחה א", "children": {
        "child-1": {"name": "יולי", "age": 12, "has_whatsapp": True, "bridge": True},
        "emy": {"name": "אמי", "age": 7, "has_whatsapp": False, "bridge": False}}},
    "family-b": {"name": "משפחה ב", "children": {
        "rotem": {"name": "רותם", "age": 13, "has_whatsapp": True, "bridge": True},
        "ofir": {"name": "אופיר", "age": 9, "has_whatsapp": False, "bridge": False}}},
}
PARENTS = {"eldad": "family-poc", "moran": "family-poc", "elad": "family-b", "anat": "family-b"}


def pg(tool, *args, **kwargs):
    return subprocess.run([str(PG_BIN / f"{tool}.exe"), *map(str, args)], check=True, **kwargs)


def psql(sql_or_file, db=DB, file=False):
    env = {**os.environ, "PGPASSWORD": (SECRETS / "pg_superuser").read_text().strip()}
    target = ["-f", sql_or_file] if file else ["-c", sql_or_file]
    pg("psql", "-h", HOST, "-p", PG_PORT, "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1", "-q", *target,
       env=env, stdout=subprocess.DEVNULL)


def pg_running():
    return subprocess.run([str(PG_BIN / "pg_isready.exe"), "-h", HOST, "-p", str(PG_PORT)],
                          capture_output=True).returncode == 0


def pg_start():
    if not pg_running():
        # All three handles detached: the server outlives this call and must not hold our pipes.
        pg("pg_ctl", "-D", PGDATA, "-l", RUNTIME / "postgres.log", "-w", "start",
           "-o", f"-p {PG_PORT} -c listen_addresses={HOST}",
           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def init():
    if RUNTIME.exists():
        sys.exit(f"{RUNTIME} exists. Use 'reset' first to rebuild local data.")
    SECRETS.mkdir(parents=True)
    (SECRETS / "pg_superuser").write_text(secrets.token_urlsafe(24))
    db_password = secrets.token_urlsafe(24)
    (SECRETS / "db_password").write_text(db_password)
    (SECRETS / "session_secret").write_text(secrets.token_urlsafe(48))
    pg("initdb", "-D", PGDATA, "-U", "postgres", "-E", "UTF8", "--locale=C", "--auth=scram-sha-256",
       f"--pwfile={SECRETS / 'pg_superuser'}", stdout=subprocess.DEVNULL)
    pg_start()
    psql(f"CREATE DATABASE {DB}", db="postgres")
    for migration in MIGRATIONS:
        psql(str(migration), file=True)
    psql(f"CREATE ROLE watchup_api_local LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS "
         f"PASSWORD '{db_password}'; GRANT watchup_app TO watchup_api_local; "
         f"GRANT CONNECT ON DATABASE {DB} TO watchup_api_local;")

    sys.path.insert(0, str(REPO / "watchup-api"))
    from app import ParentAuth  # noqa: E402

    families, bridges = {}, {}
    for tenant, family in FAMILIES.items():
        children = {}
        for child, spec in family["children"].items():
            record = {"name": spec["name"], "age": spec["age"], "has_whatsapp": spec["has_whatsapp"]}
            if spec["bridge"]:
                record["bridge_secret"] = secrets.token_urlsafe(32)
                bridges[f"{tenant}/{child}"] = record["bridge_secret"]
            children[child] = record
        families[tenant] = {"name": family["name"], "children": children}
    (SECRETS / "families.json").write_text(json.dumps(families, ensure_ascii=False, indent=2), encoding="utf-8")
    passwords = {name: secrets.token_urlsafe(9) for name in PARENTS}
    parents = {name: {**ParentAuth.password_record(passwords[name]), "tenant_id": PARENTS[name]} for name in PARENTS}
    (SECRETS / "parents.json").write_text(json.dumps(parents, indent=2), encoding="utf-8")
    (SECRETS / "local-logins.json").write_text(json.dumps(passwords, indent=2), encoding="utf-8")
    print(f"Local WatchUp initialised. Logins: {SECRETS / 'local-logins.json'}")


def api_env():
    required = [SECRETS / name for name in ("db_password", "session_secret", "families.json", "parents.json")]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        sys.exit(f"Local configuration missing (run init): {missing}")
    return {
        "PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "APP_ENV": "development",
        "WATCHUP_EVENT_STORE": "postgres",
        "WATCHUP_DB_HOST": HOST, "WATCHUP_DB_PORT": str(PG_PORT), "WATCHUP_DB_NAME": DB,
        "WATCHUP_DB_USER": "watchup_api_local", "WATCHUP_DB_PASSWORD_FILE": str(SECRETS / "db_password"),
        "WATCHUP_DB_SSLMODE": "disable",
        "WATCHUP_FAMILIES_FILE": str(SECRETS / "families.json"),
        "WATCHUP_PARENTS_FILE": str(SECRETS / "parents.json"),
        "WATCHUP_SESSION_SECRET_FILE": str(SECRETS / "session_secret"),
        "WATCHUP_REQUIRE_TOTP": "false",
        "WATCHUP_SESSION_TTL_SECONDS": "43200",
        "WATCHUP_TRUSTED_PROXY_IPS": HOST,
        "WATCHUP_API_HOST": HOST, "WATCHUP_API_PORT": str(API_PORT),
    }


class WebHandler(SimpleHTTPRequestHandler):
    """Same routing as watchup-web/nginx.conf: static site, and /api/<path> -> API /<path>."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO / "watchup-web"), **kwargs)

    def proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() in
                   ("content-type", "content-length", "cookie", "x-watchup-csrf", "x-watchup-signature", "authorization")}
        headers["X-Forwarded-For"] = self.client_address[0]
        target = f"http://{HOST}:{API_PORT}/" + self.path[len("/api/"):]
        request = urllib.request.Request(target, data=body, headers=headers, method=self.command)
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        except OSError:
            self.send_error(502)
            return
        payload = response.read()
        self.send_response(response.status)
        for key, value in response.headers.items():
            if key.lower() not in ("transfer-encoding", "connection", "server", "date"):
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.proxy()
        if self.path.split("/")[-1].startswith(".") or "/." in self.path:
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        return self.proxy() if self.path.startswith("/api/") else self.send_error(405)

    do_DELETE = do_POST

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *_args):
        pass


def up():
    env = api_env()
    pg_start()
    api = subprocess.Popen([sys.executable, str(REPO / "watchup-api" / "app.py")], env=env,
                           stdout=open(RUNTIME / "api.log", "a"), stderr=subprocess.STDOUT)
    (RUNTIME / "api.pid").write_text(str(api.pid))
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://{HOST}:{API_PORT}/watchup/session", timeout=1)
        except urllib.error.HTTPError:
            break
        except OSError:
            if api.poll() is not None:
                sys.exit(f"API exited. See {RUNTIME / 'api.log'}")
            time.sleep(0.2)
    print(f"WatchUp local: http://{HOST}:{WEB_PORT}  (API pid {api.pid}, Postgres {HOST}:{PG_PORT})")
    try:
        ThreadingHTTPServer((HOST, WEB_PORT), WebHandler).serve_forever()
    finally:
        api.terminate()


def down():
    pid_file = RUNTIME / "api.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text()), signal.SIGTERM)
        except OSError:
            pass
        pid_file.unlink()
    if PGDATA.exists() and pg_running():
        pg("pg_ctl", "-D", PGDATA, "-m", "fast", "stop", stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "init":
        init()
    elif command == "up":
        up()
    elif command == "down":
        down()
    elif command == "reset":
        down()
        shutil.rmtree(RUNTIME, ignore_errors=True)
    else:
        sys.exit(__doc__)
