"""Local WatchUp signed-event ingestion service."""

import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MAX_BODY_BYTES = 256 * 1024
APP_ROLE = "watchup_app"


class EventStore:
    """Small local stand-in for the PostgreSQL events migration."""

    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                tenant_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                source_timestamp TEXT NOT NULL,
                account_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                received_at TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, event_id)
            );
            CREATE INDEX IF NOT EXISTS events_tenant_child_received_idx
                ON events (tenant_id, child_id, received_at DESC);
            """
        )

    def insert(self, event: dict, received_at: datetime) -> bool:
        source_at = parse_timestamp(event["source_timestamp"])
        latency_ms = max(0, int((received_at - source_at).total_seconds() * 1000))
        try:
            self.db.execute(
                """INSERT INTO events (
                    tenant_id, child_id, event_id, event_type, source,
                    source_timestamp, account_json, payload_json, received_at, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event["tenant_id"], event["child_id"], event["event_id"],
                    event["type"], event["source"], event["source_timestamp"],
                    json.dumps(event["account"], ensure_ascii=False, separators=(",", ":")),
                    json.dumps(event["payload"], ensure_ascii=False, separators=(",", ":")),
                    received_at.isoformat(), latency_ms,
                ),
            )
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get(self, tenant_id: str, child_id: str, event_id: str):
        return self.db.execute(
            "SELECT event_id FROM events WHERE tenant_id = ? AND child_id = ? AND event_id = ?",
            (tenant_id, child_id, event_id),
        ).fetchone()

    def list_recent(self, tenant_id: str, child_id: str, limit: int = 50):
        rows = self.db.execute(
            """SELECT event_id, event_type, source_timestamp, account_json, payload_json,
                      received_at, latency_ms
               FROM events
              WHERE tenant_id = ? AND child_id = ?
              ORDER BY received_at DESC
              LIMIT ?""",
            (tenant_id, child_id, limit),
        ).fetchall()
        return [
            {
                "event_id": row[0], "type": row[1], "timestamp": row[2],
                "account": json.loads(row[3]), "payload": json.loads(row[4]),
                "received_at": row[5], "latency_ms": row[6],
            }
            for row in rows
        ]


def _psycopg_connect(**kwargs):
    from psycopg import connect

    return connect(**kwargs)


def _jsonb(value):
    from psycopg.types.json import Jsonb

    return Jsonb(value)


class PostgresEventStore:
    """PostgreSQL event store using the transaction-scoped RLS context."""

    def __init__(self, connection_kwargs: dict, connect_factory=_psycopg_connect, jsonb_factory=_jsonb):
        self.connection_kwargs = connection_kwargs
        self.connect_factory = connect_factory
        self.jsonb_factory = jsonb_factory

    @classmethod
    def from_environment(cls):
        required = ("WATCHUP_DB_HOST", "WATCHUP_DB_PORT", "WATCHUP_DB_NAME", "WATCHUP_DB_USER")
        values = {name: required_env(name) for name in required}
        password_path = Path(required_env("WATCHUP_DB_PASSWORD_FILE"))
        try:
            password = password_path.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as error:
            raise ValueError("WATCHUP_DB_PASSWORD_FILE cannot be read") from error
        if not password:
            raise ValueError("WATCHUP_DB_PASSWORD_FILE is empty")
        try:
            port = int(values["WATCHUP_DB_PORT"])
        except ValueError as error:
            raise ValueError("WATCHUP_DB_PORT must be an integer") from error
        sslmode = os.environ.get("WATCHUP_DB_SSLMODE", "require")
        connection_kwargs = {
            "host": values["WATCHUP_DB_HOST"],
            "port": port,
            "dbname": values["WATCHUP_DB_NAME"],
            "user": values["WATCHUP_DB_USER"],
            "password": password,
            "sslmode": sslmode,
        }
        sslrootcert = os.environ.get("WATCHUP_DB_SSLROOTCERT", "").strip()
        if sslrootcert:
            connection_kwargs["sslrootcert"] = sslrootcert
        if sslmode == "verify-full" and not sslrootcert:
            raise ValueError("WATCHUP_DB_SSLROOTCERT must be set when WATCHUP_DB_SSLMODE=verify-full")
        return cls(connection_kwargs)

    @staticmethod
    def _set_rls_context(cursor, tenant_id: str):
        cursor.execute(f"SET LOCAL ROLE {APP_ROLE}")
        cursor.execute("SELECT set_config('watchup.tenant_id', %s, true)", (tenant_id,))

    def insert(self, event: dict, received_at: datetime) -> bool:
        source_at = parse_timestamp(event["source_timestamp"])
        latency_ms = max(0, int((received_at - source_at).total_seconds() * 1000))
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, event["tenant_id"])
                cursor.execute(
                    """INSERT INTO watchup.events (
                        tenant_id, child_id, event_id, event_type, source,
                        source_timestamp, account, payload, received_at, latency_ms
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, event_id) DO NOTHING""",
                    (
                        event["tenant_id"], event["child_id"], event["event_id"],
                        event["type"], event["source"], event["source_timestamp"],
                        self.jsonb_factory(event["account"]), self.jsonb_factory(event["payload"]),
                        received_at, latency_ms,
                    ),
                )
                return cursor.rowcount == 1

    def get(self, tenant_id: str, child_id: str, event_id: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """SELECT event_id FROM watchup.events
                    WHERE tenant_id = %s AND child_id = %s AND event_id = %s""",
                    (tenant_id, child_id, event_id),
                )
                return cursor.fetchone()

    def list_recent(self, tenant_id: str, child_id: str, limit: int = 50):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """SELECT event_id, event_type, source_timestamp, account, payload,
                              received_at, latency_ms
                       FROM watchup.events
                      WHERE tenant_id = %s AND child_id = %s
                      ORDER BY received_at DESC
                      LIMIT %s""",
                    (tenant_id, child_id, limit),
                )
                return [
                    {
                        "event_id": row[0], "type": row[1], "timestamp": row[2].isoformat(),
                        "account": row[3], "payload": row[4],
                        "received_at": row[5].isoformat(), "latency_ms": row[6],
                    }
                    for row in cursor.fetchall()
                ]


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("source_timestamp must include an offset")
    return parsed.astimezone(timezone.utc)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be set")
    return value


