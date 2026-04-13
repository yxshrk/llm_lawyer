"""Contextual Retrieval — generate per-chunk situating context in ONE call.

Implements Anthropic's Contextual Retrieval (Sept 2024): for each chunk,
generate a 1-2 sentence context that situates the chunk within its
source document. Prepend the context to the chunk text before embedding
so the vector encodes both the local content AND the global position.

Research numbers from Anthropic's own benchmarks:
- 35% reduction in top-20 retrieval failure with contextual embeddings alone
- 49% with contextual BM25 fused in
- 67% when combined with a cross-encoder reranker

We batch all chunks of a document into ONE LLM call — the full doc is sent
once as the "document" context, and we ask for a JSON array of contexts
indexed by chunk number. O(1) LLM calls per document, not O(N).
"""
from __future__ import annotations

import logging

from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm.structured import extract_json

logger = logging.getLogger(__name__)


_CONTEXT_SYSTEM = """You produce short 1-2 sentence context strings for
chunks of a legal/business document. Each context must situate the chunk
inside the source document so a retriever can find it from a general query.

Rules:
- Write in the third person, neutral tone.
- Mention who the chunk is FROM, who it's TO, the document/email subject
  or section, the date if present, and the chunk's role (e.g. "describes
  the Oct 15 Gibson access", "lists the Q3 finance numbers").
- Do NOT repeat the chunk text verbatim. Summarise, don't paste.
- Keep each context under 40 words. Two sentences max.
- Output a JSON object mapping integer ordinals to context strings."""


_CONTEXT_USER_TEMPLATE = """Here is the full source document:

<document>
{document}
</document>

Here are the chunks extracted from it (keyed by ordinal):

<chunks>
{chunks}
</chunks>

Return a JSON object of the form:
{{"0": "context for chunk 0", "1": "context for chunk 1", ...}}

One entry per ordinal, in order. No prose outside the JSON."""


def _format_chunks_for_prompt(chunks: list[tuple[int, str]]) -> str:
    lines = []
    for ordinal, text in chunks:
        snippet = text if len(text) <= 600 else text[:600] + "…"
        lines.append(f"[{ordinal}]\n{snippet}\n")
    return "\n".join(lines)


async def generate_contexts(
    document_title: str,
    document_text: str,
    chunks: list[tuple[int, str]],
    *,
    max_doc_chars: int = 20_000,
) -> dict[int, str]:
    """Return {ordinal: context_string} for every chunk.

    On any LLM failure we return an empty dict and the caller falls back to
    embedding the raw chunks. This keeps Contextual Retrieval as a *boost*,
    never a blocker — failures degrade gracefully to the pre-contextual
    behaviour.
    """
    if not chunks:
        return {}

    # Truncate the document to keep the prompt bounded. For very long docs
    # the tail gets cut; chunks from the tail still get context because the
    # model sees the beginning + the chunks themselves.
    doc_text = document_text[:max_doc_chars]
    if len(document_text) > max_doc_chars:
        doc_text += f"\n\n[… document truncated at {max_doc_chars} chars, {len(document_text)} total …]"

    user_content = _CONTEXT_USER_TEMPLATE.format(
        document=f"Title: {document_title}\n\n{doc_text}",
        chunks=_format_chunks_for_prompt(chunks),
    )

    try:
        result = await llm_client.chat_completion(
            [
                {"role": "system", "content": _CONTEXT_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            task="structured",
            json_mode=True,
        )
    except Exception as e:
        logger.warning("contextualizer LLM call failed: %s", e)
        return {}

    data = extract_json(result.text)
    if not isinstance(data, dict):
        return {}

    out: dict[int, str] = {}
    for k, v in data.items():
        try:
            ordinal = int(k)
        except (TypeError, ValueError):
            continue
        if not isinstance(v, str):
            continue
        text = v.strip()
        if text:
            out[ordinal] = text[:500]
    return out


def apply_contexts(
    chunks_texts: list[str],
    contexts: dict[int, str],
) -> list[str]:
    """Return the list of texts that should be embedded: each chunk has
    its context prepended when available, otherwise the raw text."""
    embed_inputs: list[str] = []
    for i, raw in enumerate(chunks_texts):
        ctx = contexts.get(i)
        embed_inputs.append(f"{ctx}\n\n{raw}" if ctx else raw)
    return embed_inputs
