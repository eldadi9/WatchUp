-- Read-only post-deployment checks. Use a fresh connection after 001_events.sql.
SHOW server_encoding;
SHOW timezone;

SELECT
    current_setting('server_encoding') = 'UTF8' AS encoding_is_utf8,
    current_setting('timezone') = 'Asia/Jerusalem' AS session_timezone_is_jerusalem,
    EXISTS (
        SELECT 1
        FROM pg_db_role_setting AS s
        JOIN pg_database AS d ON d.oid = s.setdatabase
        CROSS JOIN LATERAL unnest(s.setconfig) AS setting
        WHERE d.datname = current_database()
          AND s.setrole = 0
          AND split_part(setting, '=', 1) ILIKE 'timezone'
          AND split_part(setting, '=', 2) = 'Asia/Jerusalem'
    ) AS database_timezone_is_jerusalem;

SELECT n.nspname, n.nspowner::regrole AS owner
FROM pg_namespace AS n
WHERE n.nspname = 'watchup';

SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'watchup' AND c.relname = 'events';

SELECT
    p.polname,
    p.polpermissive,
    p.polcmd,
    r.rolname,
    pg_get_expr(p.polqual, p.polrelid) AS using_expression,
    pg_get_expr(p.polwithcheck, p.polrelid) AS with_check_expression
FROM pg_policy AS p
JOIN pg_class AS c ON c.oid = p.polrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_roles AS r ON r.oid = ANY (p.polroles)
WHERE n.nspname = 'watchup' AND c.relname = 'events';

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
FROM pg_roles
WHERE rolname IN ('watchup_owner', 'watchup_migrator', 'watchup_app')
ORDER BY rolname;

SELECT
    EXISTS (
        SELECT 1
        FROM pg_auth_members AS m
        JOIN pg_roles AS granted ON granted.oid = m.roleid
        JOIN pg_roles AS member ON member.oid = m.member
        WHERE granted.rolname = 'watchup_owner' AND member.rolname = 'watchup_migrator'
    ) AS migrator_can_assume_owner,
    NOT EXISTS (
        SELECT 1
        FROM pg_auth_members AS m
        JOIN pg_roles AS member ON member.oid = m.member
        WHERE member.rolname = 'watchup_app'
    ) AS app_has_no_role_memberships;

SELECT
    NOT EXISTS (
        SELECT 1
        FROM pg_database AS d
        CROSS JOIN LATERAL aclexplode(COALESCE(d.datacl, acldefault('d', d.datdba))) AS acl
        WHERE d.datname = current_database() AND acl.grantee = 0
    ) AS public_has_no_database_privileges,
    NOT EXISTS (
        SELECT 1
        FROM pg_namespace AS n
        CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl, acldefault('n', n.nspowner))) AS acl
        WHERE n.nspname IN ('public', 'watchup') AND acl.grantee = 0
    ) AS public_has_no_schema_privileges,
    has_schema_privilege('watchup_app', 'watchup', 'USAGE') AS app_has_schema_usage,
    NOT has_schema_privilege('watchup_app', 'watchup', 'CREATE') AS app_cannot_create_in_schema,
    has_table_privilege('watchup_app', 'watchup.events', 'SELECT,INSERT,UPDATE,DELETE') AS app_has_events_crud;
