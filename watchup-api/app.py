"""Local WatchUp signed-event ingestion service."""

import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
import base64
import ipaddress
import re
import threading
from datetime import datetime, timezone, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import segno


MAX_BODY_BYTES = 256 * 1024
MAX_CHILDREN = 8
APP_ROLE = "watchup_app"
SESSION_COOKIE = "watchup_parent_session"
BIDI_CONTROLS = frozenset(chr(code) for code in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)))
DAY_KEYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
WINDOW_KEYS = ("study", "evening")
JERUSALEM = ZoneInfo("Asia/Jerusalem")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
BRIDGE_STATES = frozenset(("unpaired", "qr", "timeout", "paired"))


class FamilyRegistry:
    """Families, their children, and the one bridge credential bound to each child.

    Loaded from a protected file (like parents.json). Product code never names a family or child.
    """

    def __init__(self, families: dict):
        self.families = families
        self.bridges = [
            (record["bridge_secret"], tenant, child)
            for tenant, family in families.items()
            for child, record in family["children"].items()
            if record.get("bridge_secret") is not None
        ]

    @classmethod
    def from_file(cls, path: str):
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError("WATCHUP_FAMILIES_FILE cannot be read") from error
        return cls.validate(json.loads(raw))

    @classmethod
    def validate(cls, families: object):
        if not isinstance(families, dict) or not families:
            raise ValueError("families file must define at least one family")
        secrets_seen = set()
        for tenant, family in families.items():
            children = family.get("children") if isinstance(family, dict) else None
            if not isinstance(tenant, str) or not SLUG.match(tenant) or not isinstance(children, dict) or not children:
                raise ValueError("each family needs a slug id and at least one child")
            for child, record in children.items():
                if not isinstance(child, str) or not SLUG.match(child) or not isinstance(record, dict):
                    raise ValueError("child ids must be slugs")
                age, whatsapp = record.get("age"), record.get("has_whatsapp")
                if age is not None and (type(age) is not int or not 1 <= age <= 18):
                    raise ValueError("child age must be an integer from 1 to 18")
                if whatsapp is not None and not isinstance(whatsapp, bool):
                    raise ValueError("has_whatsapp must be true or false")
                secret = record.get("bridge_secret")
                if secret is None:
                    continue
                if not isinstance(secret, str) or len(secret) < 16:
                    raise ValueError("a child bridge_secret must be at least 16 characters")
                if secret in secrets_seen:
                    raise ValueError("bridge secrets must be unique per child")
                secrets_seen.add(secret)
        return cls(families)

    def check_parents(self, parents: dict):
        for username, record in parents.items():
            if not isinstance(record, dict) or record.get("tenant_id") not in self.families:
                raise ValueError(f"parent {username} has no known family")

    def tenant_ids(self):
        return list(self.families)

    def children(self, tenant: str):
        family = self.families.get(tenant) or {}
        children = []
        for child, record in (family.get("children") or {}).items():
            bridge = record.get("bridge_secret") is not None
            whatsapp = record.get("has_whatsapp")
            children.append({
                "child_id": child, "name": record.get("name") or child, "age": record.get("age"),
                "has_whatsapp": bridge if whatsapp is None else whatsapp, "has_bridge": bridge,
            })
        return children

    def has_bridge(self, tenant: str, child: str) -> bool:
        return (self.child(tenant, child) or {}).get("bridge_secret") is not None

    def child(self, tenant: str, child: str):
        return ((self.families.get(tenant) or {}).get("children") or {}).get(child)

    def binding_for_signature(self, body: bytes, provided: str):
        # ponytail: one HMAC per registered bridge. Send a bridge-id header if this reaches hundreds.
        match = None
        for secret, tenant, child in self.bridges:
            if hmac.compare_digest(provided, signature_for(secret, body)):
                match = (tenant, child)
        return match


