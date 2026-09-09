from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260908202313_identity_provisioning_activation.sql"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_migration_preserves_history_and_links_provisioned_identity_and_team() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "alter table platform.invitations" in sql
    assert "provisioned_user_id uuid references auth.users (id) on delete restrict" in sql
    assert "foreign key (team_id, workspace_id)" in sql
    assert "references platform.teams (id, workspace_id) on delete restrict" in sql
    assert "invitations_provisioned_user_unique" in sql
    assert "delete from platform.invitations" not in sql
    assert "truncate" not in sql
    assert "drop table" not in sql


def test_provisioning_creates_no_workspace_or_system_authority_before_activation() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    create = sql.split(
        "create function platform.create_identity_provisioning_invitation", 1
    )[1].split("create function platform.preview_identity_activation", 1)[0]
    activate = sql.split(
        "create function platform.activate_identity_provisioning", 1
    )[1].split("revoke all on function", 1)[0]

    assert "insert into platform.user_profiles" in create
    assert "insert into platform.invitations" in create
    assert "insert into platform.workspace_memberships" not in create
    assert "system_access_assignments" not in create
    assert "insert into platform.workspace_memberships" in activate
    assert "insert into platform.team_members" in activate
    assert "system_access_assignments" not in activate


def test_role_team_and_replay_guards_are_fail_closed() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "role.canonical_scope" not in sql
    assert "role.canonical_key in ('workspace_manager', 'member')" in sql
    assert "or role.role_kind = 'custom'" in sql
    assert "role.role_kind = 'built_in'" in sql
    assert "upper(role.name) <> 'system_admin'" in sql
    assert "team.id = target_team and team.workspace_id = target_workspace" in sql
    assert "team.id = invitation.team_id" in sql
    assert "team.workspace_id = invitation.workspace_id" in sql
    assert "invitation.status = 'accepted'" in sql
    assert "invitation_already_accepted" in sql
    assert "membership_already_exists" in sql
    assert "where candidate.token_hash = expected_hash\n  for update" in sql


def test_activation_preview_is_non_consuming_and_activation_is_atomic() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    preview = sql.split(
        "create function platform.preview_identity_activation", 1
    )[1].split("create function platform.activate_identity_provisioning", 1)[0]
    activate = sql.split(
        "create function platform.activate_identity_provisioning", 1
    )[1].split("revoke all on function", 1)[0]

    assert "update platform.invitations" not in preview
    assert "insert into platform.workspace_memberships" not in preview
    assert "update platform.invitations" in activate
    assert "status = 'accepted'" in activate
    assert "accepted_by = invitation.provisioned_user_id" in activate
    assert "on conflict" not in activate


def test_protected_functions_are_runtime_only_and_hardened() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for function in (
        "validate_identity_provisioning",
        "create_identity_provisioning_invitation",
        "preview_identity_activation",
        "activate_identity_provisioning",
    ):
        assert f"create function platform.{function}" in sql
        section = sql.split(f"create function platform.{function}", 1)[1]
        assert "security definer set search_path = ''" in section
        assert f"revoke all on function platform.{function}" in sql
        assert f"grant execute on function platform.{function}" in sql
    assert "to knowledge_platform_runtime" in sql
    assert "grant execute" in sql
    assert "to public" not in sql
    assert "to anon" not in sql
    assert "to authenticated" not in sql


def test_password_and_raw_token_never_reach_platform_persistence_or_audit() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/identity_provisioning.py"
    ).lower()
    service = read("src/knowledge_platform/application/identity_provisioning.py")

    assert "password" not in sql
    assert "password" not in persistence
    assert "expected_hash" in sql and "token_hash" in sql
    assert "token_digest" in persistence
    assert "token_urlsafe(32)" in service
    assert "activation_path=f\"/app/invitations/accept#token={raw_token}\"" in service


def test_identity_admin_key_and_password_remain_server_only() -> None:
    adapter = read("src/knowledge_platform/infrastructure/auth/supabase_admin.py")
    config = read("src/knowledge_platform/config/runtime.py")
    frontend = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "frontend").rglob("*.js")
    )

    assert 'validation_alias="SUPABASE_SECRET_KEY"' in config
    assert '"email_confirm": False' in adapter
    assert 'json={"email_confirm": True}' in adapter
    assert "/admin/users" in adapter
    assert "SUPABASE_SECRET_KEY" not in frontend
    assert "admin_secret" not in frontend


def test_delivery_exposes_system_provisioning_and_preauth_activation_only() -> None:
    delivery = read("src/knowledge_platform/delivery/identity_provisioning_api.py")
    legacy = read("src/knowledge_platform/delivery/auth_api.py")
    security = read("src/knowledge_platform/delivery/security.py")

    assert '@router.post("/api/system/identity/provision"' in delivery
    assert '@router.post("/api/auth/invitations/activation/preview")' in delivery
    assert '@router.post("/api/auth/invitations/activation")' in delivery
    assert "set_session_cookies" not in delivery
    assert '"login_path": "/login"' in delivery
    assert "/api/auth/invitations/accept" not in legacy
    assert '"/app/invitations/accept"' in security
    assert 'return Permission.INVITATIONS_MANAGE' in security


def test_activation_frontend_is_shell_free_non_consuming_and_never_logs_token_in_url() -> None:
    bootstrap = read("frontend/shared/bootstrap.js")
    activation = read("frontend/app/activation.js")

    assert 'window.location.pathname === "/app/invitations/accept"' in bootstrap
    assert "import(asset(\"/assets/app/activation.js\"))" in bootstrap
    assert "startSurface" not in activation
    assert "new URLSearchParams(window.location.hash.slice(1))" in activation
    assert 'window.history.replaceState(null, "", "/app/invitations/accept")' in activation
    assert "/api/auth/invitations/activation/preview" in activation
    assert "تفعيل الحساب" in activation
    assert "تم تفعيل الحساب" in activation
    assert "الانتقال إلى تسجيل الدخول" in activation
    assert "location.replace('/app')" not in activation
    assert 'request("/api/auth/sign-out", { method: "POST" })' in activation
    assert "window.location.replace(result.login_path || \"/login\")" in activation
    assert activation.index("/api/auth/invitations/activation") < activation.index(
        "/api/auth/sign-out"
    ) < activation.index("window.location.replace(result.login_path")


def test_system_members_provisioning_form_has_all_accepted_inputs() -> None:
    pages = read("frontend/system/pages.js")
    form = pages.split("function provisioningForm", 1)[1].split(
        "function memberRoleForm", 1
    )[0]

    for label in (
        "اسم المستخدم",
        "البريد الإلكتروني",
        "كلمة المرور الأولية",
        "مساحة العمل",
        "دور مساحة العمل",
        "الفريق (اختياري)",
        "مدة صلاحية الدعوة بالأيام",
    ):
        assert label in form
    assert '"/api/system/identity/provision"' in form
    assert "item.canonical_scope === \"WORKSPACE\"" in form
    assert 'String(item.name).toUpperCase() !== "SYSTEM_ADMIN"' in form
    assert "password.value = \"\"" in form
    assert "isSafeInternalUrl(invitation.activation_path)" in form


def test_login_has_no_team_membership_side_effect() -> None:
    login = read("src/knowledge_platform/delivery/auth_api.py").lower()
    activation = MIGRATION.read_text(encoding="utf-8").lower().split(
        "create function platform.activate_identity_provisioning", 1
    )[1]

    assert "team_members" not in login
    assert "insert into platform.team_members" in activation
