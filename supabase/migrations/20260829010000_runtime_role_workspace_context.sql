-- C2-03: establish the least-privilege runtime role and workspace context contract.
do $$
declare
    existing_role pg_roles%rowtype;
    schema_name name;
begin
    select * into existing_role
    from pg_roles
    where rolname = 'knowledge_platform_runtime';

    if not found then
        create role knowledge_platform_runtime
            login
            nosuperuser
            nobypassrls
            nocreatedb
            nocreaterole
            noreplication;
    elsif not (
        existing_role.rolcanlogin
        and not existing_role.rolsuper
        and not existing_role.rolbypassrls
        and not existing_role.rolcreatedb
        and not existing_role.rolcreaterole
        and not existing_role.rolreplication
    ) then
        raise exception 'knowledge_platform_runtime has unsafe attributes';
    end if;

    if exists (
        select 1
        from pg_auth_members membership
        join pg_roles member_role on member_role.oid = membership.member
        where member_role.rolname = 'knowledge_platform_runtime'
    ) then
        raise exception 'knowledge_platform_runtime has unexpected role membership';
    end if;

    if exists (
        select 1
        from pg_namespace namespace_record
        join pg_roles owner_role on owner_role.oid = namespace_record.nspowner
        where owner_role.rolname = 'knowledge_platform_runtime'
          and namespace_record.nspname in ('platform', 'retrieval', 'evaluation')
    ) then
        raise exception 'knowledge_platform_runtime owns a private schema';
    end if;
end
$$;

revoke create on schema platform from knowledge_platform_runtime;
revoke create on schema retrieval from knowledge_platform_runtime;
revoke create on schema evaluation from knowledge_platform_runtime;

grant usage on schema platform to knowledge_platform_runtime;
grant usage on schema retrieval to knowledge_platform_runtime;
grant usage on schema evaluation to knowledge_platform_runtime;

do $$
declare
    schema_name name;
begin
    foreach schema_name in array array['platform'::name, 'retrieval'::name, 'evaluation'::name]
    loop
        if has_schema_privilege('knowledge_platform_runtime', schema_name, 'CREATE') then
            raise exception 'knowledge_platform_runtime retains CREATE on schema %', schema_name;
        end if;
    end loop;
end
$$;

-- Application code sets this only for the current transaction:
-- set_config('app.workspace_id', '<trusted-workspace-uuid>', true)
-- Missing or malformed values must fail closed via the canonical RLS shape:
-- workspace_id = current_setting('app.workspace_id', true)::uuid
