-- Run once after 004_tracking_words.sql as the authorized migration role.
BEGIN;
SET LOCAL ROLE watchup_owner;

CREATE TABLE IF NOT EXISTS watchup.child_settings (
    tenant_id text NOT NULL,
    child_id text NOT NULL,
    schedule jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (tenant_id, child_id),
    CHECK (tenant_id <> ''),
    CHECK (child_id <> '')
);

ALTER TABLE watchup.child_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchup.child_settings FORCE ROW LEVEL SECURITY;

CREATE POLICY child_settings_app_access ON watchup.child_settings
    FOR ALL TO watchup_app
    USING (true)
    WITH CHECK (true);

CREATE POLICY child_settings_tenant_isolation ON watchup.child_settings
    AS RESTRICTIVE
    FOR ALL TO watchup_app
    USING (tenant_id = current_setting('watchup.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('watchup.tenant_id', true));

REVOKE ALL ON TABLE watchup.child_settings FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE watchup.child_settings TO watchup_app;

RESET ROLE;
COMMIT;
