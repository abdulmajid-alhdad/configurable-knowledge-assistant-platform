"""OpenRouter model catalogue discovery without model execution."""

import logging
from collections.abc import Callable
from typing import Any

from knowledge_platform.application.provider_catalogue import (
    ModelCatalogueEntry,
    ProviderModelCatalogueError,
)
from knowledge_platform.application.provider_configuration import ModelCapability

logger = logging.getLogger(__name__)


class OpenRouterModelCatalogueAdapter:
    """Normalize OpenRouter's capability-specific authoritative catalogues."""

    _GENERATION_ENDPOINT = "https://openrouter.ai/api/v1/models"
    _EMBEDDING_ENDPOINT = "https://openrouter.ai/api/v1/embeddings/models"

    def __init__(
        self,
        *,
        api_key: str | Callable[[ModelCapability], str],
        client: Any = None,
    ) -> None:
        self._api_key = api_key
        self._client = client

    def _credential(self, capability: ModelCapability) -> str:
        try:
            value = self._api_key(capability) if callable(self._api_key) else self._api_key
        except Exception:
            raise ProviderModelCatalogueError("CATALOGUE_CREDENTIAL_UNAVAILABLE") from None
        normalized = value.strip()
        if not normalized:
            raise ProviderModelCatalogueError("CATALOGUE_CREDENTIAL_UNAVAILABLE")
        return normalized

    def _http_client(self) -> Any:
        if self._client is None:
            httpx = __import__("httpx")
            self._client = httpx.Client()
        return self._client

    @staticmethod
    def _modalities(value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
        return tuple(item.strip() for item in value)

    @staticmethod
    def _context_length(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
        return value

    @staticmethod
    def _optional_context_length(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return value

    @classmethod
    def _entry(
        cls,
        raw: object,
        capability: ModelCapability,
    ) -> ModelCatalogueEntry | None:
        if not isinstance(raw, dict):
            raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
        model_id = raw.get("id")
        display_name = raw.get("name")
        architecture = raw.get("architecture")
        supported_parameters = raw.get("supported_parameters")
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or model_id != model_id.strip()
            or len(model_id) > 240
            or not isinstance(display_name, str)
            or not display_name.strip()
            or not isinstance(architecture, dict)
            or not isinstance(supported_parameters, list)
            or any(not isinstance(item, str) for item in supported_parameters)
        ):
            raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
        inputs = cls._modalities(architecture.get("input_modalities"))
        outputs = cls._modalities(architecture.get("output_modalities"))
        if capability is ModelCapability.GENERATION:
            compatible = (
                "text" in inputs
                and "text" in outputs
                and "response_format" in supported_parameters
            )
        else:
            compatible = "text" in inputs and "embeddings" in outputs
        if not compatible:
            return None
        description = raw.get("description")
        if (
            description is not None
            and not isinstance(description, str)
            and capability is ModelCapability.EMBEDDING
        ):
            raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
        normalized_description = (
            description.strip()[:1000] if isinstance(description, str) else None
        )
        if not normalized_description:
            normalized_description = None
        context_length = (
            cls._optional_context_length(raw.get("context_length"))
            if capability is ModelCapability.GENERATION
            else cls._context_length(raw.get("context_length"))
        )
        return ModelCatalogueEntry(
            provider="openrouter",
            model_id=model_id,
            display_name=display_name.strip(),
            capability=capability,
            context_length=context_length,
            input_modalities=inputs,
            output_modalities=outputs,
            embedding_dimensions=None,
            description=normalized_description,
        )

    def models(
        self, capability: ModelCapability
    ) -> tuple[ModelCatalogueEntry, ...]:
        endpoint = (
            self._EMBEDDING_ENDPOINT
            if capability is ModelCapability.EMBEDDING
            else self._GENERATION_ENDPOINT
        )
        parameters = (
            None
            if capability is ModelCapability.EMBEDDING
            else {
                "output_modalities": "text",
                "supported_parameters": "response_format",
            }
        )
        credential = self._credential(capability)
        try:
            response = self._http_client().get(
                endpoint,
                headers={"Authorization": f"Bearer {credential}"},
                params=parameters,
                timeout=15,
            )
        except Exception:
            logger.warning(
                "provider_model_catalogue_failed category=connection provider=openrouter"
            )
            raise ProviderModelCatalogueError("CATALOGUE_PROVIDER_UNAVAILABLE") from None
        status_code = getattr(response, "status_code", None)
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 200 <= status_code < 300
        ):
            logger.warning(
                "provider_model_catalogue_failed category=http_status provider=openrouter "
                "status=%s",
                status_code if isinstance(status_code, int) else "unknown",
            )
            raise ProviderModelCatalogueError("CATALOGUE_PROVIDER_UNAVAILABLE")
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError
            raw_models = body.get("data")
            if not isinstance(raw_models, list):
                raise TypeError
            normalized_entries: list[ModelCatalogueEntry] = []
            for raw in raw_models:
                try:
                    entry = self._entry(raw, capability)
                except ProviderModelCatalogueError:
                    if capability is ModelCapability.EMBEDDING:
                        raise
                    continue
                if entry is not None:
                    normalized_entries.append(entry)
            entries = tuple(normalized_entries)
            if capability is ModelCapability.GENERATION and not entries:
                raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
            identifiers = tuple(entry.model_id for entry in entries)
            if len(set(identifiers)) != len(identifiers):
                raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
        except ProviderModelCatalogueError:
            logger.warning(
                "provider_model_catalogue_failed category=schema provider=openrouter"
            )
            raise
        except Exception:
            logger.warning(
                "provider_model_catalogue_failed category=schema provider=openrouter"
            )
            raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID") from None
        return tuple(sorted(entries, key=lambda entry: entry.display_name.casefold()))
