import io
from dataclasses import dataclass

import docx as python_docx


@dataclass
class ParsedBlock:
    page: int  # DOCX has no native page concept — always 0 for now
    text: str
    bbox: list[float] | None


@dataclass
class ParsedDocx:
    blocks: list[ParsedBlock]
    author: str | None = None


def parse_docx(data: bytes) -> ParsedDocx:
    doc = python_docx.Document(io.BytesIO(data))
    blocks: list[ParsedBlock] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        blocks.append(ParsedBlock(page=0, text=text, bbox=None))
    author = None
    try:
        author = (doc.core_properties.author or None) or None
        if author is not None:
            author = author.strip() or None
    except Exception:
        pass
    return ParsedDocx(blocks=blocks, author=author)
