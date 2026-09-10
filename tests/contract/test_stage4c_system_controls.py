"""Focused contracts for Stage 4C System controls and operations."""

from pathlib import Path
from uuid import UUID

from knowledge_platform.application.provider_usage import ProviderUsageService
from knowledge_platform.infrastructure.provider_usage import OpenRouterUsageAdapter
from knowledge_platform.modules.access_control.domain import Permission

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_all_seven_stage4c_routes_use_real_page_implementations() -> None:
    routes = read("frontend/system/routes.js")
    assert routes.count('system("/system') == 14
    for page in (
        "policies",
        "usage",
        "providers",
        "credentials",
        "conversations",
        "audit",
        "access",
    ):
        assert f"SYSTEM_CONTROL_PAGES.{page}" in routes
    assert "ستتم تهيئة هذه الواجهة" not in routes


def test_stage4c_browser_uses_only_same_origin_platform_apis_and_safe_dom() -> None:
    pages = read("frontend/system/controls-pages.js")
    assert 'from "/assets/shared/api.js"' in pages
    assert "/api/system/" in pages
    assert "innerHTML" not in pages
    assert "insertAdjacentHTML" not in pages
    assert "supabase" not in pages.lower()
    assert "fetch(" not in pages


def test_policy_surface_exposes_only_approved_operational_controls() -> None:
    pages = read("frontend/system/controls-pages.js")
    assert "knowledge_source_addition_enabled" in pages
    assert "knowledge_processing_enabled" in pages
    assert "invitations_enabled" in pages
    assert "api_keys_enabled" in pages
    assert "max_invitation_expiry_days" in pages
    assert "assistant_creation_enabled" not in pages
    assert "generation_enabled" not in pages
    assert "embedding_enabled" not in pages


def test_usage_uses_provider_telemetry_not_internal_usage_events() -> None:
    pages = read("frontend/system/controls-pages.js")
    delivery = read("src/knowledge_platform/delivery/provider_usage_api.py")
    service = read("src/knowledge_platform/application/provider_usage.py")
    adapter = read(
        "src/knowledge_platform/infrastructure/provider_usage/openrouter.py"
    )
    assert 'getJSON("/api/system/usage/provider")' in pages
    assert 'prefix="/api/system/usage"' in delivery
    assert '@router.get("/provider")' in delivery
    assert "Permission.USAGE_READ" in service
    assert "https://openrouter.ai/api/v1/key" in adapter
    assert '"usage_daily"' in adapter
    assert '"usage_monthly"' in adapter
    assert '"label"' not in adapter
    assert '"api_key"' not in adapter
    assert "usage_events" not in pages


def test_provider_usage_is_authorized_and_normalized_without_secret_fields() -> None:
    class Access:
        checked: tuple[UUID, Permission] | None = None

        def require_system(self, actor: UUID, permission: Permission) -> None:
            self.checked = (actor, permission)

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "data": {
                    "usage": 2.5,
                    "usage_daily": 0.25,
                    "limit": 10,
                    "label": "must-not-leak",
                }
            }

    class Client:
        @staticmethod
        def get(*_args: object, **_kwargs: object) -> Response:
            return Response()

    actor = UUID("00000000-0000-0000-0000-000000000123")
    access = Access()
    service = ProviderUsageService(
        access=access,  # type: ignore[arg-type]
        telemetry=OpenRouterUsageAdapter(api_key="test-only", client=Client()),
    )
    result = service.summary(actor)
    assert access.checked == (actor, Permission.USAGE_READ)
    assert result["usage"] == 2.5
    assert "label" not in result
    assert "api_key" not in result


def test_provider_catalogue_reads_runtime_metadata_without_model_execution() -> None:
    pages = read("frontend/system/controls-pages.js")
    provider_section = pages.split("export function providersPage", 1)[1].split(
        "function credentialForm", 1
    )[0]
    assert "/providers" in provider_section
    assert "/assistants" in provider_section
    assert 'getJSON("/api/system/providers/runtime")' in provider_section
    assert "data.runtime.effective.embedding" in provider_section
    assert "/ask" not in provider_section
    assert "/process" not in provider_section
    assert "/chat/completions" not in provider_section
    assert "/embeddings" not in provider_section


