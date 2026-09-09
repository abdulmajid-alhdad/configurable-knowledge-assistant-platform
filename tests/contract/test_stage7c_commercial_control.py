import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "supabase/migrations/20260906010000_stage7c_commercial_administration.sql"
STAGE7A_MIGRATION = ROOT / "supabase/migrations/20260904184807_stage7a_identity_access_control.sql"
STAGE7B_MIGRATION = ROOT / "supabase/migrations/20260904225858_stage7b_administrative_control.sql"
SERVICE = ROOT / "src/knowledge_platform/infrastructure/persistence/commercial.py"
CREDENTIALS_MIGRATION = (
    ROOT / "supabase/migrations/20260910004757_system_credentials_control_plane.sql"
)
ACCESS = ROOT / "src/knowledge_platform/infrastructure/persistence/access_control.py"
ACCESS_API = ROOT / "src/knowledge_platform/delivery/access_control_api.py"
BOOTSTRAP = ROOT / "src/knowledge_platform/bootstrap/application.py"
API = ROOT / "src/knowledge_platform/delivery/commercial_api.py"
SECURITY = ROOT / "src/knowledge_platform/delivery/security.py"
AUTH = ROOT / "src/knowledge_platform/infrastructure/auth/api_keys.py"
UI = ROOT / "frontend/system/controls-pages.js"
SYSTEM_ROUTES = ROOT / "frontend/system/routes.js"
DOMAIN = ROOT / "src/knowledge_platform/modules/access_control/domain.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


STAGE7C_PERMISSIONS = {
    "plans.read", "subscriptions.read", "subscriptions.manage",
    "providers.read", "providers.manage", "credentials.read",
    "credentials.manage", "api_keys.read", "api_keys.manage",
    "security.read", "security.manage", "workspace_settings.manage",
}
PERMISSION_KEY_PATTERN = re.compile(
    r"^[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*$"
)


def permission_insert_codes(path: Path) -> set[str]:
    statement = read(path).split(
        "insert into platform.permissions (key, description) values", 1
    )[1].split(";", 1)[0]
    return set(re.findall(r"\(\s*'([^']+)'\s*,", statement))


def test_permission_catalogue_has_only_real_stage7c_capabilities() -> None:
    domain = read(DOMAIN)
    assert all(f'= "{value}"' in domain for value in STAGE7C_PERMISSIONS)
    assert "billing.read" not in domain
    enum_body = domain.split("class Permission(StrEnum):", 1)[1].split(
        "@dataclass", 1
    )[0]
    assert len(re.findall(r'^    [A-Z_]+ = "[a-z_.]+"$', enum_body, re.MULTILINE)) == 58
    assert "SYSTEM_ADMIN_PERMISSIONS" in domain


def test_permission_key_constraint_accepts_catalogue_and_rejects_malformed_keys() -> None:
    sql = read(MIGRATION)
    drop_constraint = "drop constraint permissions_key_format"
    add_constraint = "add constraint permissions_key_format"
    permission_insert = "insert into platform.permissions (key, description) values"
    expected_check = (
        "check (key ~ '^[a-z]+(_[a-z]+)*\\.[a-z]+(_[a-z]+)*$')"
    )

    assert drop_constraint in sql
    assert add_constraint in sql
    assert expected_check in sql
    assert sql.index(drop_constraint) < sql.index(add_constraint) < sql.index(
        permission_insert
    )

    existing = permission_insert_codes(STAGE7A_MIGRATION) | permission_insert_codes(
        STAGE7B_MIGRATION
    )
    stage7c = permission_insert_codes(MIGRATION)
    assert len(existing) == 28
    assert stage7c == STAGE7C_PERMISSIONS
    assert len(stage7c) == 12
    assert all(PERMISSION_KEY_PATTERN.fullmatch(code) for code in existing | stage7c)

    malformed = {
        "API_KEYS.read",
        "api-keys.read",
        "_api.read",
        "api_.read",
        "api__keys.read",
        "api",
        "api.",
        ".read",
        "api.keys.extra",
    }
    assert all(PERMISSION_KEY_PATTERN.fullmatch(code) is None for code in malformed)


def test_migration_is_forward_only_and_all_nine_tables_are_rls_hardened() -> None:
    sql = read(MIGRATION).lower()
    tables = (
        "plans", "workspace_subscriptions", "plan_entitlements", "provider_registry",
        "workspace_provider_settings", "credential_references", "workspace_api_keys",
        "workspace_security_settings", "workspace_settings",
    )
    for table in tables:
        assert f"create table platform.{table}" in sql
        assert f"alter table platform.{table} enable row level security" in sql
        assert f"alter table platform.{table} force row level security" in sql
    assert "drop table" not in sql
    assert "truncate" not in sql
    assert "create extension" not in sql
    assert "alter extension" not in sql
    assert "from anon, authenticated" in sql


