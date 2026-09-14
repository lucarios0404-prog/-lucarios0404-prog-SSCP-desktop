from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class MedicalReference(Base):
    __tablename__ = "medical_references"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    referred_to_doctor_or_specialty = Column(String, nullable=False) # Ej. "Dr. Gómez / Cardiología"
    institution = Column(String, nullable=True) # Clínica / Hospital destino
    reason_for_referral = Column(Text, nullable=False) # Motivo de la derivación
    clinical_summary = Column(Text, nullable=True) # Resumen clínico del paciente
    notes = Column(Text, nullable=True)
    
    sede_origen = Column(String, default="local")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient", backref="medical_references")
    doctor = relationship("User", foreign_keys=[doctor_id])
