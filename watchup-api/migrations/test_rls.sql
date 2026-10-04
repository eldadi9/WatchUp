\set ON_ERROR_STOP on

BEGIN;

CREATE ROLE watchup_synthetic_login LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT watchup_app TO watchup_synthetic_login;

CREATE FUNCTION pg_temp.assert_true(value boolean, message text)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    IF value IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'assertion failed: %', message;
    END IF;
END
$$;

CREATE FUNCTION pg_temp.cross_tenant_insert_is_denied()
RETURNS boolean
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO watchup.events (
        tenant_id, child_id, event_id, event_type, source,
        source_timestamp, account, payload, latency_ms
    ) VALUES (
        'tenant-beta', 'child-beta', 'forbidden', 'message', 'synthetic',
        now(), '{}'::jsonb, '{}'::jsonb, 0
    );
    RETURN false;
EXCEPTION
    WHEN insufficient_privilege OR check_violation THEN
        RETURN true;
END
$$;

CREATE FUNCTION pg_temp.schema_create_is_denied()
RETURNS boolean
LANGUAGE plpgsql
AS $$
BEGIN
    CREATE SCHEMA watchup_forbidden;
    RETURN false;
EXCEPTION
    WHEN insufficient_privilege THEN
        RETURN true;
END
$$;

CREATE FUNCTION pg_temp.owner_role_is_denied()
RETURNS boolean
LANGUAGE plpgsql
AS $$
BEGIN
    SET ROLE watchup_owner;
    RETURN false;
EXCEPTION
    WHEN insufficient_privilege OR invalid_authorization_specification THEN
        RETURN true;
END
$$;

CREATE FUNCTION pg_temp.cross_tenant_update_count()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    affected integer;
BEGIN
    UPDATE watchup.events SET event_type = 'blocked' WHERE tenant_id = 'tenant-beta';
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END
$$;

CREATE FUNCTION pg_temp.cross_tenant_delete_count()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    affected integer;
BEGIN
    DELETE FROM watchup.events WHERE tenant_id = 'tenant-beta';
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END
$$;

INSERT INTO watchup.events (
    tenant_id, child_id, event_id, event_type, source,
    source_timestamp, account, payload, latency_ms
) VALUES
    ('tenant-alpha', 'child-alpha', 'event-alpha', 'message', 'synthetic', now(), '{}'::jsonb, '{}'::jsonb, 0),
    ('tenant-beta', 'child-beta', 'event-beta', 'message', 'synthetic', now(), '{}'::jsonb, '{}'::jsonb, 0);

SET SESSION AUTHORIZATION watchup_synthetic_login;
SET ROLE watchup_app;

SELECT pg_temp.assert_true(
    (SELECT count(*) = 0 FROM watchup.events),
    'absent tenant context must fail closed'
);

SELECT set_config('watchup.tenant_id', 'tenant-alpha', true);

SELECT pg_temp.assert_true(
    (SELECT count(*) = 1 AND min(tenant_id) = 'tenant-alpha' FROM watchup.events),
    'tenant-alpha must see only its own row'
);

SELECT pg_temp.assert_true(
    pg_temp.cross_tenant_update_count() = 0,
    'cross-tenant update row count must be zero'
);

SELECT pg_temp.assert_true(
    pg_temp.cross_tenant_delete_count() = 0,
    'cross-tenant delete row count must be zero'
);

SELECT pg_temp.assert_true(
    pg_temp.cross_tenant_insert_is_denied(),
    'cross-tenant insert must be rejected'
);

SELECT pg_temp.assert_true(
    pg_temp.schema_create_is_denied(),
    'application role must not create schemas'
);

SELECT pg_temp.assert_true(
    pg_temp.owner_role_is_denied(),
    'application login must not assume the owner role'
);

SELECT set_config('watchup.tenant_id', '', true);
SELECT pg_temp.assert_true(
    (SELECT count(*) = 0 FROM watchup.events),
    'empty tenant context must fail closed'
);

RESET ROLE;
RESET SESSION AUTHORIZATION;

SELECT pg_temp.assert_true(
    (SELECT count(*) = 2 FROM watchup.events),
    'administrator must confirm both synthetic rows remain'
);

SELECT pg_temp.assert_true(
    (SELECT event_type = 'message' FROM watchup.events WHERE tenant_id = 'tenant-beta'),
    'administrator must confirm tenant-beta row is unchanged'
);

ROLLBACK;
