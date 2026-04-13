from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_lawyer.db.models import Conversation, Message


async def get_or_create_conversation(
    session: AsyncSession,
    conversation_id: UUID | None,
    document_id: UUID | None,
    title: str | None = None,
) -> Conversation:
    if conversation_id is not None:
        conv = await session.get(Conversation, conversation_id)
        if conv is not None:
            return conv
    conv = Conversation(document_id=document_id, title=title)
    session.add(conv)
    await session.flush()
    return conv


async def load_history(
    session: AsyncSession, conversation_id: UUID
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def append_message(
    session: AsyncSession,
    conversation_id: UUID,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        message_metadata=metadata or {},
    )
    session.add(msg)
    await session.flush()
    return msg
