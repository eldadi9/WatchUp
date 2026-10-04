-- PostgreSQL 13+. Run this one-time bootstrap as an authorized PostgreSQL superuser (cluster administrator).
-- An ordinary database owner is insufficient:
-- CREATE/ALTER ROLE and SET ROLE below require cluster-level authority.
-- It deliberately creates no login roles and stores no credentials.
BEGIN;

DO $$
BEGIN
    IF current_setting('server_encoding') <> 'UTF8' THEN
        RAISE EXCEPTION 'WatchUp requires a UTF8 database; found %', current_setting('server_encoding');
    END IF;
    EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'Asia/Jerusalem');

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'watchup_owner') THEN
        CREATE ROLE watchup_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'watchup_migrator') THEN
        CREATE ROLE watchup_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'watchup_app') THEN
        CREATE ROLE watchup_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END
$$;

ALTER ROLE watchup_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE watchup_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE watchup_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT watchup_owner TO watchup_migrator;

-- New deployments start with no implicit database or public-schema access.
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO watchup_owner, watchup_migrator, watchup_app', current_database());
END
$$;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS watchup AUTHORIZATION watchup_owner;
ALTER SCHEMA watchup OWNER TO watchup_owner;
REVOKE ALL ON SCHEMA watchup FROM PUBLIC;
GRANT USAGE ON SCHEMA watchup TO watchup_app;

SET ROLE watchup_owner;

CREATE TABLE IF NOT EXISTS watchup.events (
    tenant_id text NOT NULL,
    child_id text NOT NULL,
    event_id text NOT NULL,
    event_type text NOT NULL,
    source text NOT NULL,
    source_timestamp timestamptz NOT NULL,
    account jsonb NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    latency_ms bigint NOT NULL CHECK (latency_ms >= 0),
    PRIMARY KEY (tenant_id, event_id),
    CHECK (tenant_id <> ''),
    CHECK (child_id <> ''),
    CHECK (event_id <> '')
);

CREATE INDEX IF NOT EXISTS events_tenant_child_received_idx
    ON watchup.events (tenant_id, child_id, received_at DESC);
CREATE INDEX IF NOT EXISTS events_tenant_source_timestamp_idx
    ON watchup.events (tenant_id, source_timestamp DESC);

ALTER TABLE watchup.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchup.events FORCE ROW LEVEL SECURITY;

-- A restrictive policy needs this permissive base policy; the restrictive
-- predicate below remains mandatory for every app query and write.
CREATE POLICY events_app_access ON watchup.events
    FOR ALL TO watchup_app
    USING (true)
    WITH CHECK (true);

CREATE POLICY events_tenant_isolation ON watchup.events
    AS RESTRICTIVE
    FOR ALL TO watchup_app
    USING (tenant_id = current_setting('watchup.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('watchup.tenant_id', true));

REVOKE ALL ON ALL TABLES IN SCHEMA watchup FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA watchup FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA watchup FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE watchup_owner IN SCHEMA watchup REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE watchup_owner IN SCHEMA watchup REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE watchup_owner IN SCHEMA watchup REVOKE ALL ON FUNCTIONS FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE watchup.events TO watchup_app;

RESET ROLE;

COMMIT;
