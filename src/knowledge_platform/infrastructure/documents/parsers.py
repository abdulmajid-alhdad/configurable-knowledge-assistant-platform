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
        value = json.loads(content.decode("utf-8"))
        sections: list[ParsedDocumentSection] = []

        def visit(item: object, pointer: str) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    visit(child, f"{pointer}/{str(key).replace('~', '~0').replace('/', '~1')}")
            elif isinstance(item, list):
                for i, child in enumerate(item):
                    visit(child, f"{pointer}/{i}")
            else:
                sections.append(ParsedDocumentSection(str(item), f"{reference}{pointer or '/'}"))

        visit(value, "")
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
