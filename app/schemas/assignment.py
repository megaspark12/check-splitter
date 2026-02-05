"""Assignment schemas."""
from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    """Schema for creating an assignment."""
    item_id: str
    participant_id: str
    share_count: int = Field(default=1, ge=1)


class AssignmentResponse(BaseModel):
    """Schema for assignment response."""
    id: str
    item_id: str
    participant_id: str
    share_count: int
    
    class Config:
        from_attributes = True
