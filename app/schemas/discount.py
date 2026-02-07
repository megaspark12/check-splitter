"""Discount schemas."""
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.models.discount import DiscountType


class DiscountCreate(BaseModel):
    """Schema for creating a discount."""
    name: Optional[str] = Field(None, max_length=100)  # Optional - will be auto-generated if not provided
    discount_type: DiscountType
    value: Decimal = Field(..., gt=0)
    participant_id: Optional[str] = None  # None = applies to entire bill
    
    @field_validator("value")
    @classmethod
    def validate_percentage(cls, v, info):
        """Validate percentage is between 0 and 100."""
        if info.data.get("discount_type") == DiscountType.PERCENTAGE:
            if v > 100:
                raise ValueError("Percentage discount cannot exceed 100%")
        return v


class DiscountUpdate(BaseModel):
    """Schema for updating a discount."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    discount_type: Optional[DiscountType] = None
    value: Optional[Decimal] = Field(None, gt=0)
    participant_id: Optional[str] = None  # Can update target


class DiscountResponse(BaseModel):
    """Schema for discount response."""
    id: str
    session_id: str
    participant_id: Optional[str] = None
    participant_name: Optional[str] = None  # Included for convenience
    name: str
    discount_type: DiscountType
    value: Decimal
    
    class Config:
        from_attributes = True
