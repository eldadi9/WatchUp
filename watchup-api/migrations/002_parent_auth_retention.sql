-- Run once after 001_events.sql as the authorized migration role.
BEGIN;
SET LOCAL ROLE watchup_owner;

CREATE TABLE watchup.parent_sessions (
    token_hash text PRIMARY KEY,
    username text NOT NULL,
    expires_at timestamptz NOT NULL,
    csrf_hash text NOT NULL
);
CREATE INDEX parent_sessions_expires_at_idx ON watchup.parent_sessions (expires_at);

CREATE TABLE watchup.parent_totp_steps (
    username text PRIMARY KEY,
    last_step bigint NOT NULL
);

REVOKE ALL ON watchup.parent_sessions, watchup.parent_totp_steps FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON watchup.parent_sessions, watchup.parent_totp_steps TO watchup_app;
COMMIT;
