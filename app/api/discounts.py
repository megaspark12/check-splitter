"""
Discounts API routes.

Handles discount creation, updates, and deletion for sessions.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.discount import Discount
from app.models.session import Session
from app.models.participant import Participant
from app.schemas.discount import DiscountCreate, DiscountUpdate, DiscountResponse

router = APIRouter(prefix="/api/sessions/{session_code}/discounts", tags=["discounts"])


async def get_session_by_code(db: AsyncSession, code: str) -> Session:
    """Get session by code with discounts loaded."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.discounts).selectinload(Discount.participant))
        .where(Session.code == code)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("", response_model=List[DiscountResponse])
async def list_discounts(
    session_code: str,
    db: AsyncSession = Depends(get_db)
):
    """List all discounts for a session."""
    session = await get_session_by_code(db, session_code)
    
    return [
        DiscountResponse(
            id=d.id,
            session_id=d.session_id,
            participant_id=d.participant_id,
            participant_name=d.participant.name if d.participant else None,
            name=d.name,
            discount_type=d.discount_type,
            value=d.value
        )
        for d in session.discounts
    ]


@router.post("", status_code=201, response_model=DiscountResponse)
async def create_discount(
    session_code: str,
    discount_data: DiscountCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new discount for a session."""
    session = await get_session_by_code(db, session_code)
    
    # Validate participant_id if provided
    participant = None
    if discount_data.participant_id:
        result = await db.execute(
            select(Participant).where(
                Participant.id == discount_data.participant_id,
                Participant.session_id == session.id
            )
        )
        participant = result.scalar_one_or_none()
        if not participant:
            raise HTTPException(status_code=404, detail="Participant not found in this session")
    
    # Auto-generate name if not provided
    discount_name = discount_data.name
    if not discount_name or not discount_name.strip():
        # Build a descriptive name
        if discount_data.discount_type.value == "percentage":
            value_str = f"{discount_data.value}%"
        else:
            value_str = f"${discount_data.value}"
        
        if participant:
            discount_name = f"{value_str} off for {participant.name}"
        else:
            discount_name = f"{value_str} off"
    
    discount = Discount(
        session_id=session.id,
        participant_id=discount_data.participant_id,
        name=discount_name,
        discount_type=discount_data.discount_type,
        value=discount_data.value
    )
    
    db.add(discount)
    await db.commit()
    await db.refresh(discount)
    
    return DiscountResponse(
        id=discount.id,
        session_id=discount.session_id,
        participant_id=discount.participant_id,
        participant_name=participant.name if participant else None,
        name=discount.name,
        discount_type=discount.discount_type,
        value=discount.value
    )


@router.put("/{discount_id}", response_model=DiscountResponse)
async def update_discount(
    session_code: str,
    discount_id: str,
    discount_data: DiscountUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a discount."""
    session = await get_session_by_code(db, session_code)
    
    # Find the discount
    result = await db.execute(
        select(Discount)
        .options(selectinload(Discount.participant))
        .where(Discount.id == discount_id, Discount.session_id == session.id)
    )
    discount = result.scalar_one_or_none()
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    
    # Update fields
    if discount_data.name is not None:
        discount.name = discount_data.name
    if discount_data.discount_type is not None:
        discount.discount_type = discount_data.discount_type
    if discount_data.value is not None:
        discount.value = discount_data.value
    if discount_data.participant_id is not None:
        # Validate new participant
        if discount_data.participant_id:
            result = await db.execute(
                select(Participant).where(
                    Participant.id == discount_data.participant_id,
                    Participant.session_id == session.id
                )
            )
            participant = result.scalar_one_or_none()
            if not participant:
                raise HTTPException(status_code=404, detail="Participant not found in this session")
            discount.participant_id = discount_data.participant_id
        else:
            discount.participant_id = None
    
    await db.commit()
    await db.refresh(discount)
    
    # Reload participant relationship
    result = await db.execute(
        select(Discount)
        .options(selectinload(Discount.participant))
        .where(Discount.id == discount_id)
    )
    discount = result.scalar_one()
    
    return DiscountResponse(
        id=discount.id,
        session_id=discount.session_id,
        participant_id=discount.participant_id,
        participant_name=discount.participant.name if discount.participant else None,
        name=discount.name,
        discount_type=discount.discount_type,
        value=discount.value
    )


@router.delete("/{discount_id}", status_code=204)
async def delete_discount(
    session_code: str,
    discount_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a discount."""
    session = await get_session_by_code(db, session_code)
    
    result = await db.execute(
        select(Discount).where(Discount.id == discount_id, Discount.session_id == session.id)
    )
    discount = result.scalar_one_or_none()
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    
    await db.delete(discount)
    await db.commit()
