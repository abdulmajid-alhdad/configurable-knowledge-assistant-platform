"""Deterministic normalization and chunking."""

from dataclasses import dataclass

from knowledge_platform.modules.document_knowledge.ports import (
    ParsedDocument,
    ParsedDocumentSection,
)


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    content: str
    provenance_locator: str
    sequence: int
    embedding: tuple[float, ...] = ()


def normalize(document: ParsedDocument) -> ParsedDocument:
    sections = tuple(
        ParsedDocumentSection(
            " ".join(s.content.replace("\r\n", "\n").replace("\r", "\n").split()),
            s.provenance_locator,
        )
        for s in document.sections
    )
    if not any(s.content for s in sections):
        raise ValueError("normalized document is empty")
    return ParsedDocument(sections)


def chunk(
    document: ParsedDocument, *, size: int = 800, overlap: int = 80
) -> tuple[DocumentChunk, ...]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("invalid chunk bounds")
    result: list[DocumentChunk] = []
    sequence = 0
    for section in document.sections:
        text = section.content
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            value = text[start:end].strip()
            if value:
                result.append(DocumentChunk(value, section.provenance_locator, sequence))
                sequence += 1
            if end == len(text):
                break
            start = end - overlap
    if not result:
        raise ValueError("document has no chunks")
    return tuple(result)
