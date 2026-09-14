from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PaymentBase(BaseModel):
    patient_id: int
    appointment_id: Optional[int] = None
    service_name: Optional[str] = "Consulta Médica General"
    amount: float
    discount: Optional[float] = 0.0
    total: float
    payment_method: Optional[str] = "cash"
    status: Optional[str] = "paid"
    receipt_number: Optional[str] = None
    notes: Optional[str] = None

class PaymentCreate(PaymentBase):
    pass

class PaymentOut(PaymentBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
