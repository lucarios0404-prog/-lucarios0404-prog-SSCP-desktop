from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    clinic_name = Column(String, default="Centro Médico SSCP")
    doctor_name = Column(String, default="Dr. Especialista")
    specialty = Column(String, default="Medicina General")
    phone = Column(String, default="809-555-0199")
    email = Column(String, default="contacto@sscp.local")
    address = Column(Text, default="Av. Principal #100, Santo Domingo")
    currency = Column(String, default="RD$")
    sede_name = Column(String, default="Sede Central")
    tailscale_ip = Column(String, nullable=True)
    sync_interval_minutes = Column(Integer, default=5)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
