"""Item schemas."""
from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    """Schema for creating an item."""
    name: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., ge=0, decimal_places=2)
    quantity: int = Field(default=1, ge=1)
    is_tax: bool = False
    is_tip_suggestion: bool = False
    is_refund: bool = False


class ItemUpdate(BaseModel):
    """Schema for updating an item."""
    name: str | None = Field(None, min_length=1, max_length=200)
    price: Decimal | None = Field(None, ge=0, decimal_places=2)
    quantity: int | None = Field(None, ge=1)
    is_tax: bool | None = None
    is_tip_suggestion: bool | None = None
    is_refund: bool | None = None


class ItemResponse(BaseModel):
    """Schema for item response."""
    id: str
    session_id: str
    name: str
    price: Decimal
    quantity: int
    is_tax: bool
    is_tip_suggestion: bool
    is_refund: bool
    position: int
    
    class Config:
        from_attributes = True
