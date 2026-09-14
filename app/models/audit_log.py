from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class ClinicalAuditLog(Base):
    __tablename__ = "clinical_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False, index=True) # "consultation", "patient", "vital_sign", "prescription"
    entity_id = Column(Integer, nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False) # "create", "update", "delete"
    summary = Column(Text, nullable=False) # Resumen legible del cambio médico
    changes_json = Column(Text, nullable=True) # Datos anteriores y nuevos en JSON
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    patient = relationship("Patient", backref="audit_logs")
    user = relationship("User", foreign_keys=[user_id])
