-- Run once after 003_parent_audit.sql as the authorized migration role.
BEGIN;
SET LOCAL ROLE watchup_owner;

CREATE TABLE IF NOT EXISTS watchup.tracking_words (
    tenant_id text NOT NULL,
    child_id text NOT NULL,
    position smallint NOT NULL CHECK (position >= 0 AND position < 30),
    word text NOT NULL CHECK (char_length(word) BETWEEN 1 AND 40),
    normalized_word text NOT NULL,
    PRIMARY KEY (tenant_id, child_id, normalized_word),
    CHECK (tenant_id <> ''),
    CHECK (child_id <> '')
);

ALTER TABLE watchup.tracking_words ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchup.tracking_words FORCE ROW LEVEL SECURITY;

CREATE POLICY tracking_words_app_access ON watchup.tracking_words
    FOR ALL TO watchup_app
    USING (true)
    WITH CHECK (true);

CREATE POLICY tracking_words_tenant_isolation ON watchup.tracking_words
    AS RESTRICTIVE
    FOR ALL TO watchup_app
    USING (tenant_id = current_setting('watchup.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('watchup.tenant_id', true));

REVOKE ALL ON TABLE watchup.tracking_words FROM PUBLIC;
GRANT SELECT, INSERT, DELETE ON TABLE watchup.tracking_words TO watchup_app;

RESET ROLE;
COMMIT;
