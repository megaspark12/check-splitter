"""Shared API dependencies."""
from datetime import datetime, timezone
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.session_service import SessionService
from app.models.session import Session


def check_session_expiry(session: Session) -> None:
    """Raise 410 if the session has expired."""
    if session.expires_at:
        now = datetime.now(timezone.utc)
        # Handle both naive and aware datetimes
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            raise HTTPException(status_code=410, detail="Session has expired")


async def get_session_or_404(code: str, db: AsyncSession = Depends(get_db)) -> Session:
    """Shared dependency: get a session by code or raise 404/410."""
    service = SessionService(db)
    session = await service.get_session_by_code(code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    check_session_expiry(session)
    return session


async def require_host_token(
    code: str,
    db: AsyncSession = Depends(get_db),
    x_host_token: str = Header(default=None),
) -> Session:
    """Dependency that validates the host token for destructive operations.
    
    Returns the session if the token is valid, raises 401/403 otherwise.
    """
    service = SessionService(db)
    session = await service.get_session_by_code(code)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    check_session_expiry(session)
    if not x_host_token:
        raise HTTPException(status_code=401, detail="Host token required")
    if not session.verify_host_token(x_host_token):
        raise HTTPException(status_code=403, detail="Invalid host token")
    return session
