"""Read-only OpenRouter usage telemetry adapter."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from knowledge_platform.application.provider_usage import ProviderUsageUnavailable

logger = logging.getLogger(__name__)


class OpenRouterUsageAdapter:
    """Normalize the current-key usage endpoint without returning key metadata."""

    def __init__(
        self,
        *,
        api_key: str | Callable[[], str],
        endpoint: str = "https://openrouter.ai/api/v1/key",
        client: Any = None,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._client = client

    def _credential(self) -> str:
        try:
            value = self._api_key() if callable(self._api_key) else self._api_key
        except Exception:
            raise ProviderUsageUnavailable("credential") from None
        normalized = value.strip()
        if not normalized:
            raise ProviderUsageUnavailable("credential")
        return normalized

    def _http_client(self) -> Any:
        if self._client is None:
            httpx = __import__("httpx")
            self._client = httpx.Client()
        return self._client

    @staticmethod
    def _number(payload: dict[str, object], key: str) -> float | None:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)

    def summary(self) -> dict[str, object]:
        credential = self._credential()
        try:
            response = self._http_client().get(
                self._endpoint,
                headers={"Authorization": f"Bearer {credential}"},
                timeout=15,
            )
        except Exception:
            logger.warning("provider_usage_read_failed category=connection provider=openrouter")
            raise ProviderUsageUnavailable("connection") from None
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or status_code >= 400:
            safe_status = status_code if isinstance(status_code, int) else None
            logger.warning(
                "provider_usage_read_failed category=http_status provider=openrouter status=%s",
                safe_status if safe_status is not None else "unknown",
            )
            raise ProviderUsageUnavailable("http_status") from None
        try:
            body = response.json()
            data = body["data"]
            if not isinstance(data, dict):
                raise TypeError
        except Exception:
            logger.warning("provider_usage_read_failed category=schema provider=openrouter")
            raise ProviderUsageUnavailable("schema") from None
        return {
            "provider": "openrouter",
            "retrieved_at": datetime.now(UTC),
            "currency": "USD",
            "usage": self._number(data, "usage"),
            "usage_daily": self._number(data, "usage_daily"),
            "usage_weekly": self._number(data, "usage_weekly"),
            "usage_monthly": self._number(data, "usage_monthly"),
            "limit": self._number(data, "limit"),
            "limit_remaining": self._number(data, "limit_remaining"),
            "limit_reset": data.get("limit_reset")
            if data.get("limit_reset") in {"daily", "weekly", "monthly"}
            else None,
            "is_free_tier": data.get("is_free_tier")
            if isinstance(data.get("is_free_tier"), bool)
            else None,
            "expires_at": data.get("expires_at")
            if isinstance(data.get("expires_at"), str)
            else None,
        }
