"""Atomic persistent filesystem storage for original uploaded artifacts."""
# ruff: noqa: E501

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from knowledge_platform.modules.document_knowledge.artifacts import (
    OriginalArtifact,
    OriginalArtifactIntegrityError,
)
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class FilesystemOriginalArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _directory(self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> Path:
        return self._root / "workspaces" / str(workspace_id.value) / "sources" / str(source_id.value)

    def get(self, *, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> OriginalArtifact | None:
        directory = self._directory(workspace_id, source_id)
        metadata_path = directory / "metadata.json"
        payload_path = directory / "original"
        metadata_exists = metadata_path.is_file()
        payload_exists = payload_path.is_file()
        if not metadata_exists and not payload_exists:
            return None
        if metadata_exists is not payload_exists:
            raise OriginalArtifactIntegrityError(
                "original artifact metadata and payload are incomplete"
            )
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            stored_at = metadata.pop("stored_at", None)
            return OriginalArtifact(
                workspace_id=workspace_id,
                source_id=source_id,
                stored_at=datetime.fromisoformat(stored_at) if stored_at else None,
                **metadata,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OriginalArtifactIntegrityError(
                "original artifact metadata is invalid"
            ) from exc

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
        if existing is not None:
            raise ValueError("source already has an original artifact")
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
            artifact = OriginalArtifact(
                workspace_id=workspace_id, source_id=source_id,
                original_filename=safe_name, suffix=suffix, media_type=media_type,
                byte_size=size, sha256=sha256, stored_at=datetime.now(UTC),
            )
            payload_path = directory / "original"
            metadata_path = directory / "metadata.json"
            payload_linked = False
            try:
                os.link(temporary, payload_path)
                payload_linked = True
                with metadata_path.open("x", encoding="utf-8") as metadata_file:
                    json.dump(
                        {
                            "original_filename": artifact.original_filename,
                            "suffix": artifact.suffix,
                            "media_type": artifact.media_type,
                            "byte_size": artifact.byte_size,
                            "sha256": artifact.sha256,
                            "stored_at": artifact.stored_at.isoformat(),
                        },
                        metadata_file,
                        sort_keys=True,
                    )
                    metadata_file.flush()
                    os.fsync(metadata_file.fileno())
            except FileExistsError as exc:
                if payload_linked and payload_path.is_file():
                    payload_path.unlink()
                raise ValueError("source already has an original artifact") from exc
            except Exception:
                if payload_linked and payload_path.is_file():
                    payload_path.unlink()
                raise
            return artifact
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def retrieve(self, artifact: OriginalArtifact) -> bytes:
        return (self._directory(artifact.workspace_id, artifact.source_id) / "original").read_bytes()
