"""Session schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.session import SessionStatus


class SessionCreate(BaseModel):
    """Schema for creating a session."""
    host_name: str = Field(..., min_length=1, max_length=100)


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
    
    class Config:
        from_attributes = True


class ParticipantSummary(BaseModel):
    """Summary of a participant's bill."""
    participant_id: str
    participant_name: str
    items_subtotal: Decimal
    tax_share: Decimal
    tip_amount: Decimal
    total: Decimal
    items: List[dict]


class SessionSummary(BaseModel):
    """Summary of the entire session's bill split."""
    session_id: str
    session_code: str
    receipt_total: Decimal
    tax_total: Decimal
    calculated_total: Decimal
    participants: List[ParticipantSummary]
    unassigned_items: List[dict]
