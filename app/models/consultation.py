from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Consultation(Base):
    __tablename__ = "consultations"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)

    reason = Column(Text, nullable=False) # Motivo de consulta
    symptoms = Column(Text, nullable=True) # Síntomas / Anamnesis
    physical_exam = Column(Text, nullable=True) # Examen físico
    diagnosis = Column(Text, nullable=True) # Diagnóstico y código CIE-10
    treatment = Column(Text, nullable=True) # Plan terapéutico
    prescription = Column(Text, nullable=True) # Indicaciones / Receta
    notes = Column(Text, nullable=True) # Notas confidenciales

    # F3: Edición de historia médica y auditoría
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    edit_history = Column(Text, nullable=True) # Registro JSON de modificaciones (autor, fecha, motivo de cambio)

    sede_origen = Column(String, default="local")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient", backref="consultations")
    doctor = relationship("User", foreign_keys=[doctor_id], backref="consultations")
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    appointment = relationship("Appointment", backref="consultation")
