from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
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
    clinical_history = Column(Text, nullable=True) # Historia clínica / Evolución médica unificada
    is_first_visit = Column(Boolean, default=False) # Primera visita / Apertura de expediente
    edit_version = Column(Integer, default=1) # Versión de edición de la historia clínica

    symptoms = Column(Text, nullable=True) # Síntomas / Anamnesis (retrocompatibilidad)
    physical_exam = Column(Text, nullable=True) # Examen físico (retrocompatibilidad)
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

    @property
    def display_clinical_history(self) -> str:
        """
        Devuelve la historia clínica unificada. Si es una consulta previa que no tenía
        clinical_history, ensambla dinámicamente symptoms, physical_exam y diagnosis sin pérdida.
        """
        if self.clinical_history and self.clinical_history.strip():
            return self.clinical_history.strip()
        parts = []
        if self.symptoms and self.symptoms.strip():
            parts.append(self.symptoms.strip())
        if self.physical_exam and self.physical_exam.strip():
            parts.append(f"EXAMEN FÍSICO:\n{self.physical_exam.strip()}")
        if self.diagnosis and self.diagnosis.strip():
            parts.append(f"DIAGNÓSTICO:\n{self.diagnosis.strip()}")
        return "\n\n".join(parts)

