-- Run once after 006_child_event_key.sql as the authorized migration role.
BEGIN;
SET LOCAL ROLE watchup_owner;

CREATE TABLE IF NOT EXISTS watchup.child_profiles (
    tenant_id text NOT NULL,
    child_id text NOT NULL,
    display_name text NOT NULL,
    age smallint NULL CHECK (age BETWEEN 1 AND 18),
    has_whatsapp boolean NOT NULL DEFAULT false,
    created_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, child_id),
    CHECK (tenant_id <> ''),
    CHECK (child_id <> ''),
    CHECK (display_name <> '')
);

ALTER TABLE watchup.child_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchup.child_profiles FORCE ROW LEVEL SECURITY;

CREATE POLICY child_profiles_app_access ON watchup.child_profiles
    FOR ALL TO watchup_app
    USING (true)
    WITH CHECK (true);

CREATE POLICY child_profiles_tenant_isolation ON watchup.child_profiles
    AS RESTRICTIVE
    FOR ALL TO watchup_app
    USING (tenant_id = current_setting('watchup.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('watchup.tenant_id', true));

REVOKE ALL ON TABLE watchup.child_profiles FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE watchup.child_profiles TO watchup_app;

CREATE TABLE IF NOT EXISTS watchup.family_onboarding (
    tenant_id text PRIMARY KEY,
    completed_at timestamptz NOT NULL,
    completed_by text NOT NULL,
    CHECK (tenant_id <> '')
);

ALTER TABLE watchup.family_onboarding ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchup.family_onboarding FORCE ROW LEVEL SECURITY;

CREATE POLICY family_onboarding_app_access ON watchup.family_onboarding
    FOR ALL TO watchup_app
    USING (true)
    WITH CHECK (true);

CREATE POLICY family_onboarding_tenant_isolation ON watchup.family_onboarding
    AS RESTRICTIVE
    FOR ALL TO watchup_app
    USING (tenant_id = current_setting('watchup.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('watchup.tenant_id', true));

REVOKE ALL ON TABLE watchup.family_onboarding FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE watchup.family_onboarding TO watchup_app;

RESET ROLE;
COMMIT;
