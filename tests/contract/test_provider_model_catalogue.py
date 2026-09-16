"""Focused contracts for backend-mediated provider model discovery."""

import logging
from pathlib import Path
from uuid import UUID

import pytest

from knowledge_platform.application.access_control import AccessDenied
from knowledge_platform.application.provider_catalogue import (
    ModelCatalogueEntry,
    ProviderModelCatalogueError,
    ProviderModelCatalogueService,
)
from knowledge_platform.application.provider_configuration import (
    ModelCapability,
    ProviderDefinition,
)
from knowledge_platform.infrastructure.provider_configuration import (
    OpenRouterModelCatalogueAdapter,
)
from knowledge_platform.modules.access_control.domain import Permission

ROOT = Path(__file__).resolve().parents[2]
ACTOR = UUID("00000000-0000-0000-0000-000000000123")


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def model(
    model_id: str,
    *,
    outputs: list[str],
    supported_parameters: list[str],
) -> dict[str, object]:
    return {
        "id": model_id,
        "name": f"Display {model_id}",
        "description": "Provider-returned description",
        "context_length": 8192,
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": outputs,
        },
        "supported_parameters": supported_parameters,
    }


class Response:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload


class Client:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, endpoint: str, **kwargs: object) -> Response:
        self.calls.append((endpoint, kwargs))
        return self.response


def test_openrouter_generation_catalogue_uses_authoritative_execution_metadata() -> None:
    client = Client(
        Response(
            {
                "data": [
                    {
                        **model(
                            "vendor/Canonical:Exact",
                            outputs=["text"],
                            supported_parameters=[
                                "response_format",
                                "temperature",
                            ],
                        ),
                        "description": None,
                        "architecture": {
                            "input_modalities": ["text"],
                            "output_modalities": ["text"],
                            "instruct_type": None,
                            "tokenizer": "Other",
                        },
                        "pricing": {
                            "prompt": "0.0000001",
                            "completion": "0.0000002",
                        },
                        "top_provider": {
                            "context_length": 8192,
                            "max_completion_tokens": None,
                        },
                        "unrelated_provider_field": None,
                    },
                    {
                        "id": "vendor/malformed-among-valid-models",
                        "name": "Malformed",
                        "architecture": {
                            "input_modalities": None,
                            "output_modalities": ["text"],
                        },
                        "supported_parameters": ["response_format"],
                    },
                    model(
                        "vendor/no-json-mode",
                        outputs=["text"],
                        supported_parameters=["temperature"],
                    ),
                    model(
                        "vendor/embedding",
                        outputs=["embeddings"],
                        supported_parameters=[],
                    ),
                ],
                "links": {
                    "next": None,
                    "previous": None,
                },
                "total_count": 4,
            }
        )
    )

    entries = OpenRouterModelCatalogueAdapter(
        api_key="test-catalogue-key", client=client
    ).models(ModelCapability.GENERATION)

    assert tuple(entry.model_id for entry in entries) == (
        "vendor/Canonical:Exact",
    )
    assert entries[0].capability is ModelCapability.GENERATION
    assert entries[0].input_modalities == ("text",)
    assert entries[0].output_modalities == ("text",)
    assert entries[0].description is None
    assert client.calls == [
        (
            "https://openrouter.ai/api/v1/models",
            {
                "headers": {"Authorization": "Bearer test-catalogue-key"},
                "params": {
                    "output_modalities": "text",
                    "supported_parameters": "response_format",
                },
                "timeout": 15,
            },
        )
    ]


def test_generation_catalogue_omits_malformed_optional_metadata() -> None:
    raw = model(
        "vendor/optional-metadata",
        outputs=["text"],
        supported_parameters=["response_format"],
    )
    raw["description"] = {"unexpected": "shape"}
    raw["context_length"] = "unknown"

    entries = OpenRouterModelCatalogueAdapter(
        api_key="test-catalogue-key",
        client=Client(Response({"data": [raw], "total_count": 1})),
    ).models(ModelCapability.GENERATION)

    assert len(entries) == 1
    assert entries[0].model_id == "vendor/optional-metadata"
    assert entries[0].description is None
    assert entries[0].context_length is None


def test_generation_catalogue_fails_when_no_compatible_models_remain() -> None:
    incompatible = model(
        "vendor/no-structured-output",
        outputs=["text"],
        supported_parameters=["temperature"],
    )

    with pytest.raises(
        ProviderModelCatalogueError, match="CATALOGUE_RESPONSE_INVALID"
    ):
        OpenRouterModelCatalogueAdapter(
            api_key="test-catalogue-key",
            client=Client(
                Response(
                    {
                        "data": [incompatible, {"id": None}],
                        "links": {},
                        "total_count": 2,
                    }
                )
            ),
        ).models(ModelCapability.GENERATION)


def test_openrouter_embedding_catalogue_uses_dedicated_authoritative_endpoint() -> None:
    credential_capabilities: list[ModelCapability] = []

    def credential(capability: ModelCapability) -> str:
        credential_capabilities.append(capability)
        return "test-catalogue-key"

    client = Client(
        Response(
            {
                "data": [
                    model(
                        "baai/bge-m3",
                        outputs=["embeddings"],
                        supported_parameters=[],
                    ),
                    model(
                        "vendor/text",
                        outputs=["text"],
                        supported_parameters=["response_format"],
                    ),
                ]
            }
        )
    )

    entries = OpenRouterModelCatalogueAdapter(
        api_key=credential, client=client
    ).models(ModelCapability.EMBEDDING)

    assert tuple(entry.model_id for entry in entries) == ("baai/bge-m3",)
    assert entries[0].embedding_dimensions is None
    assert client.calls[0][0] == "https://openrouter.ai/api/v1/embeddings/models"
    assert client.calls[0][1]["params"] is None
    assert credential_capabilities == [ModelCapability.EMBEDDING]


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (Response({"data": "not-a-list"}), "CATALOGUE_RESPONSE_INVALID"),
        (Response({"data": [{}]}), "CATALOGUE_RESPONSE_INVALID"),
        (Response({}, status_code=503), "CATALOGUE_PROVIDER_UNAVAILABLE"),
    ],
)
def test_openrouter_catalogue_fails_safely_for_provider_or_schema_errors(
    response: Response,
    expected: str,
) -> None:
    with pytest.raises(ProviderModelCatalogueError, match=expected):
        OpenRouterModelCatalogueAdapter(
            api_key="test-catalogue-key", client=Client(response)
        ).models(ModelCapability.GENERATION)


