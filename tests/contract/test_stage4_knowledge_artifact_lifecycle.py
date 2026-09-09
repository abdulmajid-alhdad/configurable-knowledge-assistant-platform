"""Focused contracts for the immutable original-artifact lifecycle."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_upload_boundary_allows_only_missing_artifacts_in_safe_lifecycles() -> None:
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")
    section = bootstrap.split("async def upload_source", 1)[1].split(
        "def process_source", 1
    )[0]

    assert "Permission.SYSTEM_KNOWLEDGE_CREATE" in section
    assert "artifacts.get(workspace_id=wid, source_id=sid) is not None" in section
    assert 'raise ValueError("source already has an original artifact")' in section
    for lifecycle in ("REGISTERED", "FAILED", "READY"):
        assert f"KnowledgeSourceLifecycle.{lifecycle}" in section
    assert section.index("artifacts.get") < section.index("async for chunk")
    assert "source_processing_service" not in section
    assert "document_representations" not in section


def test_artifact_detail_contract_exposes_safe_real_metadata_and_states() -> None:
    delivery = read("src/knowledge_platform/delivery/product_api.py")
    response = delivery.split("class SourceArtifactResponse", 1)[1].split(
        "class ManagementServices", 1
    )[0]
    upload = delivery.split('"/workspaces/{workspace_id}/sources/{source_id}/upload"', 1)[
        1
    ].split('"/workspaces/{workspace_id}/sources/{source_id}/process"', 1)[0]

    for field in (
        "artifact_state",
        "upload_allowed",
        "original_filename",
        "media_type",
        "byte_size",
        "stored_at",
    ):
        assert field in response
    for state in ("AWAITING_UPLOAD", "STORED", "LEGACY_UNAVAILABLE"):
        assert state in delivery
    assert "artifact.sha256" not in upload
    assert "unquote_to_bytes(encoded_filename).decode" in upload


def test_system_ui_distinguishes_initial_stored_and_legacy_artifacts() -> None:
    pages = read("frontend/system/pages.js")
    section = pages.split("function sourceDetails", 1)[1].split(
        "export function knowledgePage", 1
    )[0]

    assert 'artifact.artifact_state === "LEGACY_UNAVAILABLE"' in section
    assert 'artifact.artifact_state === "AWAITING_UPLOAD"' in section
    assert "بانتظار رفع الملف الأصلي" in section
    assert "الملف الأصلي المحفوظ" in section
    assert "إرفاق الملف الأصلي" in section
    assert "المعرفة المفهرسة الحالية متاحة" in section
    assert "حالة المعالجة" in section
    assert "توفر الملف الأصلي" in section
    assert "artifact.media_type" in section
    assert "artifact.byte_size" in section
    assert "artifact.stored_at" in section
    assert 'if (!artifact.artifact_present || !can("system_knowledge.process")) return;' in section
    assert '"x-file-name": encodeURIComponent(selectedFile.name)' in section
    assert '"x-file-name-encoding": "percent"' in section


def test_source_list_shows_processing_and_artifact_states_independently() -> None:
    pages = read("frontend/system/pages.js")
    ui = read("frontend/shared/ui.js")
    list_section = pages.split("export function knowledgePage", 1)[1]

    assert '"حالة المعالجة", "الملف الأصلي"' in list_section
    assert "artifactAvailability(source.artifact)" in list_section
    assert "artifact" in pages.split("async function allSources", 1)[1].split(
        "function createSourceForm", 1
    )[0]
    assert 'LEGACY_UNAVAILABLE: "الملف الأصلي غير متوفر — مصدر تاريخي"' in ui
    assert 'AWAITING_UPLOAD: "بانتظار رفع الملف الأصلي"' in ui


def test_missing_artifact_is_checked_before_processing_state_transition() -> None:
    processing = read("src/knowledge_platform/application/knowledge_ingestion.py")
    service = processing.split("class KnowledgeSourceProcessingService", 1)[1].split(
        "class KnowledgeIngestionService", 1
    )[0]

    assert "original_artifact_exists" in service
    assert service.index("original_artifact_exists") < service.index("def prepare")
    assert 'raise FileNotFoundError("original artifact is not stored")' in service


def test_processing_resolves_the_persisted_original_and_never_reconstructs_it() -> None:
    processing = read("src/knowledge_platform/application/knowledge_ingestion.py")
    section = processing.split("class KnowledgeIngestionService", 1)[1]

    assert "artifact = self._artifacts.get" in section
    assert 'raise FileNotFoundError("original artifact is not stored")' in section
    assert "self._artifacts.retrieve(artifact)" in section
    assert "document_chunks" not in section
    assert "reconstruct" not in section.lower()
