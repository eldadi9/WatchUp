-- Read-only fingerprint of ownership, ACLs and RLS. Run on the live DB and on a restore; the outputs must be identical.
select 'grant|'||grantee||'|'||table_name||'|'||string_agg(privilege_type,',' order by privilege_type) from information_schema.role_table_grants where table_schema='watchup' and grantee like 'watchup_%' group by grantee,table_name
union all select 'seq|'||c.relname||'|'||coalesce(c.relacl::text,'-') from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='watchup' and c.relkind='S'
union all select 'schema|'||pg_get_userbyid(nspowner)||'|'||coalesce(nspacl::text,'-') from pg_namespace where nspname='watchup'
union all select 'table|'||c.relname||'|'||pg_get_userbyid(c.relowner)||'|rls='||c.relrowsecurity||'|force='||c.relforcerowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='watchup' and c.relkind='r'
union all select 'policies|'||count(*) from pg_policies where schemaname='watchup'
union all select 'pkey|'||pg_get_constraintdef(oid) from pg_constraint where conrelid='watchup.events'::regclass and contype='p'
order by 1;
