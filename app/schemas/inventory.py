from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class InventoryItemBase(BaseModel):
    name: str
    category: str = "Medicamento"
    description: Optional[str] = None
    stock: int = 0
    min_stock: int = 5
    unit: str = "Unidad"
    price: float = 0.0

class InventoryItemCreate(InventoryItemBase):
    pass

class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    stock: Optional[int] = None
    min_stock: Optional[int] = None
    unit: Optional[str] = None
    price: Optional[float] = None

class InventoryItemOut(InventoryItemBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class InventoryMovementCreate(BaseModel):
    inventory_item_id: int
    type: str # in, out, adjustment
    quantity: int
    notes: Optional[str] = None

class InventoryMovementOut(BaseModel):
    id: int
    inventory_item_id: int
    user_id: Optional[int] = None
    type: str
    quantity: int
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
