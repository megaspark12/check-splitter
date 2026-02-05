"""Item model for receipt items."""
import uuid
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Numeric
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship
from app.database import Base


class Item(Base):
    """An item from a receipt."""
    
    __tablename__ = "items"
    
    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(CHAR(36), ForeignKey("sessions.id"), nullable=False)
    name = Column(String(200), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    is_tax = Column(Boolean, default=False, nullable=False)
    is_tip_suggestion = Column(Boolean, default=False, nullable=False)
    position = Column(Integer, default=0, nullable=False)
    
    # Relationships
    session = relationship("Session", back_populates="items")
    assignments = relationship("ItemAssignment", back_populates="item", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Item(name={self.name}, price={self.price})>"
