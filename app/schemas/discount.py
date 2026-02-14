"""Discount schemas."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.discount import DiscountType


class DiscountCreate(BaseModel):
    """Schema for creating a discount."""

    name: str | None = Field(
        None, max_length=100
    )  # Optional - will be auto-generated if not provided
    discount_type: DiscountType
    value: Decimal = Field(..., gt=0)
    participant_id: str | None = None  # None = applies to entire bill

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

    name: str | None = Field(None, min_length=1, max_length=100)
    discount_type: DiscountType | None = None
    value: Decimal | None = Field(None, gt=0)
    participant_id: str | None = None  # Can update target


class DiscountResponse(BaseModel):
    """Schema for discount response."""

    id: str
    session_id: str
    participant_id: str | None = None
    participant_name: str | None = None  # Included for convenience
    name: str
    discount_type: DiscountType
    value: Decimal

    class Config:
        from_attributes = True
