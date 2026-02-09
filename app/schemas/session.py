"""Session schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.session import SessionStatus


class SessionCreate(BaseModel):
    """Schema for creating a session."""
    host_name: str = Field(..., min_length=1, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="GPS latitude for nearby discovery")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="GPS longitude for nearby discovery")


class AssignmentInItem(BaseModel):
    """Assignment within an item response."""
    id: str
    participant_id: str
    share_count: int
    
    class Config:
        from_attributes = True


class ItemInSession(BaseModel):
    """Item within a session response."""
    id: str
    name: str
    price: Decimal
    quantity: int
    is_tax: bool
    is_tip_suggestion: bool
    assignments: List[AssignmentInItem] = []
    
    class Config:
        from_attributes = True


class ParticipantInSession(BaseModel):
    """Participant within a session response."""
    id: str
    name: str
    is_host: bool
    tip_percentage: Optional[Decimal] = None
    tip_amount: Optional[Decimal] = None
    
    class Config:
        from_attributes = True


class DiscountInSession(BaseModel):
    """Discount within a session response."""
    id: str
    name: str
    discount_type: str
    value: Decimal
    participant_id: Optional[str] = None
    
    class Config:
        from_attributes = True
    
    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Handle enum conversion for discount_type."""
        if hasattr(obj, 'discount_type') and hasattr(obj.discount_type, 'value'):
            # Convert enum to string value
            data = {
                'id': obj.id,
                'name': obj.name,
                'discount_type': obj.discount_type.value,
                'value': obj.value,
                'participant_id': obj.participant_id
            }
            return cls(**data)
        return super().model_validate(obj, **kwargs)


class SessionResponse(BaseModel):
    """Schema for session response."""
    id: str
    code: str
    status: SessionStatus
    receipt_image_path: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    items: List[ItemInSession] = []
    participants: List[ParticipantInSession] = []
    discounts: List[DiscountInSession] = []
    host_token: Optional[str] = None  # Only returned on session creation
    
    class Config:
        from_attributes = True


class AppliedDiscount(BaseModel):
    """A discount that was applied to a participant."""
    id: str
    name: str
    type: str
    value: Decimal
    amount: Decimal


class ParticipantSummary(BaseModel):
    """Summary of a participant's bill."""
    participant_id: str
    participant_name: str
    items_subtotal: Decimal
    tax_share: Decimal
    tip_amount: Decimal
    discount_amount: Decimal = Decimal("0.00")
    total: Decimal
    items: List[dict]
    applied_discounts: List[AppliedDiscount] = []


class SessionSummary(BaseModel):
    """Summary of the entire session's bill split."""
    session_id: str
    session_code: str
    receipt_total: Decimal
    tax_total: Decimal
    total_discount: Decimal = Decimal("0.00")
    calculated_total: Decimal
    participants: List[ParticipantSummary]
    unassigned_items: List[dict]


class NearbySession(BaseModel):
    """Schema for a nearby session."""
    code: str
    host_name: str
    participant_count: int
    status: SessionStatus
    created_at: datetime
    
    class Config:
        from_attributes = True


class NearbySessionsResponse(BaseModel):
    """Schema for nearby sessions response."""
    sessions: List[NearbySession]
