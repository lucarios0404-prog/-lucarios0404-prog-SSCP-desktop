from sqlalchemy import Column, Integer, String, Boolean, Text, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class LabResult(Base):
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True, index=True)

    test_name = Column(String, nullable=False, index=True) # Ej: Hemograma, Perfil Lipídico
    test_category = Column(String, default="General") # Hematología, Bioquímica, etc.
    result_date = Column(Date, nullable=False)
    summary_findings = Column(Text, nullable=False) # Hallazgos y valores
    is_abnormal = Column(Boolean, default=False) # Alerta si está fuera de rango
    file_path = Column(String, nullable=True) # Adjunto PDF/JPG

    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    patient = relationship("Patient", backref="lab_results")
    consultation = relationship("Consultation", backref="lab_results")
    recorded_by = relationship("User")
