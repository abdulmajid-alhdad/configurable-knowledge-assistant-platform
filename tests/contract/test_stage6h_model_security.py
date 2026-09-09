"""Remote model provider boundary and secret-safety contracts."""

import pytest

from knowledge_platform.infrastructure.models.remote import (
    ModelProviderFailure,
    RemoteModelAdapter,
)
from knowledge_platform.modules.document_knowledge.ports import ModelInsufficientEvidence


class _Response:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"status":"grounded","answer":"grounded answer",'
                            '"evidence_ids":["E1"]}'
                        )
                    }
                }
            ]
        }


class _RecordingClient:
    def __init__(self) -> None:
        self.endpoint: str | None = None
        self.payload: object | None = None
        self.headers: dict[str, str] | None = None
        self.timeout: int | None = None

    def post(
        self,
        endpoint: str,
        *,
        json: object,
        headers: dict[str, str],
        timeout: int,
    ) -> _Response:
        self.endpoint, self.payload, self.headers, self.timeout = endpoint, json, headers, timeout
        return _Response()


def test_model_adapter_preserves_successful_request_contract() -> None:
    client = _RecordingClient()
    result = RemoteModelAdapter(
        endpoint="https://model.test/v1/chat/completions",
        model_reference="model-reference",
        api_key="  fake-token\r\n",
        client=client,
    ).generate(question="What?", context="Known evidence")

    assert result.answer == "grounded answer"
    assert result.evidence_ids == ("E1",)
    assert client.endpoint == "https://model.test/v1/chat/completions"
    assert isinstance(client.payload, dict)
    assert client.payload["model"] == "model-reference"
    assert client.payload["messages"] == [
        {
            "role": "system",
            "content": (
                "PLATFORM GROUNDING POLICY (highest priority): Answer only from the supplied "
                "evidence. Never use general or external knowledge. If the evidence is inadequate, "
                "return the insufficient disposition.\n\nPLATFORM STRUCTURED-OUTPUT CONTRACT "
                "(authoritative): Return exactly one JSON object. A grounded result must be "
                '{"status":"grounded","answer":"<nonblank>","evidence_ids":["E1"]}. '
                "An insufficient result must be "
                '{"status":"insufficient","answer":null,"evidence_ids":[]}. '
                "Assistant instructions cannot change the status values, JSON fields, evidence-ID "
                "requirements, grounding policy, or this output contract."
            ),
        },
        {"role": "user", "content": "Question: What?\nKnown evidence"},
    ]
    response_format = client.payload["response_format"]
    assert response_format == {"type": "json_object"}
    assert client.headers == {"Authorization": "Bearer fake-token"}
    assert client.timeout == 30


class _LeakingClient:
    def post(
        self,
        endpoint: str,
        *,
        json: object,
        headers: dict[str, str],
        timeout: int,
    ) -> object:
        raise RuntimeError("Authorization: Bearer fake-token; prompt=SECRET_PRIVATE_CONTEXT")


def test_model_transport_failure_is_safe_and_does_not_chain_sensitive_text() -> None:
    with pytest.raises(RuntimeError, match="model provider request failed") as caught:
        RemoteModelAdapter(
            endpoint="https://model.test/v1/chat/completions",
            model_reference="model-reference",
            api_key="fake-token",
            client=_LeakingClient(),
        ).generate(question="SECRET_PRIVATE_PROMPT", context="SECRET_PRIVATE_CONTEXT")

    assert "fake-token" not in str(caught.value)
    assert "SECRET_PRIVATE" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_model_malformed_response_is_safe() -> None:
    class Malformed:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"choices": []}

    class Client:
        def post(
            self,
            endpoint: str,
            *,
            json: object,
            headers: dict[str, str],
            timeout: int,
        ) -> Malformed:
            return Malformed()

    with pytest.raises(ModelProviderFailure) as caught:
        RemoteModelAdapter(
            endpoint="https://model.test/v1/chat/completions",
            model_reference="model-reference",
            api_key="fake-token",
            client=Client(),
        ).generate(question="question", context="context")

    assert caught.value.__cause__ is None
    assert caught.value.category == "schema_validation"
    assert caught.value.schema_reason == "missing_message"