class PairingBoard:
    """In-memory pairing handshake between a parent and one child's bridge.

    QR codes never reach the database. An API restart drops them; the bridge pushes the next code within 20s.
    """

    REQUEST_TTL = 600
    QR_TTL = 65
    BRIDGE_STALE = 45

    def __init__(self):
        self.lock = threading.Lock()
        self.state = {}

    def _entry(self, key):
        return self.state.setdefault(key, {"requested_at": None, "code": None, "qr_at": None, "seen_at": None, "result": None})

    def request(self, key, now):
        with self.lock:
            entry = self._entry(key)
            entry.update(requested_at=now, code=None, qr_at=None, result=None)

    def cancel(self, key):
        with self.lock:
            self._entry(key).update(requested_at=None, code=None, qr_at=None, result="cancelled")

    def _requested(self, entry, now):
        return entry["requested_at"] is not None and now - entry["requested_at"] < self.REQUEST_TTL

    def bridge_report(self, key, state, code, now) -> bool:
        with self.lock:
            entry = self._entry(key)
            entry["seen_at"] = now
            requested = self._requested(entry, now)
            if state == "qr" and requested:
                entry.update(code=code, qr_at=now)
            elif state in ("timeout", "paired"):
                entry.update(requested_at=None, code=None, qr_at=None, result=state)
                return False
            return requested

    def view(self, key, now) -> dict:
        with self.lock:
            entry = dict(self._entry(key))
        bridge_seen = entry["seen_at"] is not None and now - entry["seen_at"] < self.BRIDGE_STALE
        if self._requested(entry, now):
            if entry["code"] and now - entry["qr_at"] < self.QR_TTL:
                return {"state": "waiting", "code": entry["code"]}
            return {"state": "requested" if bridge_seen else "bridge_unavailable"}
        if entry["result"] == "timeout":
            return {"state": "timeout"}
        return {"state": "not_connected", "bridge_seen": bridge_seen}


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
        return bool(session and session["expires_at"] > now and isinstance(csrf_token, str) and csrf_token.isascii()
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

    def revoke_usernames(self, usernames):
        names = {name for name in usernames if isinstance(name, str)}
        if self.session_store:
            self.session_store.delete_usernames(names)
            return
        for token_hash, session in list(self.sessions.items()):
            if session.get("username") in names:
                self.sessions.pop(token_hash, None)


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

    def delete_usernames(self, usernames):
        self.db.executemany("DELETE FROM parent_sessions WHERE username = ?", [(name,) for name in usernames])
        self.db.commit()

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
                PRIMARY KEY (tenant_id, child_id, event_id)
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
            CREATE TABLE IF NOT EXISTS child_settings (
                tenant_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                schedule_json TEXT NOT NULL,
                PRIMARY KEY (tenant_id, child_id)
            );
            CREATE TABLE IF NOT EXISTS child_profiles (
                tenant_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                age INTEGER,
                has_whatsapp INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, child_id)
            );
            CREATE TABLE IF NOT EXISTS family_onboarding (
                tenant_id TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL,
                completed_by TEXT NOT NULL
            );
            """
        )

    def insert(self, event: dict, received_at: datetime) -> bool:
        source_at = parse_timestamp(event["source_timestamp"])
        latency_ms = max(0, int((received_at - source_at).total_seconds() * 1000))
        try:
            cursor = self.db.execute(
                """INSERT INTO events (
                    tenant_id, child_id, event_id, event_type, source,
                    source_timestamp, account_json, payload_json, received_at, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, child_id, event_id) DO UPDATE SET
                    source_timestamp = excluded.source_timestamp,
                    account_json = excluded.account_json,
                    payload_json = excluded.payload_json,
                    received_at = excluded.received_at,
                    latency_ms = excluded.latency_ms
                WHERE events.event_type = 'group.snapshot'""",
                (
                    event["tenant_id"], event["child_id"], event["event_id"],
                    event["type"], event["source"], event["source_timestamp"],
                    json.dumps(event["account"], ensure_ascii=False, separators=(",", ":")),
                    json.dumps(event["payload"], ensure_ascii=False, separators=(",", ":")),
                    received_at.isoformat(), latency_ms,
                ),
            )
            self.db.commit()
            return cursor.rowcount == 1
        except sqlite3.IntegrityError:
            return False

    def get(self, tenant_id: str, child_id: str, event_id: str):
        return self.db.execute(
            "SELECT event_id FROM events WHERE tenant_id = ? AND child_id = ? AND event_id = ?",
            (tenant_id, child_id, event_id),
        ).fetchone()

    def pairing_floor(self, tenant_id: str, child_id: str):
        relink = self.db.execute(
            """SELECT received_at FROM events
                WHERE tenant_id = ? AND child_id = ? AND event_type = 'connection.status'
                  AND json_extract(account_json, '$.status') = 'relink_required'
                ORDER BY received_at DESC LIMIT 1""",
            (tenant_id, child_id),
        ).fetchone()
        if not relink:
            return None
        connected = self.db.execute(
            """SELECT received_at FROM events
                WHERE tenant_id = ? AND child_id = ? AND event_type = 'connection.status'
                  AND json_extract(account_json, '$.status') = 'connected'
                  AND received_at >= ?
                ORDER BY received_at ASC LIMIT 1""",
            (tenant_id, child_id, relink[0]),
        ).fetchone()
        return connected[0] if connected else relink[0]

    def list_recent(self, tenant_id: str, child_id: str, limit: int = 200):
        # ponytail: newest 200 messages and connection events. Group snapshots
        # refresh their own received_at and would otherwise push live messages
        # out of this window. A busier day needs paging, not a larger blob.
        floor = self.pairing_floor(tenant_id, child_id)
        rows = self.db.execute(
            """SELECT event_id, event_type, source_timestamp, account_json, payload_json,
                      received_at, latency_ms
               FROM events
              WHERE tenant_id = ? AND child_id = ?
                AND event_type <> 'group.snapshot'
                AND event_type <> 'connection.status'
                AND (? IS NULL OR received_at >= ?)
              ORDER BY received_at DESC
              LIMIT ?""",
            (tenant_id, child_id, floor, floor, limit),
        ).fetchall()
        events = [
            {
                "event_id": row[0], "type": row[1], "timestamp": row[2],
                "account": json.loads(row[3]), "payload": json.loads(row[4]),
                "received_at": row[5], "latency_ms": row[6],
            }
            for row in rows
        ]
        since = jerusalem_day_start().isoformat()
        extra_rows = self.db.execute(
            """SELECT event_id, event_type, source_timestamp, account_json, payload_json,
                      received_at, latency_ms
               FROM events
              WHERE tenant_id = ? AND child_id = ?
                AND event_type <> 'group.snapshot'
                AND event_type <> 'connection.status'
                AND received_at >= ?
                AND (? IS NULL OR received_at >= ?)
              ORDER BY received_at DESC
              LIMIT 500""",
            (tenant_id, child_id, since, floor, floor),
        ).fetchall()
        extra = [
            {
                "event_id": row[0], "type": row[1], "timestamp": row[2],
                "account": json.loads(row[3]), "payload": json.loads(row[4]),
                "received_at": row[5], "latency_ms": row[6],
            }
            for row in extra_rows
        ]
        # ponytail: newest 200 plus Jerusalem-today rows, capped at 500. A louder day needs paging.
        return merge_recent(events, extra)

    def list_latest_groups(self, tenant_id: str, child_id: str, limit: int = 100):
        rows = self.db.execute(
            """SELECT event_id, event_type, source_timestamp, account_json, payload_json,
                      received_at, latency_ms,
                      (SELECT MIN(older.received_at) FROM events AS older
                        WHERE older.tenant_id = ranked.tenant_id
                          AND older.child_id = ranked.child_id
                          AND older.event_type = 'group.snapshot'
                          AND json_extract(older.account_json, '$.chat_jid')
                              = json_extract(ranked.account_json, '$.chat_jid'))
               FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY json_extract(account_json, '$.chat_jid')
                        ORDER BY received_at DESC
                    ) AS newest
                    FROM events
                    WHERE tenant_id = ? AND child_id = ? AND event_type = 'group.snapshot'
                      AND (? IS NULL OR received_at >= ?)
               ) AS ranked
              WHERE newest = 1
              ORDER BY received_at DESC
              LIMIT ?""",
            (tenant_id, child_id, self.pairing_floor(tenant_id, child_id), self.pairing_floor(tenant_id, child_id), limit),
        ).fetchall()
        return [
            {
                "event_id": row[0], "type": row[1], "timestamp": row[2],
                "account": json.loads(row[3]), "payload": json.loads(row[4]),
                "received_at": row[5], "latency_ms": row[6], "first_seen": row[7],
            }
            for row in rows
        ]

    def list_membership_changes(self, tenant_id: str, child_id: str):
        floor = self.pairing_floor(tenant_id, child_id)
        rows = self.db.execute(
            """SELECT json_extract(account_json, '$.chat_jid'),
                      json_extract(payload_json, '$.name'),
                      json_extract(payload_json, '$.participants'),
                      newest
               FROM (
                    SELECT account_json, payload_json,
                           ROW_NUMBER() OVER (
                               PARTITION BY json_extract(account_json, '$.chat_jid')
                               ORDER BY received_at DESC
                           ) AS newest
                      FROM events
                     WHERE tenant_id = ? AND child_id = ? AND event_type = 'group.snapshot'
                       AND (? IS NULL OR received_at >= ?)
               )
              WHERE newest <= 2""",
            (tenant_id, child_id, floor, floor),
        ).fetchall()
        return changes_from_snapshot_rows(rows)

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

    def purge_before(self, cutoff: datetime, tenant_id: str, child_id: str = None) -> int:
        cursor = self.db.execute(
            "DELETE FROM events WHERE received_at < ? AND tenant_id = ? AND (? IS NULL OR child_id = ?)",
            (cutoff.isoformat(), tenant_id, child_id, child_id),
        )
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

    def get_schedule(self, tenant_id: str, child_id: str):
        row = self.db.execute(
            "SELECT schedule_json FROM child_settings WHERE tenant_id = ? AND child_id = ?",
            (tenant_id, child_id),
        ).fetchone()
        if not row:
            return empty_schedule()
        try:
            return validate_schedule(json.loads(row[0]))
        except (json.JSONDecodeError, ValueError):
            return empty_schedule()

    def set_schedule(self, tenant_id: str, child_id: str, schedule: dict):
        payload = json.dumps(validate_schedule(schedule), ensure_ascii=False, separators=(",", ":"))
        self.db.execute(
            """INSERT INTO child_settings (tenant_id, child_id, schedule_json) VALUES (?, ?, ?)
               ON CONFLICT(tenant_id, child_id) DO UPDATE SET schedule_json = excluded.schedule_json""",
            (tenant_id, child_id, payload),
        )
        self.db.commit()

    def delete_family(self, tenant_id: str) -> int:
        cursor = self.db.execute("DELETE FROM events WHERE tenant_id = ?", (tenant_id,))
        self.db.execute("DELETE FROM tracking_words WHERE tenant_id = ?", (tenant_id,))
        self.db.execute("DELETE FROM child_settings WHERE tenant_id = ?", (tenant_id,))
        self.db.execute("DELETE FROM child_profiles WHERE tenant_id = ?", (tenant_id,))
        self.db.execute("DELETE FROM family_onboarding WHERE tenant_id = ?", (tenant_id,))
        self.db.execute("DELETE FROM parent_audit WHERE tenant_id = ?", (tenant_id,))
        self.db.commit()
        return cursor.rowcount

    def list_child_profiles(self, tenant_id: str):
        rows = self.db.execute(
            "SELECT child_id, display_name, age, has_whatsapp FROM child_profiles WHERE tenant_id = ?", (tenant_id,)
        ).fetchall()
        return {row[0]: {"display_name": row[1], "age": row[2], "has_whatsapp": bool(row[3])} for row in rows}

    def upsert_child_profile(self, tenant_id: str, child_id: str, display_name: str, age, has_whatsapp: bool, username: str):
        self.db.execute(
            """INSERT INTO child_profiles (tenant_id, child_id, display_name, age, has_whatsapp, created_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id, child_id) DO UPDATE SET display_name = excluded.display_name,
                   age = excluded.age, has_whatsapp = excluded.has_whatsapp, updated_at = excluded.updated_at""",
            (tenant_id, child_id, display_name, age, int(bool(has_whatsapp)), username, datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()

    def get_onboarding(self, tenant_id: str):
        row = self.db.execute("SELECT completed_at FROM family_onboarding WHERE tenant_id = ?", (tenant_id,)).fetchone()
        return row[0] if row else None

    def complete_onboarding(self, tenant_id: str, username: str):
        self.db.execute(
            """INSERT INTO family_onboarding (tenant_id, completed_at, completed_by) VALUES (?, ?, ?)
               ON CONFLICT(tenant_id) DO UPDATE SET completed_at = excluded.completed_at, completed_by = excluded.completed_by""",
            (tenant_id, datetime.now(timezone.utc).isoformat(), username),
        )
        self.db.commit()

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

    def missing_tables(self, names) -> list:
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL ROLE {APP_ROLE}")
                cursor.execute("SELECT name FROM unnest(%s::text[]) AS name WHERE to_regclass(name) IS NULL", (list(names),))
                return [row[0] for row in cursor.fetchall()]

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
                    ON CONFLICT (tenant_id, child_id, event_id) DO UPDATE SET
                        source_timestamp = EXCLUDED.source_timestamp,
                        account = EXCLUDED.account,
                        payload = EXCLUDED.payload,
                        received_at = EXCLUDED.received_at,
                        latency_ms = EXCLUDED.latency_ms
                    WHERE watchup.events.event_type = 'group.snapshot'""",
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

    def pairing_floor(self, tenant_id: str, child_id: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """SELECT received_at FROM watchup.events
                        WHERE tenant_id = %s AND child_id = %s AND event_type = 'connection.status'
                          AND account->>'status' = 'relink_required'
                        ORDER BY received_at DESC LIMIT 1""",
                    (tenant_id, child_id),
                )
                relink = cursor.fetchone()
                if not relink:
                    return None
                cursor.execute(
                    """SELECT received_at FROM watchup.events
                        WHERE tenant_id = %s AND child_id = %s AND event_type = 'connection.status'
                          AND account->>'status' = 'connected' AND received_at >= %s
                        ORDER BY received_at ASC LIMIT 1""",
                    (tenant_id, child_id, relink[0]),
                )
                connected = cursor.fetchone()
                return connected[0] if connected else relink[0]

    def list_recent(self, tenant_id: str, child_id: str, limit: int = 200):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                floor = self.pairing_floor(tenant_id, child_id)
                cursor.execute(
                    """SELECT event_id, event_type, source_timestamp, account, payload,
                              received_at, latency_ms
                       FROM watchup.events
                      WHERE tenant_id = %s AND child_id = %s
                        AND event_type <> 'group.snapshot'
                        AND event_type <> 'connection.status'
                        AND (CAST(%s AS timestamptz) IS NULL OR received_at >= CAST(%s AS timestamptz))
                      ORDER BY received_at DESC
                      LIMIT %s""",
                    (tenant_id, child_id, floor, floor, limit),
                )
                events = [postgres_event(row) for row in cursor.fetchall()]
                since = jerusalem_day_start()
                cursor.execute(
                    """SELECT event_id, event_type, source_timestamp, account, payload,
                              received_at, latency_ms
                       FROM watchup.events
                      WHERE tenant_id = %s AND child_id = %s
                        AND event_type <> 'group.snapshot'
                        AND event_type <> 'connection.status'
                        AND received_at >= %s
                        AND (CAST(%s AS timestamptz) IS NULL OR received_at >= CAST(%s AS timestamptz))
                      ORDER BY received_at DESC
                      LIMIT 500""",
                    (tenant_id, child_id, since, floor, floor),
                )
                # ponytail: newest 200 plus Jerusalem-today rows, capped at 500. A louder day needs paging.
                return merge_recent(events, [postgres_event(row) for row in cursor.fetchall()])

    def list_latest_groups(self, tenant_id: str, child_id: str, limit: int = 100):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """SELECT event_id, event_type, source_timestamp, account, payload, received_at, latency_ms,
                              (SELECT MIN(older.received_at) FROM watchup.events AS older
                                WHERE older.tenant_id = latest_groups.tenant_id
                                  AND older.child_id = latest_groups.child_id
                                  AND older.event_type = 'group.snapshot'
                                  AND older.account->>'chat_jid' = latest_groups.account->>'chat_jid')
                       FROM (
                            SELECT DISTINCT ON (account->>'chat_jid')
                                   tenant_id, child_id, event_id, event_type, source_timestamp, account, payload, received_at, latency_ms
                            FROM watchup.events
                            WHERE tenant_id = %s AND child_id = %s AND event_type = 'group.snapshot'
                              AND (CAST(%s AS timestamptz) IS NULL OR received_at >= CAST(%s AS timestamptz))
                            ORDER BY account->>'chat_jid', received_at DESC
                       ) AS latest_groups
                       ORDER BY received_at DESC
                       LIMIT %s""",
                    (tenant_id, child_id, self.pairing_floor(tenant_id, child_id), self.pairing_floor(tenant_id, child_id), limit),
                )
                return [
                    postgres_event(row, first_seen=row[7] if len(row) > 7 else None)
                    for row in cursor.fetchall()
                ]

    def list_membership_changes(self, tenant_id: str, child_id: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                floor = self.pairing_floor(tenant_id, child_id)
                cursor.execute(
                    """SELECT chat_jid, name, participants, newest
                       FROM (
                            SELECT account->>'chat_jid' AS chat_jid,
                                   payload->>'name' AS name,
                                   payload->'participants' AS participants,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY account->>'chat_jid'
                                       ORDER BY received_at DESC
                                   ) AS newest
                              FROM watchup.events
                             WHERE tenant_id = %s AND child_id = %s AND event_type = 'group.snapshot'
                               AND (CAST(%s AS timestamptz) IS NULL OR received_at >= CAST(%s AS timestamptz))
                       ) AS ranked
                      WHERE newest <= 2""",
                    (tenant_id, child_id, floor, floor),
                )
                return changes_from_snapshot_rows(cursor.fetchall())

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

    def purge_before(self, cutoff: datetime, tenant_id: str, child_id: str = None) -> int:
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    "DELETE FROM watchup.events WHERE received_at < %s AND tenant_id = %s AND (CAST(%s AS text) IS NULL OR child_id = %s)",
                    (cutoff, tenant_id, child_id, child_id),
                )
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

    def get_schedule(self, tenant_id: str, child_id: str):
        try:
            with self.connect_factory(**self.connection_kwargs) as connection:
                with connection.cursor() as cursor:
                    self._set_rls_context(cursor, tenant_id)
                    cursor.execute(
                        "SELECT schedule FROM watchup.child_settings WHERE tenant_id = %s AND child_id = %s",
                        (tenant_id, child_id),
                    )
                    row = cursor.fetchone()
        except Exception as error:
            if getattr(error, "sqlstate", None) != "42P01":
                raise
            return empty_schedule()
        if not row:
            return empty_schedule()
        raw = row[0]
        if isinstance(raw, str):
            raw = json.loads(raw)
        try:
            return validate_schedule(raw)
        except (TypeError, ValueError):
            return empty_schedule()

    def set_schedule(self, tenant_id: str, child_id: str, schedule: dict):
        payload = validate_schedule(schedule)
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """INSERT INTO watchup.child_settings (tenant_id, child_id, schedule)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (tenant_id, child_id) DO UPDATE SET schedule = EXCLUDED.schedule""",
                    (tenant_id, child_id, self.jsonb_factory(payload)),
                )

    def delete_family(self, tenant_id: str) -> int:
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute("DELETE FROM watchup.parent_audit WHERE tenant_id = %s", (tenant_id,))
                cursor.execute("DELETE FROM watchup.tracking_words WHERE tenant_id = %s", (tenant_id,))
                cursor.execute("DELETE FROM watchup.child_settings WHERE tenant_id = %s", (tenant_id,))
                # 007 may not be applied (legacy Production); a missing table must not abort this delete.
                cursor.execute("SELECT to_regclass('watchup.child_profiles') IS NOT NULL")
                if cursor.fetchone()[0]:
                    cursor.execute("DELETE FROM watchup.child_profiles WHERE tenant_id = %s", (tenant_id,))
                    cursor.execute("DELETE FROM watchup.family_onboarding WHERE tenant_id = %s", (tenant_id,))
                cursor.execute("DELETE FROM watchup.events WHERE tenant_id = %s", (tenant_id,))
                return cursor.rowcount

    def _read_optional(self, tenant_id: str, sql: str, one: bool = False):
        try:
            with self.connect_factory(**self.connection_kwargs) as connection:
                with connection.cursor() as cursor:
                    self._set_rls_context(cursor, tenant_id)
                    cursor.execute(sql, (tenant_id,))
                    return cursor.fetchone() if one else cursor.fetchall()
        except Exception as error:
            if getattr(error, "sqlstate", None) != "42P01":
                raise
            return None if one else []

    def list_child_profiles(self, tenant_id: str):
        rows = self._read_optional(
            tenant_id, "SELECT child_id, display_name, age, has_whatsapp FROM watchup.child_profiles WHERE tenant_id = %s"
        )
        return {row[0]: {"display_name": row[1], "age": row[2], "has_whatsapp": bool(row[3])} for row in rows}

    def upsert_child_profile(self, tenant_id: str, child_id: str, display_name: str, age, has_whatsapp: bool, username: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """INSERT INTO watchup.child_profiles (tenant_id, child_id, display_name, age, has_whatsapp, created_by)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (tenant_id, child_id) DO UPDATE SET display_name = EXCLUDED.display_name,
                           age = EXCLUDED.age, has_whatsapp = EXCLUDED.has_whatsapp, updated_at = now()""",
                    (tenant_id, child_id, display_name, age, bool(has_whatsapp), username),
                )

    def get_onboarding(self, tenant_id: str):
        row = self._read_optional(tenant_id, "SELECT completed_at FROM watchup.family_onboarding WHERE tenant_id = %s", one=True)
        return row[0].isoformat() if row else None

    def complete_onboarding(self, tenant_id: str, username: str):
        with self.connect_factory(**self.connection_kwargs) as connection:
            with connection.cursor() as cursor:
                self._set_rls_context(cursor, tenant_id)
                cursor.execute(
                    """INSERT INTO watchup.family_onboarding (tenant_id, completed_at, completed_by)
                       VALUES (%s, now(), %s)
                       ON CONFLICT (tenant_id) DO UPDATE SET completed_at = EXCLUDED.completed_at,
                           completed_by = EXCLUDED.completed_by""",
                    (tenant_id, username),
                )

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

    def delete_usernames(self, usernames):
        for name in usernames:
            self._execute("DELETE FROM watchup.parent_sessions WHERE username = %s", (name,))

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


