from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    category = Column(String, default="Medicamento", index=True)
    description = Column(Text, nullable=True)
    stock = Column(Integer, default=0)
    min_stock = Column(Integer, default=5)
    unit = Column(String, default="Unidad")
    price = Column(Float, default=0.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    movements = relationship("InventoryMovement", back_populates="item", cascade="all, delete-orphan", order_by="desc(InventoryMovement.created_at)")

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Tipo: "in" (Entrada), "out" (Salida / Consumo), "adjustment" (Ajuste de inventario)
    type = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("InventoryItem", back_populates="movements")
    user = relationship("User")
