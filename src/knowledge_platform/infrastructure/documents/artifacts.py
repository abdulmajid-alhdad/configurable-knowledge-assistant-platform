"""Atomic persistent filesystem storage for original uploaded artifacts."""
# ruff: noqa: E501

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from knowledge_platform.modules.document_knowledge.artifacts import OriginalArtifact
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class FilesystemOriginalArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _directory(self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> Path:
        return self._root / "workspaces" / str(workspace_id.value) / "sources" / str(source_id.value)

    def get(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> OriginalArtifact | None:
        path = self._directory(workspace_id, source_id) / "metadata.json"
        if not path.is_file():
            return None
        return OriginalArtifact(
            workspace_id=workspace_id, source_id=source_id,
            **json.loads(path.read_text(encoding="utf-8")),
        )

    def exists(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> bool:
        return self.get(workspace_id=workspace_id, source_id=source_id) is not None

    def store(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId,
              chunks: Iterable[bytes], filename: str, media_type: str | None,
              max_bytes: int) -> OriginalArtifact:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if not safe_name or safe_name in {".", ".."} or not suffix:
            raise ValueError("a supported filename is required")
        directory = self._directory(workspace_id, source_id)
        directory.mkdir(parents=True, exist_ok=True)
        existing = self.get(workspace_id=workspace_id, source_id=source_id)
        digest = hashlib.sha256()
        size = 0
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("artifact exceeds maximum size")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            sha256 = digest.hexdigest()
            if existing is not None and existing.sha256 != sha256:
                raise ValueError("source already has a different original artifact")
            artifact = OriginalArtifact(
                workspace_id=workspace_id, source_id=source_id,
                original_filename=safe_name, suffix=suffix, media_type=media_type,
                byte_size=size, sha256=sha256,
            )
            os.replace(temporary, directory / "original")
            (directory / "metadata.json").write_text(
                json.dumps({
                    "original_filename": artifact.original_filename,
                    "suffix": artifact.suffix, "media_type": artifact.media_type,
                    "byte_size": artifact.byte_size, "sha256": artifact.sha256,
                }, sort_keys=True), encoding="utf-8",
            )
            return artifact
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def retrieve(self, artifact: OriginalArtifact) -> bytes:
        return (self._directory(artifact.workspace_id, artifact.source_id) / "original").read_bytes()