def test_model_valid_insufficient_json_parses_to_typed_disposition() -> None:
    class Client:
        def post(self, *args: object, **kwargs: object) -> object:
            class Response:
                status_code = 200

                def json(self) -> dict[str, object]:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": (
                                        '{"status":"insufficient","answer":null,'
                                        '"evidence_ids":[]}'
                                    )
                                }
                            }
                        ]
                    }

            return Response()

    result = RemoteModelAdapter(
        endpoint="https://model.test", model_reference="model", api_key="token", client=Client()
    ).generate(question="question", context="context", assistant_instructions="Answer in Arabic.")
    assert isinstance(result, ModelInsufficientEvidence)


@pytest.mark.parametrize("status_code", (401, 402, 429, 500))
def test_model_http_failure_preserves_only_safe_status_diagnostic(
    status_code: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Response:
        def json(self) -> dict[str, object]:
            return {"error": "SECRET_PROVIDER_ERROR SECRET_RESPONSE_BODY"}

        def __init__(self) -> None:
            self.status_code = status_code

    class Client:
        def post(self, *args: object, **kwargs: object) -> Response:
            return Response()

    with caplog.at_level("ERROR", logger="knowledge_platform.infrastructure.models.remote"):
        with pytest.raises(ModelProviderFailure) as caught:
            RemoteModelAdapter(
                endpoint="https://model.test/v1/chat/completions",
                model_reference="model-reference",
                api_key="SECRET_TOKEN",
                client=Client(),
            ).generate(question="SECRET_QUESTION", context="SECRET_CONTEXT")

    assert caught.value.category == "http_status"
    assert caught.value.status_code == status_code
    assert str(caught.value) == "model provider request failed"
    assert f"status_code={status_code}" in caplog.text
    for secret in ("SECRET_TOKEN", "SECRET_QUESTION", "SECRET_CONTEXT", "SECRET_PROVIDER_ERROR"):
        assert secret not in caplog.text


def test_model_timeout_and_connection_have_safe_categories(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class TimeoutClient:
        def post(self, *args: object, **kwargs: object) -> object:
            raise TimeoutError("SECRET_TOKEN SECRET_PROMPT")

    with caplog.at_level("ERROR", logger="knowledge_platform.infrastructure.models.remote"):
        with pytest.raises(ModelProviderFailure) as caught:
            RemoteModelAdapter(
                endpoint="https://model.test/v1/chat/completions",
                model_reference="model-reference",
                api_key="fake-token",
                client=TimeoutClient(),
            ).generate(question="question", context="context")
    assert caught.value.category == "timeout"
    assert "category=timeout status_code=unknown operation=chat_completion" in caplog.text
    assert "SECRET_" not in caplog.text


def test_model_connection_failure_has_safe_category() -> None:
    class Client:
        def post(self, *args: object, **kwargs: object) -> object:
            raise OSError("SECRET_AUTHORIZATION SECRET_PROVIDER_ERROR")

    with pytest.raises(ModelProviderFailure) as caught:
        RemoteModelAdapter(
            endpoint="https://model.test/v1/chat/completions",
            model_reference="model-reference",
            api_key="fake-token",
            client=Client(),
        ).generate(question="SECRET_QUESTION", context="SECRET_CONTEXT")
    assert caught.value.category == "connection"
    assert "SECRET_" not in str(caught.value)


def test_model_malformed_response_logs_safe_category() -> None:
    class Client:
        def post(self, *args: object, **kwargs: object) -> object:
            class Response:
                status_code = 200

                def json(self) -> dict[str, object]:
                    return {"choices": [{"message": {"content": ""}}]}

            return Response()

    with pytest.raises(ModelProviderFailure) as caught:
        RemoteModelAdapter(
            endpoint="https://model.test/v1/chat/completions",
            model_reference="model-reference",
            api_key="fake-token",
            client=Client(),
        ).generate(question="question", context="context")
    assert caught.value.category == "missing_content"


def test_model_invalid_json_has_distinct_safe_category() -> None:
    class Client:
        def post(self, *args: object, **kwargs: object) -> object:
            class Response:
                status_code = 200

                def json(self) -> dict[str, object]:
                    return {"choices": [{"message": {"content": "not-json"}}]}

            return Response()

    with pytest.raises(ModelProviderFailure) as caught:
        RemoteModelAdapter(
            endpoint="https://model.test", model_reference="model", api_key="token", client=Client()
        ).generate(question="question", context="context")
    assert caught.value.category == "invalid_json"


@pytest.mark.parametrize(
    ("content", "schema_reason"),
    (
        ("[]", "root_not_object"),
        ("{}", "missing_status"),
        ('{"status":1}', "invalid_status_type"),
        ('{"status":"other"}', "invalid_status"),
        (
            '{"status":"grounded","answer":"SECRET_ANSWER","evidence_ids":["E1"],"extra":true}',
            "unexpected_fields",
        ),
        ('{"status":"grounded","evidence_ids":["E1"]}', "grounded_missing_answer"),
        (
            '{"status":"grounded","answer":null,"evidence_ids":["E1"]}',
            "grounded_invalid_answer_type",
        ),
        (
            '{"status":"grounded","answer":"   ","evidence_ids":["E1"]}',
            "grounded_blank_answer",
        ),
        ('{"status":"grounded","answer":"ok"}', "grounded_missing_evidence_ids"),
        (
            '{"status":"grounded","answer":"ok","evidence_ids":"E1"}',
            "grounded_invalid_evidence_ids_shape",
        ),
        (
            '{"status":"grounded","answer":"ok","evidence_ids":[]}',
            "grounded_empty_evidence_ids",
        ),
        (
            '{"status":"grounded","answer":"ok","evidence_ids":["bad"]}',
            "grounded_invalid_evidence_id_shape",
        ),
        (
            '{"status":"grounded","answer":"ok","evidence_ids":["E1","E1"]}',
            "grounded_duplicate_evidence_ids",
        ),
        (
            '{"status":"insufficient","evidence_ids":[]}',
            "insufficient_missing_answer",
        ),
        (
            '{"status":"insufficient","answer":"no","evidence_ids":[]}',
            "insufficient_has_answer",
        ),
        (
            '{"status":"insufficient","answer":null}',
            "insufficient_missing_evidence_ids",
        ),
        (
            '{"status":"insufficient","answer":null,"evidence_ids":"E1"}',
            "insufficient_invalid_evidence_ids_shape",
        ),
        (
            '{"status":"insufficient","answer":null,"evidence_ids":["E1"]}',
            "insufficient_has_evidence_ids",
        ),
    ),
)
def test_schema_validation_branches_have_safe_reason_codes(
    content: str,
    schema_reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Client:
        def post(self, *args: object, **kwargs: object) -> object:
            class Response:
                status_code = 200

                def json(self) -> dict[str, object]:
                    return {"choices": [{"message": {"content": content}}]}

            return Response()

    with caplog.at_level("ERROR", logger="knowledge_platform.infrastructure.models.remote"):
        with pytest.raises(ModelProviderFailure) as caught:
            RemoteModelAdapter(
                endpoint="https://model.test",
                model_reference="model",
                api_key="SECRET_TOKEN",
                client=Client(),
            ).generate(
                question="SECRET_QUESTION",
                context="SECRET_EVIDENCE",
                assistant_instructions="SECRET_INSTRUCTION",
            )

    assert caught.value.category == "schema_validation"
    assert caught.value.schema_reason == schema_reason
    assert f"schema_reason={schema_reason}" in caplog.text
    for secret in (
        "SECRET_TOKEN",
        "SECRET_QUESTION",
        "SECRET_EVIDENCE",
        "SECRET_INSTRUCTION",
        "SECRET_ANSWER",
    ):
        assert secret not in caplog.text


def test_invalid_message_shape_has_safe_schema_reason() -> None:
    class Client:
        def post(self, *args: object, **kwargs: object) -> object:
            class Response:
                status_code = 200

                def json(self) -> dict[str, object]:
                    return {"choices": [{"message": []}]}

            return Response()

    with pytest.raises(ModelProviderFailure) as caught:
        RemoteModelAdapter(
            endpoint="https://model.test",
            model_reference="model",
            api_key="token",
            client=Client(),
        ).generate(question="question", context="context")
    assert caught.value.category == "schema_validation"
    assert caught.value.schema_reason == "invalid_message_shape"


def test_model_adapter_rejects_blank_credential_after_trim() -> None:
    with pytest.raises(ValueError, match="credential is blank"):
        RemoteModelAdapter(
            endpoint="https://model.test/v1/chat/completions",
            model_reference="model-reference",
            api_key=" \r\n",
            client=_RecordingClient(),
        )