"""Focused contracts for the final System Teams product surface."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_system_navigation_places_teams_immediately_before_members() -> None:
    routes = read("frontend/system/routes.js")
    knowledge = routes.index('system("/system/knowledge"')
    teams = routes.index('system("/system/teams"')
    members = routes.index('system("/system/members"')
    roles = routes.index('system("/system/roles"')

    assert knowledge < teams < members < roles
    assert routes[teams:members].count('system("/system/') == 1
    assert routes[members:roles].count('system("/system/') == 1
    assert routes.count('system("/system') == 14


def test_team_schema_requires_exactly_one_workspace() -> None:
    migration = read(
        "supabase/migrations/20260904184807_stage7a_identity_access_control.sql"
    ).lower()
    teams = migration.split("create table platform.teams", 1)[1].split(
        "create table platform.team_members", 1
    )[0]

    assert "workspace_id uuid not null references platform.workspaces (id)" in teams
    assert "unique (id, workspace_id)" in teams
    assert "teams_workspace_name_unique" in teams


def test_team_creation_requires_an_explicit_workspace_in_ui_and_api() -> None:
    pages = read("frontend/system/pages.js")
    form = pages.split("function teamForm", 1)[1].split(
        "function teamMembers", 1
    )[0]
    delivery = read("src/knowledge_platform/delivery/access_control_api.py")
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    save = persistence.split("def save_team", 1)[1].split("def delete_team", 1)[0]

    assert 'required: "required", "aria-label": "مساحة العمل"' in form
    assert 'el("option", { value: "", selected: "selected", disabled: "disabled" }' in form
    assert "form.reportValidity()" in form
    assert "team?.workspace_id || workspace?.value" in form
    assert '@router.post("/workspaces/{workspace_id}/teams"' in delivery
    assert "select exists(select 1 from platform.workspaces" in save
    assert "insert into platform.teams(id,workspace_id,name,description)" in save


def test_team_detail_shows_workspace_members_and_product_metadata() -> None:
    pages = read("frontend/system/pages.js")
    detail = pages.split("function teamDetails", 1)[1].split(
        "export function teamsPage", 1
    )[0]

    for expected in (
        'infoField("اسم الفريق", team.name)',
        'infoField("مساحة العمل", workspace.name)',
        'infoField("الوصف", team.description',
        'infoField("تاريخ الإنشاء", formatDate(team.created_at))',
        'panel("أعضاء الفريق", memberTable)',
        'roleLabel(member.role_name)',
        'statusBadge(member.status)',
        "عرض وإدارة",
    ):
        assert expected in detail or expected in pages


def test_team_member_assignment_is_same_workspace_and_fail_closed() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    assignment = persistence.split("def set_team_member", 1)[1].split(
        "def create_invitation", 1
    )[0]
    migration = read(
        "supabase/migrations/20260904184807_stage7a_identity_access_control.sql"
    ).lower()
    team_members = migration.split("create table platform.team_members", 1)[1].split(
        "create table platform.invitations", 1
    )[0]

    assert "Permission.TEAMS_MANAGE" in assignment
    assert "where id=:team and workspace_id=:workspace" in assignment
    assert "where workspace_id=:workspace and user_id=:member" in assignment
    assert "if not team_exists or not member_exists" in assignment
    assert "foreign key (team_id, workspace_id)" in team_members
    assert "foreign key (workspace_id, user_id)" in team_members


def test_team_ownership_is_immutable_and_teams_do_not_grant_permissions() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    save = persistence.split("def save_team", 1)[1].split("def delete_team", 1)[0]
    permission_lookup = persistence.split("def permissions", 1)[1].split(
        "def system_permissions", 1
    )[0]

    assert "update platform.teams set name=:n,description=:d" in save
    assert "set workspace_id" not in save
    assert "team_members" not in permission_lookup
