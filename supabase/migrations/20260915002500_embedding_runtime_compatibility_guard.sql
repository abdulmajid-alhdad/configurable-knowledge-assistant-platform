-- Expose only the global existence of persisted embedding vectors to the
-- SYSTEM runtime-configuration guard. No document, chunk, or vector data is
-- returned across this boundary.

create function platform.has_indexed_embeddings()
returns boolean
language plpgsql
stable
security definer
set search_path = ''
set row_security = off
as $$
begin
  if not platform.user_has_system_permission('providers.manage') then
    raise exception using
      errcode = '42501',
      message = 'PROVIDER_CONFIGURATION_FORBIDDEN';
  end if;

  return exists (
    select 1
    from retrieval.document_chunks
  );
end $$;

revoke all on function platform.has_indexed_embeddings()
  from public, anon, authenticated;

grant execute on function platform.has_indexed_embeddings()
  to knowledge_platform_runtime;
