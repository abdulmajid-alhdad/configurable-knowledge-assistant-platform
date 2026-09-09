"""Generic test bridge from ingested representations to VectorSearchPort."""

from math import sqrt

from knowledge_platform.modules.document_knowledge.ports import EmbeddingVector


class IngestedRepresentationSearch:
    def __init__(self) -> None:
        self.representations = []

    def add(self, representation: object) -> None:
        self.representations.append(representation)

    def activate(self, *, representation: object, workspace_id: object) -> None:
        self.representations = [
            representation if item.id == representation.id else item
            for item in self.representations
        ]

    def search(
        self, *, workspace_id, source_ids, query: EmbeddingVector, limit: int = 5
    ) -> tuple[object, ...]:
        rows = []
        for representation in self.representations:
            if (
                representation.workspace_id != workspace_id
                or representation.state.value != "ACTIVE"
            ):
                continue
            if representation.source_id not in source_ids:
                continue
            for chunk in representation.chunks:
                vector = EmbeddingVector(tuple(chunk.embedding or ()))
                score = _cosine(query.values, vector.values)
                rows.append((score, chunk))
        rows.sort(key=lambda item: item[0], reverse=True)
        return tuple(item[1] for item in rows[:limit])


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    denominator = sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0.0
    )
