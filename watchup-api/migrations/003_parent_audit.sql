-- Run once after 002_parent_auth_retention.sql as the authorized migration role.
BEGIN;
SET LOCAL ROLE watchup_owner;

CREATE TABLE IF NOT EXISTS watchup.parent_audit (
    id bigserial PRIMARY KEY,
    tenant_id text NOT NULL,
    username text,
    action text NOT NULL,
    path text NOT NULL,
    client_ip inet,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (tenant_id <> ''),
    CHECK (action <> ''),
    CHECK (path <> '')
);

CREATE INDEX IF NOT EXISTS parent_audit_tenant_created_idx
    ON watchup.parent_audit (tenant_id, created_at DESC);

ALTER TABLE watchup.parent_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchup.parent_audit FORCE ROW LEVEL SECURITY;

CREATE POLICY parent_audit_app_access ON watchup.parent_audit
    FOR ALL TO watchup_app
    USING (true)
    WITH CHECK (true);

CREATE POLICY parent_audit_tenant_isolation ON watchup.parent_audit
    AS RESTRICTIVE
    FOR ALL TO watchup_app
    USING (tenant_id = current_setting('watchup.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('watchup.tenant_id', true));

REVOKE ALL ON TABLE watchup.parent_audit FROM PUBLIC;
GRANT SELECT, INSERT ON TABLE watchup.parent_audit TO watchup_app;
GRANT USAGE, SELECT ON SEQUENCE watchup.parent_audit_id_seq TO watchup_app;

RESET ROLE;
COMMIT;
