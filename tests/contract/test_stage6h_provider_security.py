"""Provider-boundary tests for credential and exception secrecy."""

import pytest

from knowledge_platform.infrastructure.embeddings.remote import RemoteEmbeddingAdapter


class _Response:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}


class _RecordingClient:
    def __init__(self) -> None:
        self.headers: dict[str, str] | None = None

    def post(self, endpoint: str, *, json: object, headers: dict[str, str], timeout: int) -> _Response:
        self.headers = headers
        return _Response()


def test_embedding_adapter_does_not_put_surrounding_credential_whitespace_in_header() -> None:
    client = _RecordingClient()
    result = RemoteEmbeddingAdapter(
        endpoint="https://embedding.test/v1",
        model_reference="embedding-model",
        api_key="  fake-token\r\n",
        dimensions=2,
        client=client,
    ).embed_query("text")

    assert result.values == (0.1, 0.2)
    assert client.headers == {"Authorization": "Bearer fake-token"}


class _LeakingProtocolClient:
    def post(self, endpoint: str, *, json: object, headers: dict[str, str], timeout: int) -> object:
        raise RuntimeError("Authorization: Bearer fake-token")


def test_embedding_transport_failure_is_safe_and_does_not_chain_header_text() -> None:
    with pytest.raises(RuntimeError, match="embedding provider request failed") as caught:
        RemoteEmbeddingAdapter(
            endpoint="https://embedding.test/v1",
            model_reference="embedding-model",
            api_key="fake-token",
            dimensions=2,
            client=_LeakingProtocolClient(),
        ).embed_query("text")

    assert "fake-token" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_embedding_adapter_rejects_blank_credential_after_trim() -> None:
    with pytest.raises(ValueError, match="credential is blank"):
        RemoteEmbeddingAdapter(
            endpoint="https://embedding.test/v1",
            model_reference="embedding-model",
            api_key=" \r\n",
            dimensions=2,
            client=_RecordingClient(),
        )


def test_embedding_adapter_restores_shuffled_provider_indexes() -> None:
    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {"index": 2, "embedding": [0.3]},
                    {"index": 0, "embedding": [0.1]},
                    {"index": 1, "embedding": [0.2]},
                ]
            }

    class Client:
        def post(self, *args: object, **kwargs: object) -> Response:
            return Response()

    result = RemoteEmbeddingAdapter(
        endpoint="https://embedding.test/v1",
        model_reference="embedding-model",
        api_key="fake-token",
        dimensions=1,
        client=Client(),
    ).embed_documents(("A", "B", "C"))
    assert tuple(vector.values for vector in result) == ((0.1,), (0.2,), (0.3,))


@pytest.mark.parametrize(
    "data",
    [
        [{"index": 0, "embedding": [0.1]}, {"index": 0, "embedding": [0.2]}],
        [{"index": 0, "embedding": [0.1]}],
        [{"index": 3, "embedding": [0.1]}, {"index": 1, "embedding": [0.2]}],
        [{"index": 0, "embedding": [0.1]}, {"embedding": [0.2]}],
    ],
)
def test_embedding_adapter_rejects_invalid_indexes(data: list[dict[str, object]]) -> None:
    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"data": data}

    class Client:
        def post(self, *args: object, **kwargs: object) -> Response:
            return Response()

    with pytest.raises(RuntimeError, match="malformed embedding response"):
        RemoteEmbeddingAdapter(
            endpoint="https://embedding.test/v1",
            model_reference="embedding-model",
            api_key="fake-token",
            dimensions=1,
            client=Client(),
        ).embed_documents(("A", "B"))
