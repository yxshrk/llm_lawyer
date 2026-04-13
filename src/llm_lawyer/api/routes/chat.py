import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from llm_lawyer.config import get_settings
from llm_lawyer.db.models import Document
from llm_lawyer.db.session import SessionDep
from llm_lawyer.llm import client as llm_client
from llm_lawyer.llm import context as ctx
from llm_lawyer.llm import prompts as PROMPTS
from llm_lawyer.rag.retriever import retrieve

router = APIRouter(prefix="/chat", tags=["chat"])


class Citation(BaseModel):
    n: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page: int | None
    bbox: list[float] | None
    score: float
    preview: str


class Usage(BaseModel):
    provider: str
    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int


class ChatIn(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    top_k: int | None = None


class ChatOut(BaseModel):
    conversation_id: uuid.UUID
    reply: str
    model: str
    citations: list[Citation]
    usage: Usage


@router.post("", response_model=ChatOut)
async def chat(body: ChatIn, session: SessionDep) -> ChatOut:
    s = get_settings()
    if not any(
        [s.openai_api_key, s.gemini_api_key, s.groq_api_key]
    ):
        raise HTTPException(500, "No LLM provider configured (openai/gemini/groq)")

    conv = await ctx.get_or_create_conversation(
        session,
        conversation_id=body.conversation_id,
        document_id=body.document_id,
        title=body.message[:60] if body.conversation_id is None else None,
    )

    top_k = body.top_k or s.retrieval_top_k

    # Pipeline isolation — defence-in-depth. If scoped to a document, pull
    # that document's production_type (own/opposing) and clamp the retriever
    # to it so the chat never leaks across sides. Unscoped chat defaults to
    # "own" so opposing production never surfaces unless explicitly requested.
    scope_case_id = None
    scope_production = "own"
    if body.document_id is not None:
        scoped_doc = await session.get(Document, body.document_id)
        if scoped_doc is not None:
            scope_case_id = scoped_doc.case_id
            scope_production = scoped_doc.production_type or "own"

    retrieved = await retrieve(
        session,
        query=body.message,
        top_k=top_k,
        document_id=body.document_id,
        case_id=scope_case_id,
        production_type=scope_production,
    )
    if not retrieved:
        # Empty index is not an error — just tell the user plainly.
        await ctx.append_message(session, conv.id, role="user", content=body.message)
        reply_text = (
            "I don't have any indexed content for this document yet. "
            "Please re-upload or wait for ingestion to finish, then try again."
        )
        await ctx.append_message(
            session, conv.id, role="assistant", content=reply_text
        )
        await session.commit()
        return ChatOut(
            conversation_id=conv.id,
            reply=reply_text,
            model="",
            citations=[],
            usage=Usage(
                provider="",
                prompt_tokens=0,
                cached_prompt_tokens=0,
                completion_tokens=0,
            ),
        )

    excerpts = [
        {"n": i + 1, "page": r.page, "text": r.text}
        for i, r in enumerate(retrieved)
    ]
    context_block = PROMPTS.build_context_block(excerpts)

    # Resolve case_id for memory injection: prefer the document's case_id
    # if the chat is scoped to a document.
    memory_case_id = None
    if body.document_id is not None:
        doc = await session.get(Document, body.document_id)
        if doc is not None:
            memory_case_id = doc.case_id
    memory_ctx = await PROMPTS.load_memory_context(session, memory_case_id)
    system_rendered = PROMPTS.render(PROMPTS.CHAT_SYSTEM, memory_ctx)

    history = await ctx.load_history(session, conv.id)

    # Stable prefix (system+memory + retrieved excerpts) first so the LLM's
    # automatic prompt cache can reuse it across follow-ups.
    messages: list[dict] = [
        {"role": "system", "content": system_rendered},
        {"role": "system", "content": context_block},
    ]
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": body.message})

    await ctx.append_message(session, conv.id, role="user", content=body.message)

    try:
        result = await llm_client.chat_completion(messages)
    except Exception as e:
        await session.commit()  # keep the user message
        raise HTTPException(
            503,
            f"Something went wrong contacting the AI — please try again. ({type(e).__name__})",
        ) from e

    await ctx.append_message(
        session,
        conv.id,
        role="assistant",
        content=result.text,
        metadata={
            "provider": result.provider,
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "cached_prompt_tokens": result.cached_prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "citations": [
                {"n": i + 1, "chunk_id": str(r.chunk_id)}
                for i, r in enumerate(retrieved)
            ],
        },
    )
    await session.commit()

    citations = [
        Citation(
            n=i + 1,
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            page=r.page,
            bbox=r.bbox,
            score=r.score,
            preview=r.text[:200],
        )
        for i, r in enumerate(retrieved)
    ]
    return ChatOut(
        conversation_id=conv.id,
        reply=result.text,
        model=result.model,
        citations=citations,
        usage=Usage(
            provider=result.provider,
            prompt_tokens=result.prompt_tokens,
            cached_prompt_tokens=result.cached_prompt_tokens,
            completion_tokens=result.completion_tokens,
        ),
    )
