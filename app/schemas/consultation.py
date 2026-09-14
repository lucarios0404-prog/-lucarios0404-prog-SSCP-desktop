from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ConsultationBase(BaseModel):
    patient_id: int
    doctor_id: Optional[int] = None
    appointment_id: Optional[int] = None
    reason: str
    symptoms: Optional[str] = None
    physical_exam: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    notes: Optional[str] = None

class ConsultationCreate(ConsultationBase):
    pass

class ConsultationUpdate(BaseModel):
    reason: Optional[str] = None
    symptoms: Optional[str] = None
    physical_exam: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    prescription: Optional[str] = None
    notes: Optional[str] = None
    edit_reason: Optional[str] = None # Motivo de la modificación para F3

class ConsultationOut(ConsultationBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    edit_history: Optional[str] = None

    class Config:
        from_attributes = True
