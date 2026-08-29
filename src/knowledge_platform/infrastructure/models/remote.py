"""Minimal remote model adapter."""

from typing import Any


class RemoteModelAdapter:
    def __init__(
        self,
        *,
        endpoint: str,
        model_reference: str,
        api_key: str,
        client: Any = None,
    ) -> None:
        self.endpoint, self.model_reference, self.api_key = endpoint, model_reference, api_key
        if client is None:
            import httpx  # type: ignore[import-not-found]
            client = httpx.Client()
        self._client = client

    def generate(self, *, question: str, context: str) -> str:
        response = self._client.post(
            self.endpoint,
            json={
                "model": self.model_reference,
                "messages": [
                    {"role": "user", "content": f"Question: {question}\nEvidence:\n{context}"}
                ],
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError("model provider request failed")
        try:
            return str(response.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("malformed model response") from exc
