"""
Assignments API routes.

Handles item-to-participant assignments.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.websocket_manager import manager
from app.models.session import Session
from app.models.item import Item
from app.models.participant import Participant
from app.models.assignment import ItemAssignment
from app.schemas.assignment import AssignmentCreate, AssignmentResponse
from app.api.dependencies import get_session_or_404

router = APIRouter(prefix="/api/sessions/{code}/assignments", tags=["assignments"])


@router.get("", response_model=List[AssignmentResponse])
async def list_assignments(
    code: str,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """List all assignments in a session."""
    
    # Get all assignments for items in this session
    result = await db.execute(
        select(ItemAssignment)
        .join(Item)
        .where(Item.session_id == session.id)
    )
    
    return result.scalars().all()


@router.post("", status_code=201, response_model=AssignmentResponse)
async def create_assignment(
    code: str,
    assignment_data: AssignmentCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """Assign an item to a participant."""
    
    # Verify item belongs to session
    item_result = await db.execute(
        select(Item).where(
            Item.id == assignment_data.item_id,
            Item.session_id == session.id
        )
    )
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in session")
    
    # Verify participant belongs to session
    participant_result = await db.execute(
        select(Participant).where(
            Participant.id == assignment_data.participant_id,
            Participant.session_id == session.id
        )
    )
    participant = participant_result.scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found in session")
    
    # Check for existing assignment
    existing_result = await db.execute(
        select(ItemAssignment).where(
            ItemAssignment.item_id == assignment_data.item_id,
            ItemAssignment.participant_id == assignment_data.participant_id
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        # Update share count
        existing.share_count = assignment_data.share_count
        await db.commit()
        await db.refresh(existing)
        # Notify all clients
        background_tasks.add_task(manager.notify_session_update, code.upper())
        return existing
    
    # Create new assignment with IntegrityError guard for race condition
    try:
        assignment = ItemAssignment(
            item_id=assignment_data.item_id,
            participant_id=assignment_data.participant_id,
            share_count=assignment_data.share_count,
        )
        
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)
    except IntegrityError:
        # Race condition: another request created the same assignment
        await db.rollback()
        existing_result = await db.execute(
            select(ItemAssignment).where(
                ItemAssignment.item_id == assignment_data.item_id,
                ItemAssignment.participant_id == assignment_data.participant_id
            )
        )
        assignment = existing_result.scalar_one()
        assignment.share_count = assignment_data.share_count
        await db.commit()
        await db.refresh(assignment)
    
    # Notify all clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
    
    return assignment


@router.delete("/{assignment_id}", status_code=204)
async def delete_assignment(
    code: str,
    assignment_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """Remove an item assignment."""
    
    # Get assignment and verify it belongs to this session
    result = await db.execute(
        select(ItemAssignment)
        .join(Item)
        .where(
            ItemAssignment.id == assignment_id,
            Item.session_id == session.id
        )
    )
    assignment = result.scalar_one_or_none()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    await db.delete(assignment)
    await db.commit()
    
    # Notify all clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