def test_openrouter_catalogue_transport_failure_never_leaks_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingClient:
        @staticmethod
        def get(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("Authorization: Bearer private-catalogue-key")

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(
            ProviderModelCatalogueError, match="CATALOGUE_PROVIDER_UNAVAILABLE"
        ) as caught,
    ):
        OpenRouterModelCatalogueAdapter(
            api_key="private-catalogue-key", client=FailingClient()
        ).models(ModelCapability.GENERATION)

    assert "private-catalogue-key" not in str(caught.value)
    assert "private-catalogue-key" not in caplog.text
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), ValueError("bad json")])
def test_openrouter_catalogue_timeout_and_malformed_json_fail_safely(
    failure: Exception,
) -> None:
    class FailingClient:
        @staticmethod
        def get(*_args: object, **_kwargs: object) -> Response:
            if isinstance(failure, TimeoutError):
                raise failure

            class InvalidJsonResponse(Response):
                def json(self) -> object:
                    raise failure

            return InvalidJsonResponse({})

    with pytest.raises(ProviderModelCatalogueError) as caught:
        OpenRouterModelCatalogueAdapter(
            api_key="test-catalogue-key", client=FailingClient()
        ).models(ModelCapability.GENERATION)

    assert str(caught.value) in {
        "CATALOGUE_PROVIDER_UNAVAILABLE",
        "CATALOGUE_RESPONSE_INVALID",
    }


def test_catalogue_service_requires_system_read_and_dispatches_by_provider() -> None:
    class Access:
        checked: tuple[UUID, Permission] | None = None

        def require_system(self, actor: UUID, permission: Permission) -> None:
            self.checked = (actor, permission)

    class Store:
        @staticmethod
        def providers() -> tuple[ProviderDefinition, ...]:
            return (
                ProviderDefinition("openrouter", "OpenRouter", "multi", None),
                ProviderDefinition("future", "Future", "generation", None),
            )

    class Catalogue:
        @staticmethod
        def models(
            capability: ModelCapability,
        ) -> tuple[ModelCatalogueEntry, ...]:
            return (
                ModelCatalogueEntry(
                    provider="openrouter",
                    model_id="vendor/model",
                    display_name="Model",
                    capability=capability,
                    context_length=None,
                    input_modalities=("text",),
                    output_modalities=("text",),
                ),
            )

    access = Access()
    service = ProviderModelCatalogueService(
        access=access,  # type: ignore[arg-type]
        providers=Store(),  # type: ignore[arg-type]
        catalogues={"openrouter": Catalogue()},
    )

    result = service.models(ACTOR, "openrouter", ModelCapability.GENERATION)

    assert access.checked == (ACTOR, Permission.PROVIDERS_READ)
    assert result["provider"] == "openrouter"
    assert result["models"][0]["model_id"] == "vendor/model"  # type: ignore[index]
    assert "credential" not in repr(result).lower()
    with pytest.raises(
        ProviderModelCatalogueError, match="CATALOGUE_INTEGRATION_UNAVAILABLE"
    ):
        service.models(ACTOR, "future", ModelCapability.GENERATION)
    with pytest.raises(ProviderModelCatalogueError, match="UNSUPPORTED_PROVIDER"):
        service.models(ACTOR, "unknown", ModelCapability.GENERATION)


def test_catalogue_service_fails_closed_before_provider_dispatch() -> None:
    class DenyingAccess:
        @staticmethod
        def require_system(_actor: UUID, permission: Permission) -> None:
            assert permission is Permission.PROVIDERS_READ
            raise AccessDenied("private authority detail")

    class Store:
        @staticmethod
        def providers() -> tuple[ProviderDefinition, ...]:
            raise AssertionError("provider registry must not be read after denial")

    service = ProviderModelCatalogueService(
        access=DenyingAccess(),  # type: ignore[arg-type]
        providers=Store(),  # type: ignore[arg-type]
        catalogues={},
    )

    with pytest.raises(AccessDenied):
        service.models(ACTOR, "openrouter", ModelCapability.GENERATION)


def test_catalogue_delivery_is_read_only_provider_neutral_and_non_executing() -> None:
    delivery = read("src/knowledge_platform/delivery/provider_configuration_api.py")
    security = read("src/knowledge_platform/delivery/security.py")
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")
    adapter = read(
        "src/knowledge_platform/infrastructure/provider_configuration/"
        "openrouter_catalogue.py"
    )

    assert '@router.get("/{provider}/models")' in delivery
    assert "capability: ModelCapability" in delivery
    assert 'r"^/api/system/providers/[^/]+/models$"' in security
    assert "Permission.PROVIDERS_READ" in security
    assert "EnvironmentCredentialResolver" in bootstrap
    assert '"Authorization": f"Bearer {credential}"' in adapter
    assert "chat/completions" not in adapter
    assert ".post(" not in adapter
    assert "vector" not in adapter.lower()
