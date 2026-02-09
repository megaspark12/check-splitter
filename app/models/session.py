"""Session model for check splitting sessions."""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import Column, String, DateTime, Text, Enum, Index
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship
from app.database import Base
from hashlib import sha256


class SessionStatus(str, PyEnum):
    """Session status enum."""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    COMPLETED = "completed"


class Session(Base):
    """A check splitting session."""
    
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
    network_hash = Column(String(64), nullable=True, index=True)  # For nearby session detection
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    host_token_hash = Column(String(64), nullable=True)  # SHA-256 hash of host token
    
    # Relationships
    items = relationship("Item", back_populates="session", cascade="all, delete-orphan")
    participants = relationship("Participant", back_populates="session", cascade="all, delete-orphan")
    discounts = relationship("Discount", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Session(code={self.code}, status={self.status})>"

    def verify_host_token(self, token: str) -> bool:
        """Verify a host token against the stored hash."""
        if not self.host_token_hash or not token:
            return False
        return sha256(token.encode()).hexdigest() == self.host_token_hash

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a host token for storage."""
        return sha256(token.encode()).hexdigest()
