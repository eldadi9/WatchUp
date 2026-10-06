"""Local WatchUp signed-event ingestion service."""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import base64
import ipaddress
from datetime import datetime, timezone, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MAX_BODY_BYTES = 256 * 1024
APP_ROLE = "watchup_app"
SESSION_COOKIE = "watchup_parent_session"
BIDI_CONTROLS = frozenset(chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


class ParentAuth:
    """Parent authentication with password, TOTP, and revocable sessions."""

    def __init__(self, parents: dict, session_secret: str, ttl_seconds: int = 1800,
                 session_store=None, require_totp: bool = True, audit_sink=None):
        self.parents = parents
        self.session_secret = session_secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds
        self.sessions = {}
        self.totp_steps = {}
        self.session_store = session_store
        self.require_totp = require_totp
        self.attempts = {}
        self.audit_log = []
        self.audit_sink = audit_sink

    @classmethod
    def from_files(cls, parents_path: str, session_secret_path: str,
                   ttl_seconds: int = 1800, require_totp: bool = True):
        parents = json.loads(Path(parents_path).read_text(encoding="utf-8"))
        secret = Path(session_secret_path).read_text(encoding="utf-8").rstrip("\r\n")
        if not isinstance(parents, dict) or len(parents) < 1 or len(secret) < 32:
            raise ValueError("invalid parent authentication secrets")
        for username, record in parents.items():
            if (not isinstance(username, str) or not isinstance(record, dict)
                    or (require_totp and not record.get("totp_secret"))):
                raise ValueError("each parent requires a TOTP secret")
        return cls(parents, secret, ttl_seconds=ttl_seconds, require_totp=require_totp)

    @staticmethod
    def password_record(password: str, salt: bytes = None) -> dict:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return {"salt": salt.hex(), "hash": digest.hex()}

    def _allowed(self, client_ip: str, now: float) -> bool:
        recent = [stamp for stamp in self.attempts.get(client_ip, []) if now - stamp < 900]
        self.attempts[client_ip] = recent
        return len(recent) < 5

    @staticmethod
    def _totp(secret: str, counter: int) -> str:
        key = base64.b32decode(secret.upper().replace(" ", ""), casefold=True)
        message = counter.to_bytes(8, "big")
        digest = hmac.new(key, message, hashlib.sha1).digest()
        offset = digest[-1] & 15
        return str((int.from_bytes(digest[offset:offset + 4], "big") & 0x7fffffff) % 1000000).zfill(6)

    def _valid_totp(self, username: str, record: dict, code: str, now: float) -> bool:
        if not isinstance(code, str) or len(code) != 6 or not code.isdigit() or not record.get("totp_secret"):
            return False
        current = int(now // 30)
        for counter in (current - 1, current, current + 1):
            try:
                matches = hmac.compare_digest(self._totp(record["totp_secret"], counter), code)
            except (ValueError, TypeError):
                return False
            if matches:
                if self.session_store:
                    return self.session_store.consume_totp_step(username, counter)
                if counter <= self.totp_steps.get(username, -1):
                    return False
                self.totp_steps[username] = counter
                return True
        return False

    def _token_hash(self, token: str) -> str:
        return hmac.new(self.session_secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _record_audit(self, action: str, username: str, client_ip: str, path: str):
        entry = {"event": action, "username": username, "at": time.time(), "path": path, "client_ip": client_ip}
        self.audit_log.append(entry)
        if self.audit_sink:
            self.audit_sink(action, username, path, client_ip)

    def username_for_token(self, token: str, now: float = None) -> str:
        now = time.time() if now is None else now
        token_hash = self._token_hash(token)
        session = self.session_store.get_session(token_hash, now) if self.session_store else self.sessions.get(token_hash)
        if not session or session["expires_at"] <= now:
            return ""
        return session["username"]

    def login(self, username: str, password: str, totp_code: str, client_ip: str, now: float = None):
        now = time.time() if now is None else now
        username = username.casefold()
        if not self._allowed(client_ip, now):
            self._record_audit("login_rate_limited", username, client_ip, "/watchup/session")
            return None, "rate_limited"
        record = self.parents.get(username)
        valid = False
        if isinstance(record, dict):
            try:
                actual = hashlib.scrypt(
                    password.encode("utf-8"), salt=bytes.fromhex(record["salt"]), n=2**14, r=8, p=1
                )
                valid = hmac.compare_digest(actual.hex(), record["hash"])
            except (KeyError, TypeError, ValueError):
                valid = False
        if not valid or (self.require_totp and not self._valid_totp(username, record or {}, totp_code, now)):
            self.attempts.setdefault(client_ip, []).append(now)
            self._record_audit("login_failed", username, client_ip, "/watchup/session")
            return None, "invalid"
        self.attempts.pop(client_ip, None)
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        session = {"username": username, "expires_at": now + self.ttl_seconds,
                   "csrf_hash": self._token_hash(csrf_token)}
        if self.session_store:
            self.session_store.create_session(token_hash, session)
        else:
            self.sessions[token_hash] = session
        self._record_audit("login_succeeded", username, client_ip, "/watchup/session")
        return (token, csrf_token), "ok"

    def validate(self, token: str, now: float = None) -> bool:
        now = time.time() if now is None else now
        token_hash = self._token_hash(token)
        session = self.session_store.get_session(token_hash, now) if self.session_store else self.sessions.get(token_hash)
        if not session or session["expires_at"] <= now:
            if self.session_store:
                self.session_store.delete_session(token_hash)
            else:
                self.sessions.pop(token_hash, None)
            return False
        return True

    def csrf_valid(self, token: str, csrf_token: str, now: float = None) -> bool:
        now = time.time() if now is None else now
        token_hash = self._token_hash(token)
        session = self.session_store.get_session(token_hash, now) if self.session_store else self.sessions.get(token_hash)
        return bool(session and session["expires_at"] > now and isinstance(csrf_token, str)
                    and hmac.compare_digest(session["csrf_hash"], self._token_hash(csrf_token)))

    def rotate_csrf(self, token: str) -> str:
        if not self.validate(token):
            return ""
        csrf_token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        csrf_hash = self._token_hash(csrf_token)
        if self.session_store:
            self.session_store.set_csrf_hash(token_hash, csrf_hash)
        else:
            self.sessions[token_hash]["csrf_hash"] = csrf_hash
        return csrf_token

    def logout(self, token: str, client_ip: str = "", now: float = None):
        token_hash = self._token_hash(token)
        session = self.session_store.delete_session(token_hash) if self.session_store else self.sessions.pop(token_hash, None)
        username = session["username"] if session else ""
        self._record_audit("logout", username, client_ip, "/watchup/session")

    def revoke_all(self):
        if self.session_store:
            self.session_store.delete_all_sessions()
        else:
            self.sessions.clear()


class SQLiteAuthStore:
    """Durable local-PoC auth state; production uses PostgreSQL instead."""
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS parent_sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
              expires_at REAL NOT NULL, csrf_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS parent_totp_steps (username TEXT PRIMARY KEY, last_step INTEGER NOT NULL);
        """)

    def create_session(self, token_hash, session):
        self.db.execute("INSERT INTO parent_sessions VALUES (?, ?, ?, ?)", (token_hash, session["username"], session["expires_at"], session["csrf_hash"]))
        self.db.commit()

    def get_session(self, token_hash, _now):
        row = self.db.execute("SELECT username, expires_at, csrf_hash FROM parent_sessions WHERE token_hash = ?", (token_hash,)).fetchone()
        return {"username": row[0], "expires_at": row[1], "csrf_hash": row[2]} if row else None

    def delete_session(self, token_hash):
        session = self.get_session(token_hash, 0)
        self.db.execute("DELETE FROM parent_sessions WHERE token_hash = ?", (token_hash,)); self.db.commit()
        return session

    def delete_all_sessions(self):
        self.db.execute("DELETE FROM parent_sessions"); self.db.commit()

    def set_csrf_hash(self, token_hash, csrf_hash):
        self.db.execute("UPDATE parent_sessions SET csrf_hash = ? WHERE token_hash = ?", (csrf_hash, token_hash)); self.db.commit()

    def consume_totp_step(self, username, step):
        cursor = self.db.execute("INSERT INTO parent_totp_steps VALUES (?, ?) ON CONFLICT(username) DO UPDATE SET last_step = excluded.last_step WHERE parent_totp_steps.last_step < excluded.last_step", (username, step))
        self.db.commit()
        return cursor.rowcount == 1

    def close(self):
        self.db.close()


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
            CREATE TABLE IF NOT EXISTS parent_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                username TEXT,
                action TEXT NOT NULL,
                path TEXT NOT NULL,
                client_ip TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS parent_audit_tenant_created_idx
                ON parent_audit (tenant_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS tracking_words (
                tenant_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                word TEXT NOT NULL,
                normalized_word TEXT NOT NULL,
                PRIMARY KEY (tenant_id, child_id, normalized_word)
            );
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

    def list_latest_groups(self, tenant_id: str, child_id: str, limit: int = 100):
        rows = self.db.execute(
            """SELECT event_id, event_type, source_timestamp, account_json, payload_json,
                      received_at, latency_ms
               FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY json_extract(account_json, '$.chat_jid')
                        ORDER BY received_at DESC
                    ) AS newest
                    FROM events
                    WHERE tenant_id = ? AND child_id = ? AND event_type = 'group.snapshot'
               )
              WHERE newest = 1
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

    def latest_connection_status(self, tenant_id: str, child_id: str):
        row = self.db.execute(
            """SELECT account_json, received_at, source_timestamp
               FROM events
              WHERE tenant_id = ? AND child_id = ? AND event_type = 'connection.status'
              ORDER BY received_at DESC
              LIMIT 1""",
            (tenant_id, child_id),
        ).fetchone()
        if not row:
            return None
        return {
            "type": "connection.status",
            "account": json.loads(row[0]),
            "received_at": row[1],
            "timestamp": row[2],
        }

    def purge_before(self, cutoff: datetime, tenant_id: str) -> int:
        cursor = self.db.execute("DELETE FROM events WHERE received_at < ? AND tenant_id = ?", (cutoff.isoformat(), tenant_id))
        self.db.commit()
        return cursor.rowcount

    def list_tracking_words(self, tenant_id: str, child_id: str):
        return [row[0] for row in self.db.execute(
            "SELECT word FROM tracking_words WHERE tenant_id = ? AND child_id = ? ORDER BY position",
            (tenant_id, child_id),
        ).fetchall()]

    def set_tracking_words(self, tenant_id: str, child_id: str, words: list[str]):
        with self.db:
            self.db.execute("DELETE FROM tracking_words WHERE tenant_id = ? AND child_id = ?", (tenant_id, child_id))
            self.db.executemany(
                "INSERT INTO tracking_words (tenant_id, child_id, position, word, normalized_word) VALUES (?, ?, ?, ?, ?)",
                [(tenant_id, child_id, index, word, word.casefold()) for index, word in enumerate(words)],
            )

    def delete_family(self, tenant_id: str) -> int:
        cursor = self.db.execute("DELETE FROM events WHERE tenant_id = ?", (tenant_id,))
        self.db.execute("DELETE FROM tracking_words WHERE tenant_id = ?", (tenant_id,))
        self.db.execute("DELETE FROM parent_audit WHERE tenant_id = ?", (tenant_id,))
        self.db.commit()
        return cursor.rowcount

    def append_parent_audit(self, tenant_id: str, username: str, action: str, path: str, client_ip: str):
        self.db.execute(
            "INSERT INTO parent_audit (tenant_id, username, action, path, client_ip, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, username or None, action, path, client_ip or None, datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()

    def list_parent_audit(self, tenant_id: str, limit: int = 100):
        rows = self.db.execute(
            """SELECT username, action, path, client_ip, created_at
               FROM parent_audit WHERE tenant_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (tenant_id, limit),
        ).fetchall()
        return [
            {"username": row[0], "action": row[1], "path": row[2], "client_ip": row[3], "created_at": row[4]}
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

    def list_latest_groups(self, tenant_id: str, child_id: str, limit: int = 100):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """SELECT event_id, event_type, source_timestamp, account, payload, received_at, latency_ms
                       FROM (
                            SELECT DISTINCT ON (account->>'chat_jid')
                                   event_id, event_type, source_timestamp, account, payload, received_at, latency_ms
                            FROM watchup.events
                            WHERE tenant_id = %s AND child_id = %s AND event_type = 'group.snapshot'
                            ORDER BY account->>'chat_jid', received_at DESC
                       ) AS latest_groups
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

    def latest_connection_status(self, tenant_id: str, child_id: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """SELECT account, received_at, source_timestamp
                       FROM watchup.events
                      WHERE tenant_id = %s AND child_id = %s AND event_type = 'connection.status'
                      ORDER BY received_at DESC
                      LIMIT 1""",
                    (tenant_id, child_id),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "type": "connection.status",
                    "account": row[0],
                    "received_at": row[1].isoformat(),
                    "timestamp": row[2].isoformat(),
                }

    def purge_before(self, cutoff: datetime, tenant_id: str) -> int:
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute("DELETE FROM watchup.events WHERE received_at < %s AND tenant_id = %s", (cutoff, tenant_id))
                return cursor.rowcount

    def list_tracking_words(self, tenant_id: str, child_id: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    "SELECT word FROM watchup.tracking_words WHERE tenant_id = %s AND child_id = %s ORDER BY position",
                    (tenant_id, child_id),
                )
                return [row[0] for row in cursor.fetchall()]

    def set_tracking_words(self, tenant_id: str, child_id: str, words: list[str]):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute("DELETE FROM watchup.tracking_words WHERE tenant_id = %s AND child_id = %s", (tenant_id, child_id))
                for index, word in enumerate(words):
                    cursor.execute(
                        "INSERT INTO watchup.tracking_words (tenant_id, child_id, position, word, normalized_word) VALUES (%s, %s, %s, %s, %s)",
                        (tenant_id, child_id, index, word, word.casefold()),
                    )

    def delete_family(self, tenant_id: str) -> int:
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute("DELETE FROM watchup.parent_audit WHERE tenant_id = %s", (tenant_id,))
                cursor.execute("DELETE FROM watchup.tracking_words WHERE tenant_id = %s", (tenant_id,))
                cursor.execute("DELETE FROM watchup.events WHERE tenant_id = %s", (tenant_id,))
                return cursor.rowcount

    def append_parent_audit(self, tenant_id: str, username: str, action: str, path: str, client_ip: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """INSERT INTO watchup.parent_audit (tenant_id, username, action, path, client_ip)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (tenant_id, username or None, action, path, client_ip or None),
                )

    def list_parent_audit(self, tenant_id: str, limit: int = 100):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """SELECT username, action, path, client_ip::text, created_at
                       FROM watchup.parent_audit
                       WHERE tenant_id = %s
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (tenant_id, limit),
                )
                return [
                    {
                        "username": row[0],
                        "action": row[1],
                        "path": row[2],
                        "client_ip": row[3],
                        "created_at": row[4].isoformat(),
                    }
                    for row in cursor.fetchall()
                ]


class PostgresAuthStore:
    """Persistent authentication state; all queries use the server-side app role."""
    def __init__(self, event_store: PostgresEventStore):
        self.event_store = event_store

    def _execute(self, sql, params=(), fetch=False):
        with self.event_store.connect_factory(**self.event_store.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL ROLE {APP_ROLE}")
                cursor.execute(sql, params)
                return cursor.fetchone() if fetch else cursor.rowcount

    def create_session(self, token_hash, session):
        self._execute("INSERT INTO watchup.parent_sessions (token_hash, username, expires_at, csrf_hash) VALUES (%s, %s, to_timestamp(%s), %s)", (token_hash, session["username"], session["expires_at"], session["csrf_hash"]))

    def get_session(self, token_hash, _now):
        row = self._execute("SELECT username, extract(epoch FROM expires_at), csrf_hash FROM watchup.parent_sessions WHERE token_hash = %s", (token_hash,), True)
        return {"username": row[0], "expires_at": float(row[1]), "csrf_hash": row[2]} if row else None

    def delete_session(self, token_hash):
        row = self.get_session(token_hash, 0)
        self._execute("DELETE FROM watchup.parent_sessions WHERE token_hash = %s", (token_hash,))
        return row

    def delete_all_sessions(self):
        self._execute("DELETE FROM watchup.parent_sessions")

    def set_csrf_hash(self, token_hash, csrf_hash):
        self._execute("UPDATE watchup.parent_sessions SET csrf_hash = %s WHERE token_hash = %s", (csrf_hash, token_hash))

    def consume_totp_step(self, username, step):
        return self._execute("INSERT INTO watchup.parent_totp_steps (username, last_step) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET last_step = EXCLUDED.last_step WHERE watchup.parent_totp_steps.last_step < EXCLUDED.last_step", (username, step)) == 1


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


def validate_tracking_words(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 30:
        raise ValueError("words must be a list of at most 30 items")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("each tracking word must be text")
        word = "".join(character for character in item.strip() if character not in BIDI_CONTROLS)
        if not word or len(word) > 40:
            raise ValueError("each tracking word must contain 1-40 characters")
        normalized = word.casefold()
        if normalized not in seen:
            seen.add(normalized)
            result.append(word)
    return result


def signature_for(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def cookie_value(raw_cookie: str, name: str) -> str:
    for part in raw_cookie.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name:
            return value
    return ""


def make_handler(
    store, secret: str, tenant_id: str, child_id: str,
    max_body_bytes: int = MAX_BODY_BYTES, dashboard_token: str = "", parent_auth=None, trusted_proxy_ips=(),
):
    def persist_audit(action: str, username: str, path: str, client_ip: str):
        if hasattr(store, "append_parent_audit"):
            store.append_parent_audit(tenant_id, username, action, path, client_ip)

    if parent_auth:
        parent_auth.audit_sink = persist_audit

    class IngestionHandler(BaseHTTPRequestHandler):
        def send_json(self, status, payload, extra_headers=None):
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            for name, value in extra_headers or []:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def parent_session(self):
            token = cookie_value(self.headers.get("Cookie", ""), SESSION_COOKIE)
            return token if parent_auth and token and parent_auth.validate(token) else ""

        def client_ip(self):
            peer = self.client_address[0]
            if peer not in trusted_proxy_ips:
                return peer
            forwarded = self.headers.get("X-Forwarded-For", "").strip()
            if "," in forwarded:
                return peer
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                return peer

        def csrf_ok(self):
            token = self.parent_session()
            return bool(token and parent_auth.csrf_valid(token, self.headers.get("X-WatchUp-CSRF", "")))

        def do_GET(self):
            if self.path == "/watchup/session" and parent_auth:
                token = self.parent_session()
                if not token:
                    self.send_json(HTTPStatus.UNAUTHORIZED, {"authenticated": False})
                    return
                persist_audit(
                    "view_session",
                    parent_auth.username_for_token(token),
                    "/watchup/session",
                    self.client_ip(),
                )
                self.send_json(HTTPStatus.OK, {"authenticated": True, "csrf_token": parent_auth.rotate_csrf(token)})
                return
            if self.path == "/watchup/audit" and parent_auth:
                token = self.parent_session()
                if not token:
                    self.send_error(HTTPStatus.UNAUTHORIZED)
                    return
                username = parent_auth.username_for_token(token)
                persist_audit("view_audit", username, "/watchup/audit", self.client_ip())
                entries = store.list_parent_audit(tenant_id) if hasattr(store, "list_parent_audit") else []
                self.send_json(HTTPStatus.OK, {"entries": entries})
                return
            if self.path != "/watchup/dashboard":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            provided = self.headers.get("Authorization", "")
            bearer_ok = not parent_auth and bool(dashboard_token) and hmac.compare_digest(provided, f"Bearer {dashboard_token}")
            token = self.parent_session()
            if not bearer_ok and not token:
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            if token and parent_auth:
                persist_audit("view_dashboard", parent_auth.username_for_token(token), "/watchup/dashboard", self.client_ip())
            connection_status = (
                store.latest_connection_status(tenant_id, child_id)
                if hasattr(store, "latest_connection_status")
                else None
            )
            body = json.dumps(
                {
                    "child_id": child_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "connection": connection_status,
                    "tracking_words": store.list_tracking_words(tenant_id, child_id) if hasattr(store, "list_tracking_words") else [],
                    "groups": store.list_latest_groups(tenant_id, child_id) if hasattr(store, "list_latest_groups") else [],
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
            if self.path == "/watchup/session":
                if not parent_auth:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                if length < 1 or length > 4096:
                    self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return
                try:
                    credentials = json.loads(self.rfile.read(length).decode("utf-8"))
                    username = credentials.get("username", "").strip()
                    password = credentials.get("password", "")
                    totp_code = credentials.get("totp", "")
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                session, result = parent_auth.login(username, password, totp_code, self.client_ip())
                if result == "rate_limited":
                    self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"authenticated": False})
                    return
                if not session:
                    self.send_json(HTTPStatus.UNAUTHORIZED, {"authenticated": False})
                    return
                token, csrf_token = session
                cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={parent_auth.ttl_seconds}"
                self.send_json(HTTPStatus.OK, {"authenticated": True, "csrf_token": csrf_token}, [("Set-Cookie", cookie)])
                return
            if self.path == "/watchup/tracking-words":
                if not self.csrf_ok():
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 1 or length > 4096:
                        raise ValueError("invalid body length")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    words = validate_tracking_words(payload.get("words"))
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, ValueError):
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                store.set_tracking_words(tenant_id, child_id, words)
                token = cookie_value(self.headers.get("Cookie", ""), SESSION_COOKIE)
                persist_audit("update_tracking_words", parent_auth.username_for_token(token), self.path, self.client_ip())
                self.send_json(HTTPStatus.OK, {"words": words})
                return
            if self.path == "/watchup/family":
                if not self.csrf_ok():
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                token = cookie_value(self.headers.get("Cookie", ""), SESSION_COOKIE)
                username = parent_auth.username_for_token(token) if token else ""
                persist_audit("delete_family", username, "/watchup/family", self.client_ip())
                deleted = store.delete_family(tenant_id)
                parent_auth.revoke_all()
                self.send_json(HTTPStatus.OK, {"deleted_events": deleted})
                return
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

        def do_DELETE(self):
            if self.path != "/watchup/session" or not parent_auth:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not self.csrf_ok():
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            token = cookie_value(self.headers.get("Cookie", ""), SESSION_COOKIE)
            if token:
                parent_auth.logout(token, self.client_ip())
            expired = f"{SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"
            self.send_json(HTTPStatus.OK, {"authenticated": False}, [("Set-Cookie", expired)])

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
        parents_file = os.environ.get("WATCHUP_PARENTS_FILE", "").strip()
        session_secret_file = os.environ.get("WATCHUP_SESSION_SECRET_FILE", "").strip()
        require_totp_value = os.environ.get("WATCHUP_REQUIRE_TOTP", "true").strip().lower()
        if require_totp_value not in {"true", "false"}:
            raise ValueError("WATCHUP_REQUIRE_TOTP must be true or false")
        require_totp = require_totp_value == "true"
        session_ttl_seconds = int(os.environ.get("WATCHUP_SESSION_TTL_SECONDS", "1800"))
        if session_ttl_seconds < 300 or session_ttl_seconds > 2592000:
            raise ValueError("WATCHUP_SESSION_TTL_SECONDS must be between 300 and 2592000")
        if production and (not parents_file or not session_secret_file):
            raise ValueError("production requires at least one parent account and a session secret")
        if parents_file and session_secret_file:
            parent_auth = ParentAuth.from_files(
                parents_file, session_secret_file,
                ttl_seconds=session_ttl_seconds, require_totp=require_totp,
            )
        else:
            parent_auth = None
        dashboard_token = ""
        if not parent_auth:
            dashboard_token = os.environ.get("WATCHUP_DASHBOARD_TOKEN") or required_secret_file("WATCHUP_DASHBOARD_TOKEN_FILE")
            if len(dashboard_token) < 24:
                raise ValueError("WATCHUP_DASHBOARD_TOKEN must be at least 24 characters")
        if parent_auth:
            if store_kind == "postgres":
                parent_auth.session_store = PostgresAuthStore(store)
            else:
                parent_auth.session_store = SQLiteAuthStore(os.environ.get("WATCHUP_AUTH_DB", "watchup-auth.db"))
        retention_days = int(os.environ.get("WATCHUP_RETENTION_DAYS", "14"))
        if retention_days < 1 or retention_days > 365:
            raise ValueError("WATCHUP_RETENTION_DAYS must be between 1 and 365")
        if os.environ.get("WATCHUP_RUN_RETENTION_ONCE") == "1":
            store.purge_before(datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=retention_days), tenant_id)
            return
        trusted_proxy_ips = tuple(ip.strip() for ip in os.environ.get("WATCHUP_TRUSTED_PROXY_IPS", "").split(",") if ip.strip())
        for ip in trusted_proxy_ips:
            ipaddress.ip_address(ip)
        port = int(os.environ.get("WATCHUP_API_PORT", "8769"))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    host = os.environ.get("WATCHUP_API_HOST", "127.0.0.1")
    ThreadingHTTPServer(
        (host, port), make_handler(
            store, secret, tenant_id, child_id,
            dashboard_token=dashboard_token, parent_auth=parent_auth, trusted_proxy_ips=trusted_proxy_ips,
        )
    ).serve_forever()


if __name__ == "__main__":
    main()
