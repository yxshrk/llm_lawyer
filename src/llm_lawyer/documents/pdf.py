from dataclasses import dataclass

import pymupdf


@dataclass
class ParsedBlock:
    page: int  # 0-indexed
    text: str
    bbox: list[float]  # [x0, y0, x1, y1]


@dataclass
class ParsedPdf:
    page_count: int
    blocks: list[ParsedBlock]
    author: str | None = None


def parse_pdf(data: bytes) -> ParsedPdf:
    doc = pymupdf.open(stream=data, filetype="pdf")
    blocks: list[ParsedBlock] = []
    try:
        author = None
        meta = doc.metadata or {}
        for key in ("author", "Author"):
            if meta.get(key):
                author = str(meta[key]).strip()
                break
        for page_idx in range(doc.page_count):
            page = doc.load_page(page_idx)
            for b in page.get_text("blocks"):
                x0, y0, x1, y1, text, _block_no, block_type = b[:7]
                if block_type != 0:  # 0 == text
                    continue
                text = (text or "").strip()
                if not text:
                    continue
                blocks.append(
                    ParsedBlock(
                        page=page_idx,
                        text=text,
                        bbox=[float(x0), float(y0), float(x1), float(y1)],
                    )
                )
        return ParsedPdf(
            page_count=doc.page_count, blocks=blocks, author=author
        )
    finally:
        doc.close()
