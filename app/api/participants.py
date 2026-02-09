"""
Participants API routes.

Handles participant management for sessions.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.websocket_manager import manager
from app.models.session import Session
from app.models.participant import Participant
from app.schemas.participant import ParticipantCreate, ParticipantUpdate, ParticipantResponse
from app.api.dependencies import get_session_or_404, require_host_token

router = APIRouter(prefix="/api/sessions/{code}/participants", tags=["participants"])


@router.get("", response_model=List[ParticipantResponse])
async def list_participants(
    code: str,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """List all participants in a session."""
    return session.participants


@router.post("", status_code=201, response_model=ParticipantResponse)
async def join_session(
    code: str,
    participant_data: ParticipantCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """Join a session as a new participant."""
    
    participant = Participant(
        session_id=session.id,
        name=participant_data.name,
        is_host=False,
    )
    
    db.add(participant)
    await db.commit()
    await db.refresh(participant)
    
    # Notify all connected clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
    
    return participant


@router.put("/{participant_id}", response_model=ParticipantResponse)
async def update_participant(
    code: str,
    participant_id: str,
    participant_data: ParticipantUpdate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """Update a participant's details (name, tip)."""
    
    result = await db.execute(
        select(Participant).where(
            Participant.id == participant_id,
            Participant.session_id == session.id
        )
    )
    participant = result.scalar_one_or_none()
    
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    if participant_data.name is not None:
        participant.name = participant_data.name
    if participant_data.tip_percentage is not None:
        participant.tip_percentage = participant_data.tip_percentage
        participant.tip_amount = None  # Clear fixed tip if percentage is set
    if participant_data.tip_amount is not None:
        participant.tip_amount = participant_data.tip_amount
        participant.tip_percentage = None  # Clear percentage if fixed tip is set
    
    await db.commit()
    await db.refresh(participant)
    
    # Notify all connected clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
    
    return participant


@router.delete("/{participant_id}", status_code=204)
async def leave_session(
    code: str,
    participant_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(require_host_token),
    db: AsyncSession = Depends(get_db)
):
    """Remove a participant from the session. Requires host token."""
    
    result = await db.execute(
        select(Participant).where(
            Participant.id == participant_id,
            Participant.session_id == session.id
        )
    )
    participant = result.scalar_one_or_none()
    
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    if participant.is_host:
        raise HTTPException(
            status_code=400, 
            detail="Cannot remove the host from the session"
        )
    
    await db.delete(participant)
    await db.commit()
    
    # Notify all connected clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
