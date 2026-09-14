from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class ClinicalTemplate(Base):
    __tablename__ = "clinical_templates"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Categorías: "prescription" (Recetas), "consultation" (Notas de consulta), "license" (Licencias), "reference" (Referencias)
    category = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    
    is_global = Column(Boolean, default=True) # Disponible para todos los médicos
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    doctor = relationship("User", foreign_keys=[doctor_id])
