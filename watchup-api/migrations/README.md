# WatchUp PostgreSQL bootstrap

Run `001_events.sql` exactly once against an empty database, and only as an authorized PostgreSQL superuser (cluster administrator). An ordinary database owner is not sufficient: this bootstrap creates and changes cluster roles, grants role membership, and assumes the owner role. It creates three non-login group roles: `watchup_owner` owns objects, `watchup_migrator` may assume that owner role for migrations, and `watchup_app` receives only CRUD access to `watchup.events`.

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
