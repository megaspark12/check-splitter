"""Session model for receipt splitting sessions."""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, String, DateTime, Text, Enum
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship
from app.database import Base


class SessionStatus(str, PyEnum):
    """Session status enum."""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    COMPLETED = "completed"


class Session(Base):
    """A receipt splitting session."""
    
    __tablename__ = "sessions"
    
    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(6), unique=True, index=True, nullable=False)
    receipt_image_path = Column(String(500), nullable=True)
    raw_ocr_text = Column(Text, nullable=True)
    status = Column(
        Enum(SessionStatus),
        default=SessionStatus.PENDING,
        nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    
    # Relationships
    items = relationship("Item", back_populates="session", cascade="all, delete-orphan")
    participants = relationship("Participant", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Session(code={self.code}, status={self.status})>"
