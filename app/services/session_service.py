"""
Session management service.

Handles session creation, retrieval, and management.
"""
import random
import string
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.session import Session, SessionStatus
from app.models.participant import Participant
from app.config import get_settings


class SessionService:
    """Service for managing receipt splitting sessions."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
    
    def _generate_code(self) -> str:
        """Generate a random session code."""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=self.settings.session_code_length))
    
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
    
    async def create_session(self, host_name: str, network_hash: str = None) -> Session:
        """
        Create a new session with the host as the first participant.
        
        Args:
            host_name: Name of the session host
            network_hash: Hash of the client's network for nearby detection
            
        Returns:
            The created Session object
        """
        code = await self.generate_unique_code()
        
        expires_at = datetime.utcnow() + timedelta(
            minutes=self.settings.session_expiry_minutes
        )
        
        session = Session(
            code=code,
            status=SessionStatus.PENDING,
            network_hash=network_hash,
            expires_at=expires_at,
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
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()
    
    async def get_session_by_code(self, code: str) -> Optional[Session]:
        """
        Get a session by its code.
        
        Args:
            code: The session code (case-insensitive)
            
        Returns:
            The Session object or None if not found
        """
        from app.models.item import Item
        from app.models.assignment import ItemAssignment
        
        result = await self.db.execute(
            select(Session)
            .where(Session.code == code.upper())
            .options(
                selectinload(Session.items).selectinload(Item.assignments),
                selectinload(Session.participants),
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
        self, 
        code: str, 
        status: SessionStatus
    ) -> Optional[Session]:
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