def test_credentials_return_and_render_reference_metadata_only() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/commercial.py"
    )
    migration = read(
        "supabase/migrations/20260910004757_system_credentials_control_plane.sql"
    )
    pages = read("frontend/system/controls-pages.js")
    query = persistence.split("def credentials", 1)[1].split(
        "def save_credential_reference", 1
    )[0]
    assert "reference_type" in query
    assert "platform.list_credential_references(:workspace)" in query
    assert "platform.credential_references" not in query
    assert "secret_reference" not in query
    assert "when credential.secret_reference like 'env:%' then 'env'" in migration
    assert "when credential.secret_reference like 'vault:%' then 'vault'" in migration
    assert "item.secret_reference" not in pages
    assert "raw API" not in pages


def test_system_conversations_are_separate_system_scope_and_have_no_delete() -> None:
    delivery = read("src/knowledge_platform/delivery/system_conversation_api.py")
    service = read("src/knowledge_platform/application/system_conversations.py")
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/system_conversations.py"
    )
    pages = read("frontend/system/controls-pages.js")
    assert 'prefix="/api/system/conversations"' in delivery
    assert '"/{conversation_id}/ask"' in delivery
    assert "workspace_id" in delivery
    assert "Permission.SYSTEM_CONVERSATIONS_READ" in service
    assert "Permission.SYSTEM_ASSISTANTS_READ" in service
    assert "Permission.SYSTEM_KNOWLEDGE_READ" in service
    visibility = service.split("def get", 1)[1].split("def rename", 1)[0]
    assert "created_by" not in visibility
    assert "system_session_scope" in persistence
    assert '@router.delete(' not in delivery
    section = pages.split("export function systemConversationsPage", 1)[1].split(
        "function auditDetails", 1
    )[0]
    assert "/api/system/conversations" in section
    assert 'method: "DELETE"' not in section
    assert "/api/workspaces/" not in section


def test_audit_metadata_is_redacted_before_delivery_and_ui_is_read_only() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/administration.py"
    )
    pages = read("frontend/system/controls-pages.js")
    assert "_SENSITIVE_METADATA_TERMS" in persistence
    assert '"[REDACTED]"' in persistence
    assert "_safe_audit_metadata(item.get(\"metadata\")" in persistence
    audit_section = pages.split("export function auditPage", 1)[1].split(
        "function systemAccessForm", 1
    )[0]
    assert "AUDIT_ACTION_LABELS" in pages
    assert '"assistant.updated": "تحديث المساعد"' in pages
    assert '"provider.updated": "تحديث المزوّد"' in pages
    assert '"security.updated": "تحديث إعدادات الأمان"' in pages
    assert "auditLabel(AUDIT_ACTION_LABELS, item.action).label" in audit_section
    assert 'el("option", { value: "" }, "كل الإجراءات")' in audit_section
    assert "actionFilter = actionSelect.value" in audit_section
    assert "/audit?" in audit_section
    assert 'method: "POST"' not in audit_section
    assert 'method: "PATCH"' not in audit_section
    assert 'method: "DELETE"' not in audit_section


def test_system_access_is_independent_and_last_admin_protection_is_preserved() -> None:
    delivery = read("src/knowledge_platform/delivery/access_control_api.py")
    persistence = read(
        "src/knowledge_platform/infrastructure/persistence/access_control.py"
    )
    security = read("src/knowledge_platform/delivery/security.py")
    pages = read("frontend/system/controls-pages.js")
    assert '@router.get("/users")' in delivery
    assert '@router.get("/access")' in delivery
    assert '@router.post("/access"' in delivery
    assert '@router.delete("/access/{user_id}/{role_id}"' in delivery
    assert "platform.assign_system_access" in persistence
    assert "platform.revoke_system_access" in persistence
    assert "Permission.SYSTEM_ACCESS_READ" in security
    assert "Permission.SYSTEM_ACCESS_MANAGE" in security
    assert 'assignment.role_name === "SYSTEM_ADMIN"' in pages
    assert "مدير مساحة العمل" in pages


def test_stage4c_routers_are_composed_without_schema_or_browser_secret_access() -> None:
    app = read("src/knowledge_platform/delivery/app.py")
    assert "create_provider_usage_router(runtime.provider_usage())" in app
    assert "create_system_conversation_router(runtime.system_conversations())" in app
    assert "credential_for_model" not in read(
        "src/knowledge_platform/delivery/provider_usage_api.py"
    )
