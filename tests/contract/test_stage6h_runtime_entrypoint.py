"""Contracts for the production ASGI composition boundary."""
from pathlib import Path


def test_production_entrypoint_uses_runtime_composition_without_demo_fallback() -> None:
    source = Path("src/knowledge_platform/bootstrap/asgi.py").read_text(encoding="utf-8")
    assert "create_runtime()" in source
    assert "create_app(runtime=create_runtime())" in source
    assert "create_app()" not in source


def test_docker_targets_production_entrypoint() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "knowledge_platform.bootstrap.asgi:app" in dockerfile
    assert "knowledge_platform.delivery.app:app" not in dockerfile