def test_every_retained_entitlement_is_measured_and_enforced() -> None:
    sql = read(MIGRATION).lower()
    cases = (
        ("max_assistants", "platform.assistants", "workspace_id = new.workspace_id"),
        ("max_knowledge_sources", "platform.knowledge_sources", "workspace_id = new.workspace_id"),
        ("max_workspace_members", "platform.workspace_memberships", "status = 'active'"),
        ("max_teams", "platform.teams", "workspace_id = new.workspace_id"),
        ("max_custom_roles", "platform.roles", "not is_system"),
        ("max_api_keys", "platform.workspace_api_keys", "expires_at is null or expires_at > now()"),
    )
    for entitlement, table, measurement in cases:
        assert entitlement in sql
        assert table in sql
        assert measurement in sql
    assert "for update of subscription" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "measured_count := greatest(measured_count, current_count)" in sql
    assert "entitlement_limit_reached" in sql


def test_free_defaults_are_explicitly_unlimited_and_not_magic_numbers() -> None:
    sql = read(MIGRATION).lower()
    assert "limit_value bigint check (limit_value is null or limit_value >= 0)" in sql
    assert sql.count("null::bigint") == 6
    assert "999999" not in sql
    assert "-1" not in sql


def test_authoritative_create_paths_check_limits_and_audit_denial() -> None:
    bootstrap, access = read(BOOTSTRAP), read(ACCESS)
    stage1 = read(
        ROOT / "supabase/migrations/20260906070000_stage1_authority_data_foundation.sql"
    )
    assert "max_assistants" not in bootstrap
    assert "assistant.create_denied" not in bootstrap
    assert "drop trigger if exists stage7c_assistant_limit_before_insert" in stage1
    assert "max_knowledge_sources" in bootstrap
    assert "knowledge_source.create_denied" in bootstrap
    for key in ("max_teams", "max_custom_roles"):
        assert key in access
    for action in ("team.create_denied", "role.create_denied"):
        assert action in access
    assert '"denied"' in bootstrap
    assert '"denied"' in access


def test_member_limit_is_atomic_at_invitation_acceptance() -> None:
    sql = read(MIGRATION).lower()
    function = sql.split("create function platform.accept_invitation_stage7c", 1)[1]
    function = function.split("create function platform.check_api_key_creation", 1)[0]
    assert "for update" in function
    assert "max_workspace_members" in function
    assert "status = 'active'" in function
    assert "invitation.accept_denied" in function
    assert function.index("stage7c_entitlement_decision") < function.index(
        "insert into platform.workspace_memberships"
    )
    assert function.index("insert into platform.workspace_memberships") < function.index(
        "set status='accepted'"
    )
    assert "platform.workspace_memberships" in function


def test_invitation_security_settings_are_enforced_at_actual_insert() -> None:
    sql = read(MIGRATION).lower()
    api = read(ROOT / "src/knowledge_platform/delivery/identity_provisioning_api.py")
    assert "stage7c_invitation_policy_before_insert" in sql
    assert "invitations_enabled" in sql
    assert "invitation_expiry_exceeds_policy" in sql
    assert "max_invitation_expiry_days" in sql
    assert "expires_in_days" in api
    assert "expires_in_days" in read(ROOT / "frontend/system/pages.js")


def test_subscription_state_has_deliberate_mutation_semantics() -> None:
    sql, service = read(MIGRATION).lower(), read(SERVICE)
    assert "subscription_state not in ('active','trialing')" in sql
    assert "return 'subscription_inactive'" in sql
    assert "subscription.state in ('active','trialing') as mutations_allowed" in service
    for state in ("past_due", "suspended", "cancelled"):
        assert state in sql


def test_provider_and_credential_manage_permissions_have_real_capabilities() -> None:
    api, service, sql = read(API), read(SERVICE), read(MIGRATION)
    assert '@router.patch("/workspaces/{workspace_id}/providers/{provider_code}"' in api
    assert "def update_provider" in service
    assert "update_workspace_provider" in sql
    assert '@router.post("/workspaces/{workspace_id}/credentials"' in api
    assert '@router.delete("/workspaces/{workspace_id}/credentials/{reference_id}"' in api
    assert "save_credential_reference" in sql
    assert "delete_credential_reference" in sql
    assert "billing.read" not in api + service + sql


def test_credential_contract_is_reference_only_and_non_disclosing() -> None:
    service, sql = read(SERVICE), read(CREDENTIALS_MIGRATION)
    list_query = service.split("def credentials", 1)[1].split(
        "def save_credential_reference", 1
    )[0]
    assert "platform.list_credential_references(:workspace)" in list_query
    assert "platform.credential_references" not in list_query
    assert "secret_reference" not in list_query
    assert "reference_type" in list_query
    assert "returns table(" in sql
    assert "when credential.secret_reference like 'env:%' then 'env'" in sql
    assert "when credential.secret_reference like 'vault:%' then 'vault'" in sql
    listing = sql.split("create function platform.list_credential_references", 1)[1].split(
        "create or replace function platform.save_credential_reference", 1
    )[0]
    assert "secret_reference text" not in listing
    assert "platform.user_has_system_permission('credentials.read')" in listing
    assert "platform.user_has_permission" not in listing
    assert "platform.user_has_workspace_membership" not in listing
    assert "where credential.workspace_id = target_workspace" in listing
    assert "raise exception using errcode = '42501'" in listing
    assert "secret_reference: SecretStr" in read(API)
    assert "get_secret_value()" in read(API)
    assert "revoke select on table platform.credential_references" in sql
    assert "grant execute on function platform.list_credential_references(uuid)" in sql


