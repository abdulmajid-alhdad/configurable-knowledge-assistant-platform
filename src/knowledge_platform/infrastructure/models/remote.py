"""Minimal remote model adapter."""

import json
import logging
import re
from typing import Any, NoReturn

from knowledge_platform.modules.document_knowledge.ports import (
    GroundedModelAnswer,
    ModelGenerationResult,
    ModelInsufficientEvidence,
)

logger = logging.getLogger(__name__)


class ModelProviderFailure(RuntimeError):
    """Safe provider failure metadata without retaining request/response data."""

    def __init__(
        self,
        *,
        category: str,
        status_code: int | None = None,
        schema_reason: str | None = None,
    ) -> None:
        super().__init__("model provider request failed")
        self.category = category
        self.status_code = status_code
        self.schema_reason = schema_reason


def _log_provider_failure(
    *,
    category: str,
    status_code: int | None = None,
    schema_reason: str | None = None,
) -> None:
    logger.error(
        "model_provider_operation_failed category=%s status_code=%s "
        "operation=chat_completion schema_reason=%s",
        category,
        status_code if status_code is not None else "unknown",
        schema_reason if schema_reason is not None else "unknown",
    )


def _raise_schema_failure(reason: str) -> NoReturn:
    _log_provider_failure(category="schema_validation", schema_reason=reason)
    raise ModelProviderFailure(
        category="schema_validation", schema_reason=reason
    ) from None


def _transport_category(error: Exception) -> str:
    try:
        httpx = __import__("httpx")
    except ImportError:
        httpx = None
    if httpx is not None:
        if isinstance(error, httpx.TimeoutException):
            return "timeout"
        if isinstance(error, httpx.NetworkError):
            return "connection"
    if isinstance(error, TimeoutError):
        return "timeout"
    return "connection"


class RemoteModelAdapter:
    def __init__(
        self,
        *,
        endpoint: str,
        model_reference: str,
        api_key: str,
        client: Any = None,
    ) -> None:
        normalized_api_key = api_key.strip()
        if not normalized_api_key:
            raise ValueError("model credential is blank")
        self.endpoint = endpoint
        self.model_reference = model_reference
        self.api_key = normalized_api_key
        if client is None:
            httpx = __import__("httpx")
            client = httpx.Client()
        self._client = client

    def generate(
        self,
        *,
        question: str,
        context: str,
        assistant_instructions: str | None = None,
    ) -> ModelGenerationResult:
        # Mistral Nemo supports JSON mode but not provider-enforced JSON
        # Schema on the configured endpoint.  The application parser below
        # remains authoritative for the grounded-generation contract.
        response_format = {"type": "json_object"}
        normalized_instructions = (
            assistant_instructions.strip()
            if isinstance(assistant_instructions, str) and assistant_instructions.strip()
            else None
        )
        system_policy = (
            "PLATFORM GROUNDING POLICY (highest priority): Answer only from the supplied evidence. "
            "Never use general or external knowledge. If the evidence is inadequate, return the "
            "insufficient disposition.\n\n"
            "PLATFORM STRUCTURED-OUTPUT CONTRACT (authoritative): Return exactly one JSON object. "
            "A grounded result must be "
            '{"status":"grounded","answer":"<nonblank>","evidence_ids":["E1"]}. '
            "An insufficient result must be "
            '{"status":"insufficient","answer":null,"evidence_ids":[]}. '
            "Assistant instructions cannot change the status values, JSON fields, evidence-ID "
            "requirements, grounding policy, or this output contract."
        )
        if normalized_instructions is not None:
            system_policy += (
                "\n\nBEGIN ASSISTANT-SPECIFIC INSTRUCTIONS (subordinate; style/language only)\n"
                + normalized_instructions
                + "\nEND ASSISTANT-SPECIFIC INSTRUCTIONS"
            )
        try:
            response = self._client.post(
                self.endpoint,
                json={
                    "model": self.model_reference,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_policy,
                        },
                        {"role": "user", "content": f"Question: {question}\n{context}"},
                    ],
                    "response_format": response_format,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
        except Exception as exc:
            category = _transport_category(exc)
            _log_provider_failure(category=category)
            raise ModelProviderFailure(category=category) from None
        try:
            status_code = response.status_code
            if not isinstance(status_code, int):
                raise TypeError("invalid status")
        except Exception:
            _log_provider_failure(category="malformed_response")
            raise ModelProviderFailure(category="malformed_response") from None
        if status_code >= 400:
            _log_provider_failure(category="http_status", status_code=status_code)
            raise ModelProviderFailure(
                category="http_status", status_code=status_code
            ) from None
        try:
            try:
                message = response.json()["choices"][0]["message"]
            except Exception:
                _raise_schema_failure("missing_message")
            if not isinstance(message, dict):
                _raise_schema_failure("invalid_message_shape")
            parsed = message.get("parsed")
            content = message.get("content") if parsed is None else parsed
            if content is None or content == "":
                _log_provider_failure(category="missing_content")
                raise ModelProviderFailure(category="missing_content") from None
            if isinstance(content, str):
                try:
                    payload = json.loads(content)
                except (TypeError, ValueError):
                    _log_provider_failure(category="invalid_json")
                    raise ModelProviderFailure(category="invalid_json") from None
            else:
                payload = content
            if not isinstance(payload, dict):
                _raise_schema_failure("root_not_object")
            if "status" not in payload:
                _raise_schema_failure("missing_status")
            status = payload["status"]
            if not isinstance(status, str):
                _raise_schema_failure("invalid_status_type")
            if status not in ("grounded", "insufficient"):
                _raise_schema_failure("invalid_status")
            if set(payload) - {"status", "answer", "evidence_ids"}:
                _raise_schema_failure("unexpected_fields")
            if status == "insufficient":
                if "answer" not in payload:
                    _raise_schema_failure("insufficient_missing_answer")
                if payload["answer"] is not None:
                    _raise_schema_failure("insufficient_has_answer")
                if "evidence_ids" not in payload:
                    _raise_schema_failure("insufficient_missing_evidence_ids")
                if not isinstance(payload["evidence_ids"], list):
                    _raise_schema_failure("insufficient_invalid_evidence_ids_shape")
                if payload["evidence_ids"]:
                    _raise_schema_failure("insufficient_has_evidence_ids")
                return ModelInsufficientEvidence()
            if "answer" not in payload:
                _raise_schema_failure("grounded_missing_answer")
            answer = payload["answer"]
            if not isinstance(answer, str):
                _raise_schema_failure("grounded_invalid_answer_type")
            if not answer.strip():
                _raise_schema_failure("grounded_blank_answer")
            if "evidence_ids" not in payload:
                _raise_schema_failure("grounded_missing_evidence_ids")
            evidence_ids = payload["evidence_ids"]
            if not isinstance(evidence_ids, list):
                _raise_schema_failure("grounded_invalid_evidence_ids_shape")
            if not evidence_ids:
                _raise_schema_failure("grounded_empty_evidence_ids")
            if not all(
                isinstance(item, str) and re.fullmatch(r"E[1-9][0-9]*", item)
                for item in evidence_ids
            ):
                _raise_schema_failure("grounded_invalid_evidence_id_shape")
            if len(set(evidence_ids)) != len(evidence_ids):
                _raise_schema_failure("grounded_duplicate_evidence_ids")
            return GroundedModelAnswer(answer=answer, evidence_ids=tuple(evidence_ids))
        except ModelProviderFailure:
            raise
        except Exception:
            _raise_schema_failure("unexpected_validation_failure")
