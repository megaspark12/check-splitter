"""ItemAssignment model for mapping items to participants."""

import uuid

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship

from app.database import Base


class ItemAssignment(Base):
    """Assignment of an item to a participant."""

    __tablename__ = "item_assignments"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id = Column(CHAR(36), ForeignKey("items.id"), nullable=False)
    participant_id = Column(CHAR(36), ForeignKey("participants.id"), nullable=False)
    share_count = Column(Integer, default=1, nullable=False)

    # Relationships
    item = relationship("Item", back_populates="assignments")
    participant = relationship("Participant", back_populates="assignments")

    # Ensure unique assignment per item-participant pair
    __table_args__ = (
        UniqueConstraint("item_id", "participant_id", name="unique_item_participant"),
    )

    def __repr__(self):
        return f"<ItemAssignment(item_id={self.item_id}, participant_id={self.participant_id}, share_count={self.share_count})>"
