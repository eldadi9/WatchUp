# WatchUp PostgreSQL bootstrap

Run `001_events.sql` exactly once against an empty database, and only as an authorized PostgreSQL superuser (cluster administrator). An ordinary database owner is not sufficient: this bootstrap creates and changes cluster roles, grants role membership, and assumes the owner role. It creates three non-login group roles: `watchup_owner` owns objects, `watchup_migrator` may assume that owner role for migrations, and `watchup_app` receives only CRUD access to `watchup.events`.

Run `002_parent_auth_retention.sql` exactly once afterwards through the approved migration path. It creates only hashed session state and TOTP replay counters; the parent password hashes and TOTP seeds remain protected files outside PostgreSQL and Git.

Run `003_parent_audit.sql` exactly once after `002`. It creates `watchup.parent_audit` for durable parent login and dashboard view logging with the same tenant RLS model as `watchup.events`.

Run `004_tracking_words.sql` exactly once after `003`. It stores the family's bounded tracking-word list with the same tenant RLS model; words are removed by the authenticated family-deletion path.

The retention job is the same API image with `WATCHUP_RUN_RETENTION_ONCE=1` and `WATCHUP_RETENTION_DAYS=14`; schedule it daily using the existing protected environment and network. It deletes expired `watchup.events` rows only. The authenticated `DELETE /watchup/family` path revokes all parent sessions and deletes all events for the configured tenant. Media, caches, and encrypted backups are not currently produced by this API and must not be introduced without adding their deletion implementation to that path.

The migration fails before schema changes unless the database encoding is UTF8, and it writes the durable database setting `timezone = 'Asia/Jerusalem'`. Run `verify_watchup.sql` in a fresh connection afterwards; its encoding and both timezone booleans must be `true`.

The table and indexes tolerate a rerun, but the named policies intentionally do not. Do not rerun this bootstrap on an existing database: inspect and use a reviewed, dedicated follow-up migration instead of silently replacing security policies.

Create real login principals outside this migration and grant only the required group role. Do not give application logins `watchup_owner`, `watchup_migrator`, `BYPASSRLS`, `CREATEROLE`, or schema `CREATE` privileges. A separately authorized migration login must assume `watchup_migrator` and then `watchup_owner`; application connections must assume `watchup_app`.

Every application query must be inside a transaction. Set the tenant only from server-side authenticated request context, using a bound parameter, and keep it transaction-local:

```sql
BEGIN;
SELECT set_config('watchup.tenant_id', $1, true);
-- Queries and writes as watchup_app.
COMMIT;
```

The policy fails closed when the setting is absent, empty, or does not equal a row's `tenant_id`; it governs both reads and writes. A custom session setting is not an identity provider: anyone with arbitrary SQL access as `watchup_app` can set it. Keep that role's credential server-side and never expose a direct database connection to clients.
