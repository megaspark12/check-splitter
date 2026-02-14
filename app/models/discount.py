"""Discount model for session discounts."""

import uuid
from enum import Enum as PyEnum

from sqlalchemy import Column, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship

from app.database import Base


class DiscountType(str, PyEnum):
    """Type of discount."""

    PERCENTAGE = "percentage"  # e.g., 10% off
    FIXED = "fixed"  # e.g., $10 off


class Discount(Base):
    """A discount applied to a session or participant."""

    __tablename__ = "discounts"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        CHAR(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    # Optional: if set, discount applies only to this participant
    # If null, discount applies to entire bill (split proportionally)
    participant_id = Column(
        CHAR(36), ForeignKey("participants.id", ondelete="CASCADE"), nullable=True
    )

    name = Column(String(100), nullable=False)  # e.g., "Birthday Coupon", "10% Off"
    discount_type = Column(Enum(DiscountType), nullable=False)
    value = Column(Numeric(10, 2), nullable=False)  # percentage (0-100) or fixed amount

    # Relationships
    session = relationship("Session", back_populates="discounts")
    participant = relationship("Participant", back_populates="discounts")

    def __repr__(self):
        target = (
            f"participant={self.participant_id}"
            if self.participant_id
            else "entire bill"
        )
        return f"<Discount(name={self.name}, type={self.discount_type}, value={self.value}, {target})>"
