-- WatchUp: ownership and GRANTs to re-apply after pg_restore.
-- Backups use `pg_dump --no-owner --no-privileges`, so a restored schema has no
-- owners and no grants. Run as a superuser (watchup_admin / postgres) against the
-- restored database, after the roles exist (see docs/ops/RESTORE_RUNBOOK.md).
-- Idempotent. RLS policies and FORCE ROW LEVEL SECURITY ARE in the dump.
\set ON_ERROR_STOP on
ALTER SCHEMA watchup OWNER TO watchup_owner;
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'watchup' LOOP
    EXECUTE format('ALTER TABLE watchup.%I OWNER TO watchup_owner', r.tablename);
  END LOOP;
  FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'watchup' LOOP
    EXECUTE format('ALTER SEQUENCE watchup.%I OWNER TO watchup_owner', r.sequencename);
  END LOOP;
END $$;
GRANT USAGE ON SCHEMA watchup TO watchup_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  watchup.events, watchup.parent_sessions, watchup.parent_totp_steps,
  watchup.child_settings, watchup.child_profiles, watchup.family_onboarding
  TO watchup_app;
GRANT SELECT, INSERT ON watchup.parent_audit TO watchup_app;
GRANT SELECT, INSERT, DELETE ON watchup.tracking_words TO watchup_app;
GRANT USAGE, SELECT ON SEQUENCE watchup.parent_audit_id_seq TO watchup_app;
