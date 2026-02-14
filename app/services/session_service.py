"""
Session management service.

Handles session creation, retrieval, and management.
"""

from __future__ import annotations

import random
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.participant import Participant
from app.models.session import Session, SessionStatus


class SessionService:
    """Service for managing check splitting sessions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    def _generate_code(self) -> str:
        """Generate a random session code."""
        chars = string.ascii_uppercase + string.digits
        return "".join(random.choices(chars, k=self.settings.session_code_length))

    async def _is_code_unique(self, code: str) -> bool:
        """Check if a session code is unique."""
        result = await self.db.execute(
            select(Session).where(Session.code == code.upper())
        )
        return result.scalar_one_or_none() is None

    async def generate_unique_code(self) -> str:
        """Generate a unique session code."""
        for _ in range(10):  # Max 10 attempts
            code = self._generate_code()
            if await self._is_code_unique(code):
                return code
        raise RuntimeError("Could not generate unique session code")

    async def create_session(
        self, host_name: str, network_hash: str = None, location_hash: str = None
    ) -> tuple[Session, str]:
        """
        Create a new session with the host as the first participant.

        Args:
            host_name: Name of the session host
            network_hash: Hash of the client's network for nearby detection (IP-based)
            location_hash: Geohash of the client's location for nearby detection (GPS-based)

        Returns:
            Tuple of (Session object, plain-text host token)
        """
        code = await self.generate_unique_code()

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.session_expiry_minutes
        )

        # Generate a secure host token
        host_token = secrets.token_urlsafe(32)

        session = Session(
            code=code,
            status=SessionStatus.PENDING,
            network_hash=network_hash,
            location_hash=location_hash,
            expires_at=expires_at,
            host_token_hash=Session.hash_token(host_token),
        )

        self.db.add(session)
        await self.db.flush()  # Get the session ID

        # Create host participant
        host = Participant(
            session_id=session.id,
            name=host_name,
            is_host=True,
        )
        self.db.add(host)

        await self.db.commit()

        # Reload with relationships
        stmt = (
            select(Session)
            .where(Session.id == session.id)
            .options(selectinload(Session.items))
            .options(selectinload(Session.participants))
            .options(selectinload(Session.discounts))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one(), host_token

    async def get_session_by_code(self, code: str) -> Session | None:
        """
        Get a session by its code.

        Args:
            code: The session code (case-insensitive)

        Returns:
            The Session object or None if not found
        """
        from app.models.assignment import ItemAssignment
        from app.models.discount import Discount
        from app.models.item import Item

        result = await self.db.execute(
            select(Session)
            .where(Session.code == code.upper())
            .options(
                selectinload(Session.items).selectinload(Item.assignments),
                selectinload(Session.participants),
                selectinload(Session.discounts),
            )
        )
        return result.scalar_one_or_none()

    async def delete_session(self, code: str) -> bool:
        """
        Delete a session by its code.

        Args:
            code: The session code

        Returns:
            True if deleted, False if not found
        """
        session = await self.get_session_by_code(code)
        if not session:
            return False

        await self.db.delete(session)
        await self.db.commit()
        return True

    async def update_session_status(
        self, code: str, status: SessionStatus
    ) -> Session | None:
        """
        Update a session's status.

        Args:
            code: The session code
            status: The new status

        Returns:
            The updated Session or None if not found
        """
        session = await self.get_session_by_code(code)
        if not session:
            return None

        session.status = status
        await self.db.commit()
        await self.db.refresh(session)

        return session
