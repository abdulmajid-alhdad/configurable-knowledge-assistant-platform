import hashlib

import pytest

from knowledge_platform.infrastructure.documents.artifacts import FilesystemOriginalArtifactStore
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


def test_original_artifact_is_persistent_idempotent_and_path_safe(tmp_path) -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    store = FilesystemOriginalArtifactStore(tmp_path)
    value = b"hello document"
    artifact = store.store(
        workspace_id=workspace_id, source_id=source_id, chunks=(value,),
        filename="../notes.txt", media_type="text/plain", max_bytes=1000,
    )
    assert artifact.sha256 == hashlib.sha256(value).hexdigest()
    assert store.exists(workspace_id=workspace_id, source_id=source_id)
    assert store.retrieve(artifact) == value
    same = store.store(
        workspace_id=workspace_id, source_id=source_id, chunks=(value,),
        filename="notes.txt", media_type="text/plain", max_bytes=1000,
    )
    assert same.sha256 == artifact.sha256
    with pytest.raises(ValueError, match="different original"):
        store.store(
            workspace_id=workspace_id, source_id=source_id, chunks=(b"other",),
            filename="other.txt", media_type="text/plain", max_bytes=1000,
        )


def test_oversized_upload_cleans_partial_file(tmp_path) -> None:
    workspace_id, source_id = WorkspaceId.new(), KnowledgeSourceId.new()
    store = FilesystemOriginalArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="maximum size"):
        store.store(
            workspace_id=workspace_id, source_id=source_id, chunks=(b"123", b"456"),
            filename="large.txt", media_type="text/plain", max_bytes=5,
        )
    assert not store.exists(workspace_id=workspace_id, source_id=source_id)
