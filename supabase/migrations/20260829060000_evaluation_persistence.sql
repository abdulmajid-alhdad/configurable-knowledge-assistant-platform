create table evaluation.evaluation_runs (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces(id),
    suite_key text not null,
    suite_version text not null,
    suite_hash text not null,
    lifecycle text not null check (lifecycle in ('created', 'running', 'completed', 'failed')),
    configuration_snapshot jsonb not null default '{}'::jsonb,
    summary_metrics jsonb not null default '{}'::jsonb
);
create table evaluation.evaluation_results (
    run_id uuid not null references evaluation.evaluation_runs(id),
    case_key text not null,
    outcome_type text not null,
    passed boolean not null,
    diagnostic jsonb not null default '{}'::jsonb,
    primary key (run_id, case_key)
);
alter table evaluation.evaluation_runs enable row level security;
alter table evaluation.evaluation_runs force row level security;
alter table evaluation.evaluation_results enable row level security;
alter table evaluation.evaluation_results force row level security;
create policy evaluation_runs_workspace on evaluation.evaluation_runs for all to knowledge_platform_runtime using (workspace_id = current_setting('app.workspace_id', true)::uuid) with check (workspace_id = current_setting('app.workspace_id', true)::uuid);
create policy evaluation_results_workspace on evaluation.evaluation_results for all to knowledge_platform_runtime using (run_id in (select id from evaluation.evaluation_runs where workspace_id = current_setting('app.workspace_id', true)::uuid)) with check (run_id in (select id from evaluation.evaluation_runs where workspace_id = current_setting('app.workspace_id', true)::uuid));
grant select, insert, update on table evaluation.evaluation_runs to knowledge_platform_runtime;
grant select, insert on table evaluation.evaluation_results to knowledge_platform_runtime;
