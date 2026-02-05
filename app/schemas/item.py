"""Item schemas."""
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    """Schema for creating an item."""
    name: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., ge=0, decimal_places=2)
    quantity: int = Field(default=1, ge=1)
    is_tax: bool = False
    is_tip_suggestion: bool = False


class ItemUpdate(BaseModel):
    """Schema for updating an item."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    quantity: Optional[int] = Field(None, ge=1)
    is_tax: Optional[bool] = None
    is_tip_suggestion: Optional[bool] = None


class ItemResponse(BaseModel):
    """Schema for item response."""
    id: str
    session_id: str
    name: str
    price: Decimal
    quantity: int
    is_tax: bool
    is_tip_suggestion: bool
    position: int
    
    class Config:
        from_attributes = True
