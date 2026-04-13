"""Recursive, sentence-aware chunker.

Splits text along a hierarchy of separators (paragraph → line → sentence →
clause → word) rather than a dumb token packer. Semantic boundaries matter
for legal docs: contract sections, signature blocks, enumerations.

Still token-aware — each chunk targets ~500 tokens with ~80 tokens of overlap.
Overlap is computed in sentences (not characters) so we never cut mid-clause.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken


@dataclass
class ParsedBlock:
    page: int
    text: str
    bbox: list[float] | None


@dataclass
class Chunk:
    ordinal: int
    page: int
    text: str
    bbox: list[float] | None
    token_count: int


@lru_cache
def _encoder():
    return tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


# Recursive separators: coarse → fine. Each block is split at the first
# separator that produces pieces ≤ target.
_SEPARATORS = [
    "\n\n",     # paragraphs
    "\n",       # line breaks
    r"(?<=[.!?])\s+",  # sentence boundaries (lookbehind — keeps terminator)
    "; ",       # clauses
    ", ",       # softer clauses
    " ",        # words
]


def _split(text: str, separator: str) -> list[str]:
    if separator.startswith("(?<="):
        return re.split(separator, text)
    return text.split(separator)


def _recursive_split(text: str, target_tokens: int) -> list[str]:
    """Return a list of strings each under target_tokens, splitting at the
    coarsest separator possible."""
    if _count_tokens(text) <= target_tokens:
        return [text]
    for sep in _SEPARATORS:
        pieces = _split(text, sep)
        if len(pieces) == 1:
            continue
        # Recurse into any piece that's still too big.
        out: list[str] = []
        for p in pieces:
            p = p.strip()
            if not p:
                continue
            if _count_tokens(p) > target_tokens:
                out.extend(_recursive_split(p, target_tokens))
            else:
                out.append(p)
        return out
    # Ultimate fallback: hard token-slice.
    ids = _encoder().encode(text)
    return [
        _encoder().decode(ids[i : i + target_tokens])
        for i in range(0, len(ids), target_tokens)
    ]


def _union_bbox(
    a: list[float] | None, b: list[float] | None
) -> list[float] | None:
    if a is None:
        return b
    if b is None:
        return a
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


@dataclass
class _Piece:
    text: str
    page: int
    bbox: list[float] | None
    tokens: int


def chunk_blocks(
    blocks: list[ParsedBlock],
    target_tokens: int = 500,
    overlap_tokens: int = 80,
) -> list[Chunk]:
    """Pack parsed blocks into chunks using sentence-aware recursive splitting.

    Each block is first split into sentence-level pieces (if bigger than
    target), then pieces are greedily packed into chunks up to target_tokens.
    Overlap is carried between chunks by re-emitting trailing sentences that
    cover ~overlap_tokens.
    """
    pieces: list[_Piece] = []
    for b in blocks:
        text = b.text.strip()
        if not text:
            continue
        for frag in _recursive_split(text, target_tokens):
            frag = frag.strip()
            if not frag:
                continue
            pieces.append(
                _Piece(text=frag, page=b.page, bbox=b.bbox, tokens=_count_tokens(frag))
            )

    chunks: list[Chunk] = []
    ordinal = 0
    cur: list[_Piece] = []
    cur_tokens = 0

    def _flush():
        nonlocal ordinal, cur, cur_tokens
        if not cur:
            return
        text = "\n".join(p.text for p in cur).strip()
        if not text:
            cur = []
            cur_tokens = 0
            return
        first_page = cur[0].page
        bbox: list[float] | None = None
        for p in cur:
            if p.page == first_page and p.bbox is not None:
                bbox = _union_bbox(bbox, p.bbox)
        chunks.append(
            Chunk(
                ordinal=ordinal,
                page=first_page,
                text=text,
                bbox=bbox,
                token_count=cur_tokens,
            )
        )
        ordinal += 1
        # Carry a tail of trailing pieces whose tokens sum to ~overlap_tokens.
        if overlap_tokens > 0:
            tail: list[_Piece] = []
            tail_tok = 0
            for p in reversed(cur):
                if tail_tok + p.tokens > overlap_tokens and tail:
                    break
                tail.insert(0, p)
                tail_tok += p.tokens
                if tail_tok >= overlap_tokens:
                    break
            cur = list(tail)  # carry tail as next chunk's overlap prefix
            cur_tokens = sum(p.tokens for p in cur)
        else:
            cur = []
            cur_tokens = 0

    for piece in pieces:
        # A single piece that exceeds target is already split to ≤target by
        # _recursive_split, so adding one piece never alone exceeds target.
        if cur_tokens + piece.tokens > target_tokens and cur_tokens > 0:
            _flush()
        cur.append(piece)
        cur_tokens += piece.tokens

    # Final flush without carrying overlap (last chunk stands alone).
    if cur:
        text = "\n".join(p.text for p in cur).strip()
        if text:
            first_page = cur[0].page
            bbox: list[float] | None = None
            for p in cur:
                if p.page == first_page and p.bbox is not None:
                    bbox = _union_bbox(bbox, p.bbox)
            chunks.append(
                Chunk(
                    ordinal=ordinal,
                    page=first_page,
                    text=text,
                    bbox=bbox,
                    token_count=cur_tokens,
                )
            )
    return chunks
