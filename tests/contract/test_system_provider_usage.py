"""Focused contracts for the authoritative OpenRouter usage surface."""

from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from knowledge_platform.application.provider_usage import (
    ProviderUsageService,
    ProviderUsageSummary,
    ProviderUsageUnavailable,
)
from knowledge_platform.infrastructure.provider_usage import OpenRouterUsageAdapter
from knowledge_platform.modules.access_control.domain import Permission

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class _Response:
    status_code = 200

    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def json(self) -> dict[str, object]:
        return {"data": self._data}


class _Client:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, endpoint: str, **kwargs: Any) -> _Response:
        self.calls.append((endpoint, kwargs))
        return _Response(self._data)


def test_current_key_fields_are_forwarded_without_local_cost_derivation() -> None:
    provider_data: dict[str, object] = {
        "usage": 4.125678,
        "usage_daily": 0.125678,
        "usage_weekly": 1.25,
        "usage_monthly": 3.5,
        "limit": 20,
        "limit_remaining": 15.874322,
        "limit_reset": "monthly",
        "is_free_tier": False,
        "label": "must-not-leak",
    }
    client = _Client(provider_data)

    result = OpenRouterUsageAdapter(
        api_key="secret-value-must-not-leak",
        credential_reference="OPENROUTER_API_KEY",
        client=client,
    ).summary()

    assert client.calls[0][0] == "https://openrouter.ai/api/v1/key"
    assert client.calls[0][1]["timeout"] == 15
    for field in (
        "usage",
        "usage_daily",
        "usage_weekly",
        "usage_monthly",
        "limit",
        "limit_remaining",
        "limit_reset",
        "is_free_tier",
    ):
        assert getattr(result, field) == provider_data[field]
    assert isinstance(result, ProviderUsageSummary)
    assert result.currency == "USD"
    assert result.source.provider == "openrouter"
    assert result.source.kind == "provider_key"
    assert result.source.credential_reference == "OPENROUTER_API_KEY"
    serialized = repr(asdict(result))
    assert "label" not in serialized
    assert "secret-value-must-not-leak" not in serialized


def test_optional_limit_fields_remain_unavailable_instead_of_becoming_zero() -> None:
    result = OpenRouterUsageAdapter(
        api_key="test-only",
        credential_reference="OPENROUTER_API_KEY",
        client=_Client({"usage": 0, "limit_reset": "unsupported"}),
    ).summary()

    assert result.usage == 0
    assert result.limit is None
    assert result.limit_remaining is None
    assert result.limit_reset is None
    assert result.is_free_tier is None


def test_missing_credential_is_classified_before_any_remote_request() -> None:
    client = _Client({})

    def missing_credential() -> str:
        raise RuntimeError("not configured")

    try:
        OpenRouterUsageAdapter(
            api_key=missing_credential,
            credential_reference="OPENROUTER_API_KEY",
            client=client,
        ).summary()
    except ProviderUsageUnavailable as exc:
        assert exc.category == "credential"
    else:
        raise AssertionError("missing provider credential must fail closed")
    assert client.calls == []


def test_usage_service_requires_system_usage_read_and_returns_typed_summary() -> None:
    class Access:
        checked: tuple[UUID, Permission] | None = None

        def require_system(self, actor: UUID, permission: Permission) -> None:
            self.checked = (actor, permission)

    actor = UUID("00000000-0000-0000-0000-000000000123")
    access = Access()
    service = ProviderUsageService(
        access=access,  # type: ignore[arg-type]
        telemetry=OpenRouterUsageAdapter(
            api_key="test-only",
            credential_reference="OPENROUTER_API_KEY",
            client=_Client({"usage": 1.25}),
        ),
    )

    result = service.summary(actor)

    assert access.checked == (actor, Permission.USAGE_READ)
    assert isinstance(result, ProviderUsageSummary)
    assert result.usage == 1.25


def test_usage_delivery_exposes_only_safe_unavailable_categories() -> None:
    delivery = read("src/knowledge_platform/delivery/provider_usage_api.py")

    assert '"provider usage credential unavailable"' in delivery
    assert '"provider usage telemetry unavailable"' in delivery
    assert "exc.category == \"credential\"" in delivery
    assert "asdict(service.summary" in delivery
    assert "Authorization" not in delivery


def test_usage_ui_has_precise_spend_and_optional_limit_semantics() -> None:
    pages = read("frontend/system/controls-pages.js")
    usage = pages.split("export function usagePage", 1)[1].split(
        "function providerEditor", 1
    )[0]

    assert 'getJSON("/api/system/usage/provider")' in usage
    assert "الإنفاق الإجمالي للمفتاح" in usage
    assert 'getJSON("/api/system/providers/runtime")' in usage
    assert ".catch(() => {})" in usage
    assert "Promise.all" not in usage
    assert "استخدام المزود" in usage
    assert "مصدر بيانات الاستخدام" in usage
    assert "حدود المفتاح" in usage
    assert "سياق التشغيل الحالي" in usage
    assert "نموذج التوليد" in usage
    assert "نموذج التمثيلات المتجهية" in usage
    assert "مرجع اعتماد القياس" in usage
    assert "بيانات الاستخدام المعروضة صادرة من المزود على مستوى مفتاح القياس" in usage
    assert "ولا يعني ذلك أن الإنفاق التاريخي منسوب إليها" in usage
    assert "maximumFractionDigits: 20" in pages
    assert "money(value, data.currency)" in usage
    assert "providerDisplayName(sourceProvider, providers)" in usage
    assert "US$" not in usage
    assert "OpenRouter" not in usage
    assert 'style: "currency"' not in pages
    assert "typeof data.limit === \"number\"" in usage
    assert "typeof data.limit_remaining === \"number\"" in usage
    assert "if (limitFacts.length)" in usage
    assert "وتيرة إعادة ضبط الحد" in usage
    assert "formatDate(data.limit_reset)" not in usage
    assert "المفتاح ضمن الفئة المجانية" in usage
    assert "الخطة المجانية" not in usage
    assert "لا توجد بيانات استخدام للفترة المحددة." in usage


def test_usage_path_is_separate_from_execution_and_internal_events() -> None:
    adapter = read(
        "src/knowledge_platform/infrastructure/provider_usage/openrouter.py"
    )
    pages = read("frontend/system/controls-pages.js")
    usage = pages.split("export function usagePage", 1)[1].split(
        "function providerEditor", 1
    )[0]

    assert "usage_events" not in adapter
    assert "usage_events" not in usage
    assert "/api/v1/activity" not in adapter
    assert "/chat/completions" not in adapter
    assert "/embeddings" not in adapter
    assert "vector" not in adapter.lower()
    assert "/chat/completions" not in usage
    assert "/embeddings" not in usage
