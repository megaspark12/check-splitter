"""Participant schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class ParticipantCreate(BaseModel):
    """Schema for creating a participant."""
    name: str = Field(..., min_length=1, max_length=100)


class ParticipantUpdate(BaseModel):
    """Schema for updating a participant."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    tip_percentage: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    tip_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=2)


class ParticipantResponse(BaseModel):
    """Schema for participant response."""
    id: str
    session_id: str
    name: str
    is_host: bool
    tip_percentage: Optional[Decimal] = None
    tip_amount: Optional[Decimal] = None
    joined_at: datetime
    
    class Config:
        from_attributes = True
