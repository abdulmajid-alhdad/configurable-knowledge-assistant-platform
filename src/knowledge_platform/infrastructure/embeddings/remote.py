"""Minimal provider-neutral remote embedding adapter."""

from typing import Any

from knowledge_platform.modules.document_knowledge.ports import (
    EmbeddingVector,
)


class RemoteEmbeddingAdapter:
    def __init__(
        self,
        *,
        endpoint: str,
        model_reference: str,
        api_key: str,
        dimensions: int,
        client: Any = None,
    ) -> None:
        self.endpoint, self.model_reference, self.api_key, self.dimensions = (
            endpoint,
            model_reference,
            api_key,
            dimensions,
        )
        if client is None:
            import httpx  # type: ignore[import-not-found]
            client = httpx.Client()
        self._client = client

    def _request(self, inputs: list[str]) -> tuple[EmbeddingVector, ...]:
        try:
            response = self._client.post(
                self.endpoint,
                json={"model": self.model_reference, "input": inputs},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
        except TimeoutError as exc:
            raise RuntimeError("embedding request timed out") from exc
        if response.status_code >= 400:
            raise RuntimeError("embedding provider request failed")
        try:
            data = response.json()
            vectors = tuple(
                EmbeddingVector(tuple(float(x) for x in item["embedding"])) for item in data["data"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("malformed embedding response") from exc
        if len(vectors) != len(inputs):
            raise RuntimeError("embedding vector count mismatch")
        if any(not v.values or len(v.values) != self.dimensions for v in vectors):
            raise RuntimeError("embedding dimension mismatch")
        return vectors

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._request([text])[0]

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return self._request(list(texts))
