from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_lawyer.db.models import Chunk
from llm_lawyer.rag.embeddings import embed_query
from llm_lawyer.rag.reranker import rerank_texts


@dataclass
class Retrieved:
    chunk_id: UUID
    document_id: UUID
    page: int | None
    ordinal: int
    text: str
    bbox: list[float] | None
    score: float  # cosine similarity in [-1, 1], higher = more similar


async def retrieve(
    session: AsyncSession,
    query: str,
    top_k: int = 8,
    document_id: UUID | None = None,
    use_reranker: bool = True,
    overfetch: int = 4,
) -> list[Retrieved]:
    """pgvector cosine top-k with optional Voyage cross-encoder rerank.

    When ``use_reranker`` is True, we over-fetch (top_k * overfetch) with the
    fast dense retriever and then rerank that shortlist down to top_k with the
    cross-encoder. Net: same k returned to the caller, dramatically better
    precision (industry: +28–48% NDCG@10).
    """
    qvec = await embed_query(query)

    fetch_k = top_k * overfetch if use_reranker else top_k
    distance = Chunk.embedding.cosine_distance(qvec).label("distance")
    stmt = select(Chunk, distance).order_by(distance).limit(fetch_k)
    if document_id is not None:
        stmt = stmt.where(Chunk.document_id == document_id)

    rows = (await session.execute(stmt)).all()
    shortlist: list[Retrieved] = []
    for chunk, dist in rows:
        shortlist.append(
            Retrieved(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                page=chunk.page,
                ordinal=chunk.ordinal,
                text=chunk.text,
                bbox=chunk.bbox,
                score=float(1.0 - dist),
            )
        )

    if not shortlist or not use_reranker or len(shortlist) <= top_k:
        return shortlist[:top_k]

    return await rerank_texts(query, shortlist, get_text=lambda r: r.text, top_k=top_k)
