import importlib.util
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


APP_PATH = Path(__file__).parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("watchup_postgres_app", APP_PATH)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class FakeCursor:
    def __init__(self, rowcount=1, row=("event-1",), rows=None):
        self.commands = []
        self.rowcount = rowcount
        self.row = row
        self.rows = rows or []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.commands.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value


class PostgresEventStoreTests(unittest.TestCase):
    def setUp(self):
        self.cursors = []
        self.connections = []

        def connect_factory(**kwargs):
            self.kwargs = kwargs
            cursor = FakeCursor()
            connection = FakeConnection(cursor)
            self.cursors.append(cursor)
            self.connections.append(connection)
            return connection

        self.store = app.PostgresEventStore(
            {"host": "db", "port": 5432, "dbname": "watchup", "user": "login", "password": "secret"},
            connect_factory=connect_factory,
            jsonb_factory=lambda value: ("jsonb", value),
        )
        self.event = {
            "tenant_id": "tenant-a", "child_id": "child-a", "event_id": "event-1",
            "type": "message.received", "source": "synthetic",
            "source_timestamp": "2026-10-04T00:00:00+00:00",
            "account": {"chat_jid": "synthetic@example.test"}, "payload": {"content": "test"},
        }

    def test_insert_uses_one_transaction_with_role_rls_and_parameterized_jsonb(self):
        self.assertTrue(self.store.insert(self.event, datetime(2026, 10, 4, tzinfo=timezone.utc)))
        self.assertTrue(self.connections[0].entered)
        commands = self.cursors[0].commands
        self.assertEqual(commands[0], ("SET LOCAL ROLE watchup_app", None))
        self.assertEqual(commands[1], ("SELECT set_config('watchup.tenant_id', %s, true)", ("tenant-a",)))
        sql, params = commands[2]
        self.assertIn("INSERT INTO watchup.events", sql)
        self.assertIn("ON CONFLICT (tenant_id, event_id) DO NOTHING", sql)
        self.assertIn("%s", sql)
        self.assertEqual(params[6], ("jsonb", self.event["account"]))
        self.assertEqual(params[7], ("jsonb", self.event["payload"]))

    def test_get_repeats_transaction_scoped_rls_context(self):
        self.assertEqual(self.store.get("tenant-a", "child-a", "event-1"), ("event-1",))
        commands = self.cursors[0].commands
        self.assertEqual(commands[0], ("SET LOCAL ROLE watchup_app", None))
        self.assertEqual(commands[1][1], ("tenant-a",))
        self.assertEqual(commands[2][1], ("tenant-a", "child-a", "event-1"))

    def test_list_recent_uses_rls_and_fixed_child_scope(self):
        self.assertEqual(self.store.list_recent("tenant-a", "child-a"), [])
        commands = self.cursors[0].commands
        self.assertEqual(commands[0], ("SET LOCAL ROLE watchup_app", None))
        self.assertEqual(commands[1][1], ("tenant-a",))
        self.assertIn("ORDER BY received_at DESC", commands[2][0])
        self.assertEqual(commands[2][1], ("tenant-a", "child-a", 50))

    def test_production_main_refuses_sqlite_fallback(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            secret = Path(directory) / "webhook-secret"
            secret.write_text("synthetic-test-secret", encoding="utf-8")
            environment = {
                "APP_ENV": "production",
                "WATCHUP_WEBHOOK_SECRET_FILE": str(secret),
                "WATCHUP_TENANT_ID": "tenant-a",
                "WATCHUP_CHILD_ID": "child-a",
                "WATCHUP_EVENT_STORE": "sqlite",
            }
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(SystemExit, "production requires WATCHUP_EVENT_STORE=postgres"):
                    app.main()

    def test_production_requires_webhook_secret_file(self):
        environment = {
            "APP_ENV": "production",
            "WATCHUP_WEBHOOK_SECRET": "must-not-be-used-in-production",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(SystemExit, "WATCHUP_WEBHOOK_SECRET_FILE must be set"):
                app.main()

    def test_production_requires_verify_full(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            secret = Path(directory) / "webhook-secret"
            secret.write_text("synthetic-test-secret", encoding="utf-8")
            environment = {
                "APP_ENV": "production",
                "WATCHUP_WEBHOOK_SECRET_FILE": str(secret),
                "WATCHUP_TENANT_ID": "tenant-a",
                "WATCHUP_CHILD_ID": "child-a",
                "WATCHUP_EVENT_STORE": "postgres",
                "WATCHUP_DB_SSLMODE": "require",
            }
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(SystemExit, "production requires WATCHUP_DB_SSLMODE=verify-full"):
                    app.main()

    def test_postgres_config_passes_ca_file_for_verify_full(self):
        with TemporaryDirectory() as temporary_directory:
            password_file = Path(temporary_directory) / "password"
            password_file.write_text("synthetic-password\n", encoding="utf-8")
            environment = {
                "WATCHUP_DB_HOST": "watchup-postgres",
                "WATCHUP_DB_PORT": "5432",
                "WATCHUP_DB_NAME": "watchup",
                "WATCHUP_DB_USER": "watchup_login",
                "WATCHUP_DB_PASSWORD_FILE": str(password_file),
                "WATCHUP_DB_SSLMODE": "verify-full",
                "WATCHUP_DB_SSLROOTCERT": "/run/secrets/watchup_db_ca.crt",
            }
            with patch.dict(os.environ, environment, clear=True):
                store = app.PostgresEventStore.from_environment()
        self.assertEqual(store.connection_kwargs["sslrootcert"], "/run/secrets/watchup_db_ca.crt")

    def test_verify_full_requires_a_ca_file(self):
        with TemporaryDirectory() as temporary_directory:
            password_file = Path(temporary_directory) / "password"
            password_file.write_text("synthetic-password\n", encoding="utf-8")
            environment = {
                "WATCHUP_DB_HOST": "watchup-postgres",
                "WATCHUP_DB_PORT": "5432",
                "WATCHUP_DB_NAME": "watchup",
                "WATCHUP_DB_USER": "watchup_login",
                "WATCHUP_DB_PASSWORD_FILE": str(password_file),
                "WATCHUP_DB_SSLMODE": "verify-full",
            }
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(ValueError, "WATCHUP_DB_SSLROOTCERT"):
                    app.PostgresEventStore.from_environment()

    def test_postgres_tls_defaults_to_require(self):
        with TemporaryDirectory() as temporary_directory:
            password_file = Path(temporary_directory) / "password"
            password_file.write_text("synthetic-password\n", encoding="utf-8")
            environment = {
                "WATCHUP_DB_HOST": "watchup-postgres",
                "WATCHUP_DB_PORT": "5432",
                "WATCHUP_DB_NAME": "watchup",
                "WATCHUP_DB_USER": "watchup_login",
                "WATCHUP_DB_PASSWORD_FILE": str(password_file),
            }
            with patch.dict(os.environ, environment, clear=True):
                store = app.PostgresEventStore.from_environment()
        self.assertEqual(store.connection_kwargs["sslmode"], "require")


if __name__ == "__main__":
    unittest.main()
