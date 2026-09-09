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
        normalized_api_key = api_key.strip()
        if not normalized_api_key:
            raise ValueError("embedding credential is blank")
        self.endpoint, self.model_reference, self.api_key, self.dimensions = (
            endpoint,
            model_reference,
            normalized_api_key,
            dimensions,
        )
        if client is None:
            httpx = __import__("httpx")
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
        except TimeoutError:
            raise RuntimeError("embedding request timed out") from None
        except Exception:
            # Do not preserve transport exception text: HTTP clients may include
            # Authorization headers in protocol errors and their tracebacks.
            raise RuntimeError("embedding provider request failed") from None
        if response.status_code >= 400:
            raise RuntimeError("embedding provider request failed")
        try:
            data = response.json()
            items = data["data"]
            if not isinstance(items, list) or len(items) != len(inputs):
                raise ValueError("invalid embedding count")
            indexed: dict[int, EmbeddingVector] = {}
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("invalid embedding item")
                index = item["index"]
                if not isinstance(index, int) or isinstance(index, bool):
                    raise ValueError("invalid embedding index")
                if index < 0 or index >= len(inputs) or index in indexed:
                    raise ValueError("invalid embedding index")
                values = item["embedding"]
                if not isinstance(values, (list, tuple)):
                    raise ValueError("invalid embedding values")
                indexed[index] = EmbeddingVector(tuple(float(x) for x in values))
            if set(indexed) != set(range(len(inputs))):
                raise ValueError("incomplete embedding indexes")
            vectors = tuple(indexed[index] for index in range(len(inputs)))
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("malformed embedding response") from None
        if len(vectors) != len(inputs):
            raise RuntimeError("embedding vector count mismatch")
        if any(not v.values or len(v.values) != self.dimensions for v in vectors):
            raise RuntimeError("embedding dimension mismatch")
        return vectors

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._request([text])[0]

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return self._request(list(texts))
