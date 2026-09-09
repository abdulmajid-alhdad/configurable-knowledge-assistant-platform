import hashlib
from collections.abc import Iterator

import pytest

from knowledge_platform.infrastructure.documents.artifacts import FilesystemOriginalArtifactStore
from knowledge_platform.modules.document_knowledge.artifacts import (
    OriginalArtifactIntegrityError,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


def test_original_artifact_is_persistent_immutable_and_path_safe(tmp_path) -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    store = FilesystemOriginalArtifactStore(tmp_path)
    value = b"hello document"
    artifact = store.store(
        workspace_id=workspace_id, source_id=source_id, chunks=(value,),
        filename="../notes.txt", media_type="text/plain", max_bytes=1000,
    )
    assert artifact.sha256 == hashlib.sha256(value).hexdigest()
    assert artifact.stored_at is not None
    assert store.exists(workspace_id=workspace_id, source_id=source_id)
    assert store.retrieve(artifact) == value
    with pytest.raises(ValueError, match="already has an original artifact"):
        store.store(
            workspace_id=workspace_id, source_id=source_id, chunks=(value,),
            filename="notes.txt", media_type="text/plain", max_bytes=1000,
        )
    assert store.retrieve(artifact) == value


def test_oversized_upload_cleans_partial_file(tmp_path) -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    store = FilesystemOriginalArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="maximum size"):
        store.store(
            workspace_id=workspace_id, source_id=source_id, chunks=(b"123", b"456"),
            filename="large.txt", media_type="text/plain", max_bytes=5,
        )
    assert not store.exists(workspace_id=workspace_id, source_id=source_id)


def test_incomplete_artifact_is_not_reported_as_a_persisted_original(tmp_path) -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    directory = (
        tmp_path
        / "workspaces"
        / str(workspace_id.value)
        / "sources"
        / str(source_id.value)
    )
    directory.mkdir(parents=True)
    (directory / "original").write_bytes(b"orphaned payload")

    store = FilesystemOriginalArtifactStore(tmp_path)

    with pytest.raises(OriginalArtifactIntegrityError, match="incomplete"):
        store.get(workspace_id=workspace_id, source_id=source_id)


def test_failed_upload_leaves_no_partial_artifact_and_remains_retryable(tmp_path) -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    store = FilesystemOriginalArtifactStore(tmp_path)

    def interrupted_chunks() -> Iterator[bytes]:
        yield b"partial"
        raise OSError("simulated stream failure")

    with pytest.raises(OSError, match="simulated stream failure"):
        store.store(
            workspace_id=workspace_id,
            source_id=source_id,
            chunks=interrupted_chunks(),
            filename="ملف.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            max_bytes=1000,
        )

    assert not store.exists(workspace_id=workspace_id, source_id=source_id)
    artifact = store.store(
        workspace_id=workspace_id,
        source_id=source_id,
        chunks=(b"complete",),
        filename="ملف.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        max_bytes=1000,
    )
    assert artifact.original_filename == "ملف.docx"
    assert store.retrieve(artifact) == b"complete"
