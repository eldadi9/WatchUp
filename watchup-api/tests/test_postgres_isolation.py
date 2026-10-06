import re
import unittest
from pathlib import Path


MIGRATION = Path(__file__).parents[1] / "migrations" / "001_events.sql"
TRACKING_WORDS_MIGRATION = Path(__file__).parents[1] / "migrations" / "004_tracking_words.sql"
VERIFY = Path(__file__).parents[1] / "migrations" / "verify_watchup.sql"
README = Path(__file__).parents[1] / "migrations" / "README.md"


class PostgresIsolationMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.tracking_words_sql = TRACKING_WORDS_MIGRATION.read_text(encoding="utf-8")
        cls.verify_sql = VERIFY.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def test_bootstrap_requires_cluster_superuser_not_database_owner(self):
        required = "authorized PostgreSQL superuser (cluster administrator)"
        self.assertIn(required, self.sql)
        self.assertIn(required, self.readme)
        self.assertNotIn("database owner or superuser", self.sql)
        self.assertNotIn("as its database owner or a superuser", self.readme)
        self.assertIn("SET ROLE watchup_owner;", self.sql)

    def test_encoding_fails_fast_and_timezone_is_durable(self):
        self.assertIn("IF current_setting('server_encoding') <> 'UTF8' THEN", self.sql)
        self.assertIn("RAISE EXCEPTION 'WatchUp requires a UTF8 database; found %'", self.sql)
        self.assertIn("ALTER DATABASE %I SET timezone TO %L", self.sql)
        self.assertIn("database_timezone_is_jerusalem", self.verify_sql)
        self.assertIn("pg_db_role_setting", self.verify_sql)

    def test_roles_are_distinct_non_login_and_cannot_bypass_rls(self):
        for role in ("watchup_owner", "watchup_migrator", "watchup_app"):
            self.assertRegex(
                self.sql,
                rf"ALTER ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;",
            )
        self.assertIn("GRANT watchup_owner TO watchup_migrator;", self.sql)

    def test_events_are_owned_by_the_dedicated_schema_with_required_indexes(self):
        self.assertIn("CREATE SCHEMA IF NOT EXISTS watchup AUTHORIZATION watchup_owner;", self.sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS watchup.events", self.sql)
        self.assertIn("ON watchup.events (tenant_id, child_id, received_at DESC)", self.sql)
        self.assertIn("ON watchup.events (tenant_id, source_timestamp DESC)", self.sql)

    def test_public_and_app_object_creation_privileges_are_removed(self):
        for clause in (
            "REVOKE ALL ON DATABASE %I FROM PUBLIC",
            "REVOKE ALL ON SCHEMA public FROM PUBLIC;",
            "REVOKE ALL ON SCHEMA watchup FROM PUBLIC;",
            "GRANT USAGE ON SCHEMA watchup TO watchup_app;",
            "REVOKE ALL ON ALL TABLES IN SCHEMA watchup FROM PUBLIC;",
        ):
            self.assertIn(clause, self.sql)
        self.assertNotIn("GRANT CREATE ON SCHEMA watchup TO watchup_app", self.sql)

    def test_rls_is_forced_and_tenant_policy_fails_closed(self):
        self.assertIn("ALTER TABLE watchup.events ENABLE ROW LEVEL SECURITY;", self.sql)
        self.assertIn("ALTER TABLE watchup.events FORCE ROW LEVEL SECURITY;", self.sql)
        restrictive = re.search(
            r"CREATE POLICY events_tenant_isolation.*?AS RESTRICTIVE.*?FOR ALL TO watchup_app"
            r".*?USING \(tenant_id = current_setting\('watchup\.tenant_id', true\)\)"
            r".*?WITH CHECK \(tenant_id = current_setting\('watchup\.tenant_id', true\)\);",
            self.sql,
            re.DOTALL,
        )
        self.assertIsNotNone(restrictive)

    def test_policy_predicate_has_no_cross_tenant_escape(self):
        policy = re.search(
            r"CREATE POLICY events_tenant_isolation ON watchup\.events(?P<body>.*?);",
            self.sql,
            re.DOTALL,
        ).group("body")
        self.assertNotRegex(policy, r"\bOR\b|USING \(true\)|WITH CHECK \(true\)")
        self.assertEqual(policy.count("current_setting('watchup.tenant_id', true)"), 2)

    def test_verification_covers_membership_acl_and_rls_policy_details(self):
        for clause in (
            "migrator_can_assume_owner",
            "app_has_no_role_memberships",
            "public_has_no_database_privileges",
            "public_has_no_schema_privileges",
            "app_cannot_create_in_schema",
            "app_has_events_crud",
            "relforcerowsecurity",
            "pg_get_expr(p.polqual, p.polrelid)",
            "pg_get_expr(p.polwithcheck, p.polrelid)",
        ):
            self.assertIn(clause, self.verify_sql)

    def test_tracking_words_are_bounded_and_tenant_isolated(self):
        sql = self.tracking_words_sql
        self.assertIn("CHECK (position >= 0 AND position < 30)", sql)
        self.assertIn("CHECK (char_length(word) BETWEEN 1 AND 40)", sql)
        self.assertIn("ALTER TABLE watchup.tracking_words FORCE ROW LEVEL SECURITY;", sql)
        self.assertEqual(sql.count("current_setting('watchup.tenant_id', true)"), 2)
        self.assertIn("REVOKE ALL ON TABLE watchup.tracking_words FROM PUBLIC;", sql)


if __name__ == "__main__":
    unittest.main()
