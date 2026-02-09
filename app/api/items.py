"""
Items API routes.

Handles CRUD operations for receipt items.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.websocket_manager import manager
from app.models.session import Session
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate, ItemResponse
from app.api.dependencies import get_session_or_404, require_host_token

router = APIRouter(prefix="/api/sessions/{code}/items", tags=["items"])


@router.get("", response_model=List[ItemResponse])
async def list_items(
    code: str,
    session: Session = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db)
):
    """List all items in a session."""
    return session.items


@router.post("", status_code=201, response_model=ItemResponse)
async def create_item(
    code: str,
    item_data: ItemCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(require_host_token),
    db: AsyncSession = Depends(get_db)
):
    """Add an item to a session. Requires host token."""
    
    # Get next position
    max_position = max((i.position for i in session.items), default=-1)
    
    item = Item(
        session_id=session.id,
        name=item_data.name,
        price=item_data.price,
        quantity=item_data.quantity,
        is_tax=item_data.is_tax,
        is_tip_suggestion=item_data.is_tip_suggestion,
        position=max_position + 1,
    )
    
    db.add(item)
    await db.commit()
    await db.refresh(item)
    
    # Notify all connected clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
    
    return item


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    code: str,
    item_id: str,
    item_data: ItemUpdate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(require_host_token),
    db: AsyncSession = Depends(get_db)
):
    """Update an item. Requires host token."""
    
    # Find the item
    result = await db.execute(
        select(Item).where(
            Item.id == item_id,
            Item.session_id == session.id
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Update fields
    if item_data.name is not None:
        item.name = item_data.name
    if item_data.price is not None:
        item.price = item_data.price
    if item_data.quantity is not None:
        item.quantity = item_data.quantity
    if item_data.is_tax is not None:
        item.is_tax = item_data.is_tax
    if item_data.is_tip_suggestion is not None:
        item.is_tip_suggestion = item_data.is_tip_suggestion
    
    await db.commit()
    await db.refresh(item)
    
    # Notify all connected clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
    
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    code: str,
    item_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(require_host_token),
    db: AsyncSession = Depends(get_db)
):
    """Delete an item. Requires host token."""
    
    result = await db.execute(
        select(Item).where(
            Item.id == item_id,
            Item.session_id == session.id
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    await db.delete(item)
    await db.commit()
    
    # Notify all connected clients
    background_tasks.add_task(manager.notify_session_update, code.upper())
