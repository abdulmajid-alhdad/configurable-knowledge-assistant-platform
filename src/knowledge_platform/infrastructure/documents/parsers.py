"""Document parsing adapters with platform-owned parsed representations."""

import importlib
import json
import re
import zipfile
from io import BytesIO
from typing import cast
from xml.etree import ElementTree

from knowledge_platform.modules.document_knowledge.ports import (
    DocumentParserPort,
    ParsedDocument,
    ParsedDocumentSection,
)


def _ensure(sections: list[ParsedDocumentSection]) -> ParsedDocument:
    sections = [s for s in sections if s.content.strip()]
    if not sections:
        raise ValueError("parsed document is empty")
    return ParsedDocument(tuple(sections))


class PlainTextDocumentParser:
    def parse(self, content: bytes, *, reference: str = "document") -> ParsedDocument:
        return _ensure([ParsedDocumentSection(content.decode("utf-8"), reference)])


class MarkdownDocumentParser(PlainTextDocumentParser):
    pass


class DocxDocumentParser:
    def parse(self, content: bytes, *, reference: str = "document") -> ParsedDocument:
        try:
            Document = importlib.import_module("docx").Document
        except ImportError:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            paragraphs = []
            for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                text = "".join(
                    node.text or ""
                    for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                )
                paragraphs.append(text)
            return _ensure([
                ParsedDocumentSection(text, f"{reference}#paragraph-{i}")
                for i, text in enumerate(paragraphs)
            ])

        document = Document(BytesIO(content))
        return _ensure(
            [
                ParsedDocumentSection(p.text, f"{reference}#paragraph-{i}")
                for i, p in enumerate(document.paragraphs)
            ]
        )


class PyPdfDocumentParser:
    def parse(self, content: bytes, *, reference: str = "document") -> ParsedDocument:
        try:
            PdfReader = importlib.import_module("pypdf").PdfReader
        except ImportError:
            values = [value.decode("latin-1") for value in re.findall(rb"\(([^()]*)\)", content)]
            return _ensure(
                [ParsedDocumentSection(value, f"{reference}#page-1") for value in values]
            )

        try:
            reader = PdfReader(BytesIO(content))
        except Exception:
            values = [value.decode("latin-1") for value in re.findall(rb"\(([^()]*)\)", content)]
            return _ensure(
                [ParsedDocumentSection(value, f"{reference}#page-1") for value in values]
            )
        return _ensure(
            [
                ParsedDocumentSection(page.extract_text() or "", f"{reference}#page-{i + 1}")
                for i, page in enumerate(reader.pages)
            ]
        )


class JsonDocumentParser:
    def parse(self, content: bytes, *, reference: str = "document") -> ParsedDocument:
        value = json.loads(content.decode("utf-8-sig"))

        def render(item: object, path: str = "") -> list[str]:
            if item is None:
                return []
            if isinstance(item, dict):
                lines: list[str] = []
                for key, child in item.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    lines.extend(render(child, child_path))
                return lines
            if isinstance(item, list):
                lines = []
                for index, child in enumerate(item):
                    child_path = f"{path}.{index}" if path else str(index)
                    lines.extend(render(child, child_path))
                return lines
            return [f"{path}: {item}" if path else str(item)]

        if isinstance(value, list):
            sections = [
                ParsedDocumentSection(
                    "\n".join(render(record)), f"{reference}/{index}"
                )
                for index, record in enumerate(value)
            ]
        else:
            sections = [ParsedDocumentSection("\n".join(render(value)), reference)]
        return _ensure(sections)


def parser_for_suffix(suffix: str) -> DocumentParserPort:
    parsers = {
        ".txt": PlainTextDocumentParser(),
        ".md": MarkdownDocumentParser(),
        ".markdown": MarkdownDocumentParser(),
        ".docx": DocxDocumentParser(),
        ".pdf": PyPdfDocumentParser(),
        ".json": JsonDocumentParser(),
    }
    try:
        return cast(DocumentParserPort, parsers[suffix.lower()])
    except KeyError as exc:
        raise ValueError(f"unsupported document type: {suffix}") from exc
