from pydantic import BaseModel
from typing import Optional

class SettingBase(BaseModel):
    clinic_name: str = "Centro Médico SSCP"
    doctor_name: Optional[str] = "Dr. Especialista"
    specialty: Optional[str] = "Medicina General"
    phone: Optional[str] = "809-555-0199"
    email: Optional[str] = "contacto@sscp.local"
    address: Optional[str] = "Av. Principal #100, Santo Domingo"
    currency: str = "RD$"
    sede_name: str = "Sede Central"
    tailscale_ip: Optional[str] = None
    sync_interval_minutes: int = 5

class SettingUpdate(SettingBase):
    pass

class SettingOut(SettingBase):
    id: int

    class Config:
        from_attributes = True
