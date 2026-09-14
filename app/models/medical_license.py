from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class MedicalLicense(Base):
    __tablename__ = "medical_licenses"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    diagnosis = Column(Text, nullable=False) # Diagnóstico médico justificativo
    days_rest = Column(Integer, nullable=False, default=1) # Días de reposo médico
    start_date = Column(Date, nullable=False) # Fecha de inicio del reposo
    end_date = Column(Date, nullable=False) # Fecha de término del reposo
    
    workplace_or_school = Column(String, nullable=True) # Empresa / Escuela a quien va dirigido
    notes = Column(Text, nullable=True) # Indicaciones adicionales
    
    sede_origen = Column(String, default="local")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient", backref="medical_licenses")
    doctor = relationship("User", foreign_keys=[doctor_id])