def test_credential_mutation_functions_are_system_only() -> None:
    service, sql = read(SERVICE), read(CREDENTIALS_MIGRATION)
    save = sql.split("create or replace function platform.save_credential_reference", 1)[1].split(
        "create or replace function platform.delete_credential_reference", 1
    )[0]
    delete = sql.split("create or replace function platform.delete_credential_reference", 1)[1]
    assert "platform.user_has_system_permission('credentials.manage')" in save
    assert "platform.user_has_system_permission('credentials.manage')" in delete
    assert "platform.user_has_permission" not in save + delete
    assert "platform.user_has_workspace_membership" not in save + delete
    assert "self._access.require_system(user_id, Permission.CREDENTIALS_MANAGE)" in service
    assert "revoke all on function platform.save_credential_reference" in sql
    assert "revoke all on function platform.delete_credential_reference" in sql


def test_api_key_is_generated_once_hash_only_and_constant_time_verified() -> None:
    service, sql = read(SERVICE), read(MIGRATION).lower()
    assert 'raw = "kp_" + secrets.token_hex(32)' in service
    assert "hashlib.sha256" in service
    assert "hmac.compare_digest" in service
    assert '"secret": raw' in service
    list_query = service.split("def api_keys", 1)[1].split("def create_api_key", 1)[0]
    assert "secret_hash" not in list_query
    assert "lookup_workspace_api_key" in sql
    assert "touch_workspace_api_key" in sql
    assert "revoked_at is null" in sql
    assert "expires_at is null or expires_at > now()" in sql
    assert "cardinality(scopes) > 0" in sql
    assert "API_KEY_EXPIRY_INVALID" in service
    assert "grant select (id,workspace_id,name,key_prefix,scopes" in sql


def test_api_key_principal_is_dedicated_and_scope_checked() -> None:
    source = read(AUTH)
    assert "class ApiKeyPrincipal" in source
    assert "return permission in self.scopes" in source
    assert 'raise PermissionError("API_KEY_SCOPE_DENIED")' in source
    assert "app.api_key_id" in source
    assert "UUID(int=0)" in source
    binding = source.split("def bind_authorization_context", 1)[1]
    assert "str(principal.created_by)" not in binding


def test_middleware_maps_every_stage7c_mutation_permission() -> None:
    security = read(SECURITY)
    for permission in (
        "PROVIDERS_MANAGE", "CREDENTIALS_MANAGE", "API_KEYS_MANAGE",
        "SECURITY_MANAGE", "WORKSPACE_SETTINGS_MANAGE", "SUBSCRIPTIONS_MANAGE",
    ):
        assert permission in security
    assert "/api/plans" not in security
    assert "workspaces/[^/]+/plans" in security


def test_plan_catalogue_delivery_is_workspace_authorized_and_globally_read() -> None:
    api = read(API)
    service = read(SERVICE)

    assert '@router.get("/workspaces/{workspace_id}/plans")' in api
    assert '@router.get("/plans")' not in api
    assert "service.plans(user(request), workspace_id)" in api

    plans_method = service.split("def plans(", 1)[1].split("def subscription(", 1)[0]
    assert "Permission.PLANS_READ" in plans_method
    assert "self._tx(user_id, workspace_id)" in plans_method
    plans_query = plans_method.split('text("""', 1)[1].split('""")', 1)[0]
    assert "from platform.plans" in plans_query
    assert "where status='active'" in plans_query
    assert "workspace_id" not in plans_query


def test_security_definer_functions_are_hardened_and_grants_minimal() -> None:
    sql = read(MIGRATION).lower()
    assert sql.count("security definer") >= 15
    assert sql.count("set search_path = ''") == sql.count("security definer")
    assert "grant insert" not in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    for function in (
        "stage7c_entitlement_decision", "stage7c_enforce_count_limit",
        "stage7c_enforce_invitation_policy",
    ):
        assert f"grant execute on function platform.{function}" not in sql


def test_stage7c_ui_is_arabic_first_and_uses_shared_spa_state() -> None:
    ui = read(UI)
    routes = read(SYSTEM_ROUTES)
    assert 'system("/system/policies", "الضوابط والسياسات"' in routes
    assert 'system("/system/providers", "المزودون والنماذج"' in routes
    assert 'system("/system/credentials", "بيانات الاعتماد"' in routes
    assert "workspaceCache" in ui
    assert "workspaceCache.staleWhileRevalidate" in ui
    assert "SYSTEM_SCOPE" in ui
    assert "POLICY_LABELS" in ui
    assert "providersPage" in ui
    assert "credentialsPage" in ui
    assert "security.manage" in ui
    assert "billing.read" not in ui
