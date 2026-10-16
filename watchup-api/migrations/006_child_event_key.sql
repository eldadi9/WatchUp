-- Run once after 005_child_settings.sql as the authorized migration role.
-- Two children in one WhatsApp group receive the same message id and the same
-- group-snapshot id, so the event key must include the child. Existing rows
-- already satisfy the wider key; no data changes.
BEGIN;
SET LOCAL ROLE watchup_owner;
SET LOCAL lock_timeout = '5s';

ALTER TABLE watchup.events DROP CONSTRAINT events_pkey;
ALTER TABLE watchup.events ADD CONSTRAINT events_pkey PRIMARY KEY (tenant_id, child_id, event_id);

RESET ROLE;
COMMIT;
