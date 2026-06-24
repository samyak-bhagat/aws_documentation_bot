"""ChatMemoryRepository — persist and retrieve chat sessions and messages."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import settings
from core.logging import get_logger
from services.memory.models import ChatMessage, ChatSession

logger = get_logger(__name__)


class ChatMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_session(self, session_id: str) -> ChatSession:
        """Return an existing session or create a new one."""
        result = await self._session.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        chat_session = result.scalar_one_or_none()
        if chat_session is None:
            chat_session = ChatSession(session_id=session_id)
            self._session.add(chat_session)
            await self._session.commit()
            await self._session.refresh(chat_session)
        return chat_session

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list | None = None,
        tokens_used: int | None = None,
        latency_ms: float | None = None,
    ) -> ChatMessage:
        """Append a message to the session."""
        chat_session = await self.get_or_create_session(session_id)
        message = ChatMessage(
            session_id=chat_session.id,
            role=role,
            content=content,
            citations=citations,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )
        self._session.add(message)
        await self._session.commit()
        return message

    async def get_recent_messages(self, session_id: str) -> list[ChatMessage]:
        """Return the last MAX_CONTEXT_MESSAGES messages for a session."""
        result = await self._session.execute(
            select(ChatSession)
            .where(ChatSession.session_id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        chat_session = result.scalar_one_or_none()
        if chat_session is None:
            return []
        messages = chat_session.messages
        limit = settings.max_context_messages
        return messages[-limit:] if len(messages) > limit else messages

    async def format_history(self, session_id: str) -> str:
        """Return recent chat history as a formatted string for the LLM prompt."""
        messages = await self.get_recent_messages(session_id)
        if not messages:
            return ""
        lines = []
        for msg in messages:
            prefix = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{prefix}: {msg.content}")
        return "\n".join(lines)