def parse_participants(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def participant_labels(people):
    labels = {}
    for person in parse_participants(people):
        if not isinstance(person, dict):
            continue
        phone = str(person.get("phone") or "").strip()
        name = str(person.get("name") or "").strip()
        key = phone or name
        if key:
            labels[key] = name or phone
    return labels


def membership_delta(previous, current):
    before = participant_labels(previous)
    after = participant_labels(current)
    return (
        [after[key] for key in after if key not in before],
        [before[key] for key in before if key not in after],
    )


def changes_from_snapshot_rows(rows):
    grouped = {}
    for chat_jid, name, participants, newest in rows:
        if not chat_jid:
            continue
        grouped.setdefault(chat_jid, {})[int(newest)] = (name or "", participants)
    changes = []
    for chat_jid, versions in grouped.items():
        if 1 not in versions or 2 not in versions:
            continue
        added, left = membership_delta(versions[2][1], versions[1][1])
        if not added and not left:
            continue
        changes.append({
            "chat_jid": chat_jid,
            "name": versions[1][0] or "קבוצה",
            "added": added[:12],
            "left": left[:12],
        })
    return changes


def isoformat_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def postgres_event(row, first_seen=None):
    event = {
        "event_id": row[0], "type": row[1], "timestamp": isoformat_value(row[2]),
        "account": row[3], "payload": row[4],
        "received_at": isoformat_value(row[5]), "latency_ms": row[6],
    }
    if first_seen is not None or len(row) > 7:
        event["first_seen"] = isoformat_value(row[7] if first_seen is None else first_seen)
    return event


def slim_group_for_dashboard(event):
    """Shrink group rows for the parent dashboard JSON.

    ponytail: base64 avatars + full participant lists (~500KB+) aborted parent
    browsers mid-download (BrokenPipe) and froze the UI. Keep counts only.
    """
    if not isinstance(event, dict):
        return event
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return event
    people = payload.get("participants") if isinstance(payload.get("participants"), list) else []
    slim_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"imageBase64", "participants"}
    }
    if payload.get("imageBase64"):
        slim_payload["has_image"] = True
    slim_payload["unrecognized_count"] = sum(
        1 for person in people if not isinstance(person, dict) or person.get("isRecognized") is not True
    )
    if "participantCount" not in slim_payload:
        slim_payload["participantCount"] = len(people)
    return {**event, "payload": slim_payload}


