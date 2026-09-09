"""Focused contracts for Workspace Knowledge upload and processing."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def load_workspace_admin_mutation(source: str):  # type: ignore[no-untyped-def]
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_workspace_admin_mutation"
    )
    namespace = {"re": re, "UNSAFE": {"POST", "PATCH", "PUT", "DELETE"}}
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, "security.py", "exec"), namespace)
    return namespace["_workspace_admin_mutation"]


def test_workspace_knowledge_routes_reach_canonical_permissions() -> None:
    security = read("src/knowledge_platform/delivery/security.py")
    workspace_admin_mutation = load_workspace_admin_mutation(security)
    workspace = "00000000-0000-0000-0000-000000000001"
    source = "00000000-0000-0000-0000-000000000002"

    assert not workspace_admin_mutation(
        f"/api/workspaces/{workspace}/sources", "POST"
    )
    assert not workspace_admin_mutation(
        f"/api/workspaces/{workspace}/sources/{source}/upload", "POST"
    )
    assert not workspace_admin_mutation(
        f"/api/workspaces/{workspace}/sources/{source}/process", "POST"
    )
    assert '"POST": Permission.KNOWLEDGE_CREATE' in security
    assert '"POST": Permission.KNOWLEDGE_PROCESS' in security


def test_upload_uses_workspace_permission_policy_and_safe_filename_transport() -> None:
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")
    delivery = read("src/knowledge_platform/delivery/product_api.py")
    frontend = read("frontend/app/pages.js")

    service = bootstrap.split("async def upload_source", 1)[1].split(
        "def process_source", 1
    )[0]
    route = delivery.split("async def upload_source", 1)[1].split(
        '@router.post("/workspaces/{workspace_id}/sources/{source_id}/process"', 1
    )[0]
    assert "system_operation: bool = False" in service
    assert "Permission.SYSTEM_KNOWLEDGE_CREATE" in service
    assert "Permission.KNOWLEDGE_CREATE" in service
    assert "knowledge_source_addition_enabled" in service
    assert 'source_id=sid, workspace_id=wid' in service
    assert "source already has an original artifact" in service
    assert "knowledge_source_addition_enabled" in route
    assert "system_operation=True" in route
    assert '"x-file-name": encodeURIComponent(selectedFile.name)' in frontend
    assert '"x-file-name-encoding": "percent"' in frontend


def test_artifact_ui_is_immutable_and_uses_confirmed_upload_response() -> None:
    frontend = read("frontend/app/pages.js")
    details = frontend.split("function sourceDetails", 1)[1].split(
        "export function knowledgePage", 1
    )[0]

    assert "/sources/${source.id}/artifact" in details
    assert "source.artifact.artifact_present" in details
    assert "source.artifact.upload_allowed" in details
    assert "source.artifact = stored" in details
    assert "اسم الملف الأصلي" in details
    assert "original_filename" in details
    assert "media_type" in details
    assert "byte_size" in details
    assert "stored_at" in details
    assert 'workspaceKnowledgeError(error, "upload")' in details
    assert "actions.append(apiError(error))" not in details


def test_processing_policy_precedes_hard_gates_and_external_execution() -> None:
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")
    service = bootstrap.split("def process_source", 1)[1].split(
        "def attach_source", 1
    )[0]

    policy = service.index("knowledge_processing_enabled")
    operational_gate = service.index("require_ai_execution")
    processing = service.index("source_processing_service")
    assert policy < operational_gate < processing
    assert "Permission.KNOWLEDGE_PROCESS" in service
    assert "Permission.SYSTEM_KNOWLEDGE_PROCESS" in service
    assert "if system_operation:" in service


def test_workspace_processing_does_not_write_system_administrative_operation() -> None:
    delivery = read("src/knowledge_platform/delivery/product_api.py")
    route = delivery.split("def process_source", 1)[1].split(
        "def list_attached_sources", 1
    )[0]

    assert "if administration is not None and system:" in route
    assert "if system:" in route
    assert "source_processing_administration_record_failed" in route
    assert route.rindex("return _source(value)") > route.index(
        "source_processing_administration_record_failed"
    )


def test_workspace_ui_has_action_specific_feedback_and_cache_update() -> None:
    frontend = read("frontend/app/pages.js")
    details = frontend.split("function sourceDetails", 1)[1].split(
        "export function knowledgePage", 1
    )[0]

    assert "تعذر رفع الملف." in frontend
    assert "تعذر معالجة المصدر." in frontend
    assert "إضافة محتوى المعرفة متوقفة" in frontend
    assert "معالجة مصادر المعرفة متوقفة" in frontend
    assert "لا يوجد ملف أصلي محفوظ لهذا المصدر." in frontend
    assert "workspaceCache.set" in details
    assert "Object.assign(source, updated)" in details
    assert 'workspaceKnowledgeError(error, "process")' in details