from sqlalchemy import Column, Integer, String, Date, Time, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_id = Column(Integer, ForeignKey("users.id"))
    
    date = Column(Date, index=True)
    start_time = Column(Time)
    end_time = Column(Time)
    
    reason = Column(String)
    status = Column(String, default="Pendiente") # Pendiente, Confirmada, Completada, Cancelada
    notes = Column(Text, nullable=True)
    
    is_recurring = Column(Boolean, default=False)
    
    # Sistema de Turno de Atención en Sala
    queue_number = Column(Integer, nullable=True, index=True) # Turno del día (ej. 1, 2, 3...)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True) # Talonario de Servicios
    price = Column(Float, nullable=True, default=0.0)

    sede_origen = Column(String, default="local")
    
    # WhatsApp recordatorio
    whatsapp_reminder_sent = Column(Boolean, default=False)
    whatsapp_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    patient = relationship("Patient", backref="appointments")
    doctor = relationship("User", backref="appointments")
    service = relationship("Service", backref="appointments")