def merge_recent(primary, extra, limit=500):
    seen = set()
    merged = []
    for item in list(primary) + list(extra):
        event_id = item.get("event_id")
        if event_id in seen:
            continue
        seen.add(event_id)
        merged.append(item)
    merged.sort(key=lambda item: item.get("received_at") or "", reverse=True)
    return merged[:limit]


def jerusalem_day_start(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(JERUSALEM)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def empty_schedule():
    return {day: {"study": None, "evening": None} for day in DAY_KEYS}


def clock_value(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("time must be HH:MM")
    hour, minute = value.split(":")
    if not hour.isdigit() or not minute.isdigit():
        raise ValueError("time must be HH:MM")
    hour_i, minute_i = int(hour), int(minute)
    if hour_i > 23 or minute_i > 59:
        raise ValueError("time must be HH:MM")
    return f"{hour_i:02d}:{minute_i:02d}"


def validate_schedule(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("schedule must be an object")
    result = empty_schedule()
    for day in DAY_KEYS:
        raw = value.get(day) or {}
        if not isinstance(raw, dict):
            raise ValueError("each day must be an object")
        for window in WINDOW_KEYS:
            pair = raw.get(window)
            if pair in (None, "", []):
                result[day][window] = None
                continue
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("a window is two times")
            start, end = clock_value(pair[0]), clock_value(pair[1])
            if start >= end:
                raise ValueError("window start must be before end")
            result[day][window] = [start, end]
    return result


def connection_is_live(status, now=None) -> bool:
    if not status or (status.get("account") or {}).get("status") != "connected":
        return False
    try:
        received = parse_timestamp(status["received_at"])
    except (KeyError, TypeError, ValueError):
        return False
    now = now or datetime.now(timezone.utc)
    return now - received < timedelta(minutes=6)


def pairing_payload(status, qr_path: str) -> dict:
    # Reading the existing code does not ask the bridge for a new one.
    if connection_is_live(status):
        return {"state": "connected", "svg": None}
    path = Path(qr_path) if qr_path else None
    if path is None:
        return {"state": "unavailable", "svg": None}
    try:
        if not path.is_file():
            return {"state": "unavailable", "svg": None}
        age = time.time() - path.stat().st_mtime
        code = path.read_text(encoding="utf-8").strip()
    except OSError:
        return {"state": "unavailable", "svg": None}
    if not code or age > 3600 or len(code) > 512 or any(character in code for character in "\r\n"):
        return {"state": "unavailable", "svg": None}
    return {"state": "waiting", "svg": qr_svg(code)}


def qr_svg(code: str) -> str:
    # A data-URI <img> needs a standalone SVG (with xmlns); svg_inline() omits it and renders blank.
    buffer = io.BytesIO()
    segno.make(code, error="m").save(buffer, kind="svg", scale=6, xmldecl=False, nl=False)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def validate_child_profile(value: object) -> tuple:
    if not isinstance(value, dict):
        raise ValueError("profile must be an object")
    name, age, has_whatsapp = value.get("display_name"), value.get("age"), value.get("has_whatsapp")
    name = name.strip() if isinstance(name, str) else ""
    if not 1 <= len(name) <= 40 or any(ch in BIDI_CONTROLS or ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("invalid display name")
    if isinstance(age, bool) or not isinstance(age, int) or not 1 <= age <= 18:
        raise ValueError("invalid age")
    if not isinstance(has_whatsapp, bool):
        raise ValueError("invalid has_whatsapp")
    return name, age, has_whatsapp


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
    qr_path: str = "", families: FamilyRegistry = None, pairing: PairingBoard = None,
):
    pairing = pairing or PairingBoard()

    def tenant_for(username: str) -> str:
        record = parent_auth.parents.get(username) if parent_auth and username else None
        if isinstance(record, dict) and record.get("tenant_id"):
            return record["tenant_id"]
        # Multi-Family never falls back to the process tenant.
        return "" if families else tenant_id

    def scope_for(token: str, requested_child: str = None):
        """Server-side (tenant, child, children) for this request, or None to fail closed."""
        if not (parent_auth and token):
            if families or requested_child not in (None, child_id):
                return None
            return tenant_id, child_id, [{"child_id": child_id, "name": ""}]
        username = parent_auth.username_for_token(token)
        record = parent_auth.parents.get(username) if username else None
        tenant = tenant_for(username) if isinstance(record, dict) else ""
        if not tenant:
            return None
        if families:
            children = family_children(tenant)
        else:
            children = [{"child_id": record.get("child_id") or child_id, "name": ""}]
        ids = [child["child_id"] for child in children]
        if not ids:
            return None
        if requested_child is None:
            return tenant, ids[0], children
        return (tenant, requested_child, children) if requested_child in ids else None

    def bridge_binding(body: bytes, provided: str):
        if not provided.isascii():
            # compare_digest raises on non-ASCII text; a forged header is just unauthenticated.
            return None
        if families:
            return families.binding_for_signature(body, provided)
        return (tenant_id, child_id) if hmac.compare_digest(provided, signature_for(secret, body)) else None

    def family_children(tenant: str):
        """Registry children plus parent-added ones; DB profile fields override the admin seed."""
        children = [dict(child) for child in families.children(tenant)]
        profiles = store.list_child_profiles(tenant) if hasattr(store, "list_child_profiles") else {}
        for child in children:
            profile = profiles.pop(child["child_id"], None)
            if profile:
                child.update(name=profile["display_name"], age=profile["age"], has_whatsapp=profile["has_whatsapp"])
        for child_id in sorted(profiles):
            profile = profiles[child_id]
            children.append({"child_id": child_id, "name": profile["display_name"], "age": profile["age"],
                             "has_whatsapp": profile["has_whatsapp"], "has_bridge": False})
        return children

    def with_connection(tenant: str, children):
        live = hasattr(store, "latest_connection_status")
        return [{**child, "connected": live and connection_is_live(store.latest_connection_status(tenant, child["child_id"]))}
                for child in children]

    def pairing_view(scoped_tenant: str, scoped_child: str) -> dict:
        status = store.latest_connection_status(scoped_tenant, scoped_child) if hasattr(store, "latest_connection_status") else None
        if not families:
            return pairing_payload(status, qr_path)
        if connection_is_live(status):
            return {"state": "connected", "svg": None}
        if not families.has_bridge(scoped_tenant, scoped_child):
            return {"state": "no_bridge", "svg": None}
        view = pairing.view((scoped_tenant, scoped_child), time.time())
        if view["state"] == "waiting":
            return {"state": "waiting", "svg": qr_svg(view["code"])}
        legacy_file = (families.child(scoped_tenant, scoped_child) or {}).get("qr_file")
        if view["state"] == "not_connected" and legacy_file:
            legacy = pairing_payload(status, legacy_file)
            if legacy["state"] == "waiting":
                return legacy
        return {"state": view["state"], "svg": None}

    def persist_audit(action: str, username: str, path: str, client_ip: str):
        if not hasattr(store, "append_parent_audit"):
            return
        audit_tenant = tenant_for(username)
        if not audit_tenant:
            # ponytail: an unknown username has no family, so it stays in the in-memory log only.
            return
        if action == "view_dashboard" and hasattr(store, "list_parent_audit"):
            # ponytail: one dashboard line per 10 minutes. The 5s refresh would otherwise fill the log.
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
            for row in store.list_parent_audit(audit_tenant, limit=30):
                if row.get("username") != username or row.get("action") != action:
                    continue
                created = row.get("created_at")
                if isinstance(created, str):
                    created = datetime.fromisoformat(created)
                if getattr(created, "tzinfo", None) is None:
                    created = created.replace(tzinfo=timezone.utc)
                if created >= cutoff:
                    return
                break
        store.append_parent_audit(audit_tenant, username, action, path, client_ip)

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

        def route(self):
            """Path plus the single requested child_id (None when absent, "" when malformed)."""
            parts = urlsplit(self.path)
            values = parse_qs(parts.query, keep_blank_values=True).get("child_id")
            requested = None if values is None else (values[0] if len(values) == 1 else "")
            return parts.path, requested

        def parent_scope(self, requested_child):
            """(token, scope). Sends 401/403 itself and returns scope None when the request must stop."""
            token = self.parent_session()
            if not token:
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return token, None
            scope = scope_for(token, requested_child)
            if not scope:
                self.send_error(HTTPStatus.FORBIDDEN)
            return token, scope

        def read_json(self, limit):
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > limit:
                raise ValueError("invalid body length")
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self):
            path, requested_child = self.route()
            if path == "/watchup/session" and parent_auth:
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
            if path == "/watchup/audit" and parent_auth:
                token, scope = self.parent_scope(None)
                if not scope:
                    return
                username = parent_auth.username_for_token(token)
                persist_audit("view_audit", username, "/watchup/audit", self.client_ip())
                entries = store.list_parent_audit(scope[0]) if hasattr(store, "list_parent_audit") else []
                self.send_json(HTTPStatus.OK, {"entries": entries})
                return
            if path == "/watchup/pairing" and parent_auth:
                _token, scope = self.parent_scope(requested_child)
                if not scope:
                    return
                self.send_json(HTTPStatus.OK, pairing_view(scope[0], scope[1]))
                return
            if path == "/watchup/onboarding" and families:
                _token, scope = self.parent_scope(None)
                if not scope:
                    return
                tenant = scope[0]
                self.send_json(HTTPStatus.OK, {
                    "completed": bool(store.get_onboarding(tenant)),
                    "family_name": (families.families.get(tenant) or {}).get("name", ""),
                    "children": [{**child, "tracking_words": store.list_tracking_words(tenant, child["child_id"]),
                                  "schedule": store.get_schedule(tenant, child["child_id"])}
                                 for child in with_connection(tenant, scope[2])],
                })
                return
            if path != "/watchup/dashboard":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            provided = self.headers.get("Authorization", "")
            bearer_ok = not parent_auth and bool(dashboard_token) and hmac.compare_digest(provided, f"Bearer {dashboard_token}")
            token = self.parent_session()
            if not bearer_ok and not token:
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            scope = scope_for(token, requested_child)
            if not scope:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            scoped_tenant, scoped_child, children = scope
            if token and parent_auth:
                persist_audit("view_dashboard", parent_auth.username_for_token(token), "/watchup/dashboard", self.client_ip())
            connection_status = (
                store.latest_connection_status(scoped_tenant, scoped_child)
                if hasattr(store, "latest_connection_status")
                else None
            )
            groups = store.list_latest_groups(scoped_tenant, scoped_child) if hasattr(store, "list_latest_groups") else []
            body = json.dumps(
                {
                    "child_id": scoped_child,
                    "children": with_connection(scoped_tenant, children) if families else children,
                    "onboarding_completed": not families or bool(store.get_onboarding(scoped_tenant)),
                    "family_name": (families.families.get(scoped_tenant) or {}).get("name", "") if families else "",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "connection": connection_status,
                    "tracking_words": store.list_tracking_words(scoped_tenant, scoped_child) if hasattr(store, "list_tracking_words") else [],
                    "schedule": store.get_schedule(scoped_tenant, scoped_child) if hasattr(store, "get_schedule") else empty_schedule(),
                    "groups": [slim_group_for_dashboard(group) for group in groups],
                    "group_changes": store.list_membership_changes(scoped_tenant, scoped_child) if hasattr(store, "list_membership_changes") else [],
                    "events": store.list_recent(scoped_tenant, scoped_child),
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
            path, requested_child = self.route()
            if path == "/watchup/session":
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
            if path == "/watchup/bridge/pairing":
                self.bridge_pairing()
                return
            if path in ("/watchup/children", "/watchup/onboarding"):
                if not families:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if not self.csrf_ok():
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                token, scope = self.parent_scope(requested_child if path == "/watchup/children" else None)
                if not scope:
                    return
                tenant, _child, children = scope
                username = parent_auth.username_for_token(token)
                if path == "/watchup/onboarding":
                    missing = [child["child_id"] for child in children if not child.get("name") or not child.get("age")]
                    if missing:
                        self.send_json(HTTPStatus.CONFLICT, {"missing": missing})
                        return
                    store.complete_onboarding(tenant, username)
                    persist_audit("complete_onboarding", username, path, self.client_ip())
                    self.send_json(HTTPStatus.OK, {"completed": True})
                    return
                try:
                    name, age, has_whatsapp = validate_child_profile(self.read_json(2048))
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                if requested_child is None:
                    # ponytail: count-then-insert; two parallel adds can pass the cap by one. Move the check into the INSERT if it matters.
                    if len(children) >= MAX_CHILDREN:
                        self.send_json(HTTPStatus.CONFLICT, {"error": "too_many_children"})
                        return
                    # The id is always server-generated; a client never names a child.
                    ids = {child["child_id"] for child in children}
                    target, action = f"child-{secrets.token_hex(4)}", "add_child"
                    while target in ids:
                        target = f"child-{secrets.token_hex(4)}"
                else:
                    target, action = requested_child, "update_child"
                store.upsert_child_profile(tenant, target, name, age, has_whatsapp, username)
                persist_audit(action, username, f"{path}?child_id={target}", self.client_ip())
                saved = next((c for c in family_children(tenant) if c["child_id"] == target), None)
                if saved is None:
                    self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self.send_json(HTTPStatus.OK, saved)
                return
            if path in ("/watchup/tracking-words", "/watchup/schedule", "/watchup/today", "/watchup/family", "/watchup/pairing"):
                if not self.csrf_ok():
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                token, scope = self.parent_scope(None if path == "/watchup/family" else requested_child)
                if not scope:
                    return
                scoped_tenant, scoped_child, _children = scope
                username = parent_auth.username_for_token(token)
            if path == "/watchup/tracking-words":
                try:
                    words = validate_tracking_words(self.read_json(4096).get("words"))
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, ValueError):
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                store.set_tracking_words(scoped_tenant, scoped_child, words)
                persist_audit("update_tracking_words", username, path, self.client_ip())
                self.send_json(HTTPStatus.OK, {"words": words})
                return
            if path == "/watchup/schedule":
                try:
                    schedule = validate_schedule(self.read_json(8192).get("schedule"))
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, ValueError):
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                store.set_schedule(scoped_tenant, scoped_child, schedule)
                persist_audit("update_schedule", username, path, self.client_ip())
                self.send_json(HTTPStatus.OK, {"schedule": schedule})
                return
            if path == "/watchup/today":
                # Child-level reset: a sibling's day stays intact.
                deleted = store.purge_before(jerusalem_day_start(), scoped_tenant, scoped_child)
                persist_audit("reset_today", username, path, self.client_ip())
                self.send_json(HTTPStatus.OK, {"deleted_events": deleted})
                return
            if path == "/watchup/family":
                persist_audit("delete_family", username, "/watchup/family", self.client_ip())
                deleted = store.delete_family(scoped_tenant)
                names = [name for name in parent_auth.parents if tenant_for(name) == scoped_tenant]
                parent_auth.revoke_usernames(names)
                self.send_json(HTTPStatus.OK, {"deleted_events": deleted})
                return
            if path == "/watchup/pairing":
                if not families:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                status = store.latest_connection_status(scoped_tenant, scoped_child) if hasattr(store, "latest_connection_status") else None
                if connection_is_live(status):
                    # A paired child is never re-paired from the dashboard.
                    self.send_json(HTTPStatus.CONFLICT, {"state": "connected", "svg": None})
                    return
                if not families.has_bridge(scoped_tenant, scoped_child):
                    self.send_json(HTTPStatus.CONFLICT, {"state": "no_bridge", "svg": None})
                    return
                pairing.request((scoped_tenant, scoped_child), time.time())
                persist_audit("request_pairing", username, path, self.client_ip())
                self.send_json(HTTPStatus.ACCEPTED, pairing_view(scoped_tenant, scoped_child))
                return
            if path != "/watchup/events":
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
            binding = bridge_binding(body, self.headers.get("X-WatchUp-Signature", ""))
            if not binding:
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            try:
                event = validate_event(json.loads(body.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            if (event["tenant_id"], event["child_id"]) != binding:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            inserted = store.insert(event, datetime.now(timezone.utc))
            self.send_response(HTTPStatus.ACCEPTED if inserted else HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"accepted": inserted, "duplicate": not inserted}).encode("utf-8"))

        def bridge_pairing(self):
            """A child's bridge reports its pairing state and learns whether a parent asked to pair it."""
            if not families:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 2048:
                    raise ValueError("invalid body length")
            except ValueError:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            body = self.rfile.read(length)
            binding = bridge_binding(body, self.headers.get("X-WatchUp-Signature", ""))
            if not binding:
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            try:
                report = json.loads(body.decode("utf-8"))
                state = report["state"]
                code = report.get("code") or ""
                sent_at = parse_timestamp(report["sent_at"])
                if state not in BRIDGE_STATES or (state == "qr") != bool(code):
                    raise ValueError("invalid state")
                if not isinstance(code, str) or len(code) > 512 or any(character in code for character in "\r\n"):
                    raise ValueError("invalid code")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError):
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            if (report.get("tenant_id"), report.get("child_id")) != binding:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if abs((datetime.now(timezone.utc) - sent_at).total_seconds()) > 120:
                self.send_error(HTTPStatus.UNAUTHORIZED)
                return
            requested = pairing.bridge_report(binding, state, code, time.time())
            self.send_json(HTTPStatus.OK, {"pairing_requested": requested})

        def do_DELETE(self):
            path, requested_child = self.route()
            if path == "/watchup/pairing" and families:
                if not self.csrf_ok():
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                token, scope = self.parent_scope(requested_child)
                if not scope:
                    return
                pairing.cancel((scope[0], scope[1]))
                persist_audit("cancel_pairing", parent_auth.username_for_token(token), path, self.client_ip())
                self.send_json(HTTPStatus.OK, pairing_view(scope[0], scope[1]))
                return
            if path != "/watchup/session" or not parent_auth:
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
        families_file = os.environ.get("WATCHUP_FAMILIES_FILE", "").strip()
        families = FamilyRegistry.from_file(families_file) if families_file else None
        if families:
            # Multi-Family: every bridge secret and binding comes from the families file.
            secret, tenant_id, child_id = "", "", ""
        else:
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
        if (production or families) and (not parents_file or not session_secret_file):
            raise ValueError("production and Multi-Family require parent accounts and a session secret")
        if parents_file and session_secret_file:
            parent_auth = ParentAuth.from_files(
                parents_file, session_secret_file,
                ttl_seconds=session_ttl_seconds, require_totp=require_totp,
            )
        else:
            parent_auth = None
        if families:
            families.check_parents(parent_auth.parents)
            if store_kind == "postgres" and store.missing_tables(("watchup.child_profiles", "watchup.family_onboarding")):
                raise ValueError("Multi-Family requires migration 007_child_profiles.sql")
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
        retention_days = int(os.environ.get("WATCHUP_RETENTION_DAYS", "3"))
        if retention_days < 1 or retention_days > 365:
            raise ValueError("WATCHUP_RETENTION_DAYS must be between 1 and 365")
        if os.environ.get("WATCHUP_RUN_RETENTION_ONCE") == "1":
            cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=retention_days)
            for retention_tenant in (families.tenant_ids() if families else [tenant_id]):
                store.purge_before(cutoff, retention_tenant)
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
            qr_path=os.environ.get("WATCHUP_QR_FILE", "").strip(), families=families,
        )
    ).serve_forever()


if __name__ == "__main__":
    main()
