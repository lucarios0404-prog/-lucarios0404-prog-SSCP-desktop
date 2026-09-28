from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class LabOrder(Base):
    __tablename__ = "lab_orders"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    order_date = Column(Date, nullable=False, default=func.current_date())
    clinical_indication = Column(String, nullable=True) # Diagnóstico presuntivo o indicación
    tests_requested = Column(Text, nullable=False) # JSON o texto con la lista de análisis requeridos
    notes = Column(Text, nullable=True) # Indicaciones de preparación (ej. ayuno de 8-12h)
    status = Column(String, default="solicitado") # solicitado, en_proceso, completado, cancelado

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient", backref="lab_orders")
    consultation = relationship("Consultation", backref="lab_orders")
    doctor = relationship("User")
