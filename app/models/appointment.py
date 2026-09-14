from sqlalchemy import Column, Integer, String, Date, Time, Text, DateTime, ForeignKey, Boolean
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
    
    sede_origen = Column(String, default="local")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    patient = relationship("Patient", backref="appointments")
    doctor = relationship("User", backref="appointments")