def required_secret_file(name: str) -> str:
    path = Path(required_env(name))
    try:
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as error:
        raise ValueError(f"{name} cannot be read") from error
    if not value:
        raise ValueError(f"{name} is empty")
    return value


def validate_event(event: object) -> dict:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    required_text = ("event_id", "type", "source", "source_timestamp", "tenant_id", "child_id")
    for field in required_text:
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise ValueError(f"{field} is required")
    if not isinstance(event.get("account"), dict):
        raise ValueError("account must be an object")
    if not isinstance(event.get("payload"), dict):
        raise ValueError("payload must be an object")
    parse_timestamp(event["source_timestamp"])
    return event


def signature_for(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def make_handler(
    store, secret: str, tenant_id: str, child_id: str,
    max_body_bytes: int = MAX_BODY_BYTES, dashboard_token: str = "",
):
    class IngestionHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/watchup/dashboard":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            provided = self.headers.get("Authorization", "")
            if not dashboard_token or not hmac.compare_digest(provided, f"Bearer {dashboard_token}"):
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            body = json.dumps(
                {
                    "child_id": child_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "events": store.list_recent(tenant_id, child_id),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/watchup/events":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            if length < 1 or length > max_body_bytes:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            body = self.rfile.read(length)
            provided = self.headers.get("X-WatchUp-Signature", "")
            if not hmac.compare_digest(provided, signature_for(secret, body)):
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            try:
                event = validate_event(json.loads(body.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            if event["tenant_id"] != tenant_id or event["child_id"] != child_id:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            inserted = store.insert(event, datetime.now(timezone.utc))
            self.send_response(HTTPStatus.ACCEPTED if inserted else HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"accepted": inserted, "duplicate": not inserted}).encode("utf-8"))

        def log_message(self, _format, *_args):
            pass  # Never log message payloads or signatures.

    return IngestionHandler


def main():
    try:
        production = os.environ.get("APP_ENV", "development").lower() == "production"
        secret = (
            required_secret_file("WATCHUP_WEBHOOK_SECRET_FILE")
            if production
            else os.environ.get("WATCHUP_WEBHOOK_SECRET") or required_secret_file("WATCHUP_WEBHOOK_SECRET_FILE")
        )
        if len(secret) < 16:
            raise ValueError("WATCHUP_WEBHOOK_SECRET must be at least 16 characters")
        tenant_id = required_env("WATCHUP_TENANT_ID")
        child_id = required_env("WATCHUP_CHILD_ID")
        store_kind = os.environ.get("WATCHUP_EVENT_STORE", "postgres" if production else "sqlite").lower()
        if production and store_kind != "postgres":
            raise ValueError("production requires WATCHUP_EVENT_STORE=postgres")
        if production and os.environ.get("WATCHUP_DB_SSLMODE", "require") != "verify-full":
            raise ValueError("production requires WATCHUP_DB_SSLMODE=verify-full")
        if store_kind == "postgres":
            store = PostgresEventStore.from_environment()
        elif store_kind == "sqlite" and not production:
            store = EventStore(os.environ.get("WATCHUP_EVENTS_DB", "watchup-events.db"))
        else:
            raise ValueError("WATCHUP_EVENT_STORE must be postgres or local sqlite outside production")
        dashboard_token = (
            required_secret_file("WATCHUP_DASHBOARD_TOKEN_FILE")
            if production
            else os.environ.get("WATCHUP_DASHBOARD_TOKEN") or required_secret_file("WATCHUP_DASHBOARD_TOKEN_FILE")
        )
        if len(dashboard_token) < 24:
            raise ValueError("WATCHUP_DASHBOARD_TOKEN must be at least 24 characters")
        port = int(os.environ.get("WATCHUP_API_PORT", "8769"))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    host = os.environ.get("WATCHUP_API_HOST", "127.0.0.1")
    ThreadingHTTPServer(
        (host, port), make_handler(store, secret, tenant_id, child_id, dashboard_token=dashboard_token)
    ).serve_forever()


if __name__ == "__main__":
    main()
