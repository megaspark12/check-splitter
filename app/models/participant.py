"""Participant model for session participants."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship
from app.database import Base


class Participant(Base):
    """A participant in a check splitting session."""
    
    __tablename__ = "participants"
    
    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(CHAR(36), ForeignKey("sessions.id"), nullable=False)
    name = Column(String(100), nullable=False)
    is_host = Column(Boolean, default=False, nullable=False)
    tip_percentage = Column(Numeric(5, 2), nullable=True)
    tip_amount = Column(Numeric(10, 2), nullable=True)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    session = relationship("Session", back_populates="participants")
    assignments = relationship("ItemAssignment", back_populates="participant", cascade="all, delete-orphan")
    discounts = relationship("Discount", back_populates="participant", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Participant(name={self.name}, is_host={self.is_host})>"
