"""Participant schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class ParticipantCreate(BaseModel):
    """Schema for creating a participant."""
    name: str = Field(..., min_length=1, max_length=100)


class ParticipantUpdate(BaseModel):
    """Schema for updating a participant."""
    name: str | None = Field(None, min_length=1, max_length=100)
    tip_percentage: Decimal | None = Field(None, ge=0, le=100, decimal_places=2)
    tip_amount: Decimal | None = Field(None, ge=0, decimal_places=2)


class ParticipantResponse(BaseModel):
    """Schema for participant response."""
    id: str
    session_id: str
    name: str
    is_host: bool
    tip_percentage: Decimal | None = None
    tip_amount: Decimal | None = None
    joined_at: datetime
    
    class Config:
        from_attributes = True
