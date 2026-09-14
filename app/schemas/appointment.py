from pydantic import BaseModel
from typing import Optional
from datetime import date, time, datetime
from app.schemas.patient import Patient

class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int
    date: date
    start_time: time
    end_time: time
    reason: str
    status: Optional[str] = "Pendiente"
    notes: Optional[str] = None
    is_recurring: Optional[bool] = False

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentUpdate(AppointmentBase):
    pass

class Appointment(AppointmentBase):
    id: int
    sede_origen: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    patient: Optional[Patient] = None
    
    class Config:
        from_attributes = True
