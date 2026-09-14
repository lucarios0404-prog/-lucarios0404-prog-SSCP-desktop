from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class VaccineRecord(Base):
    __tablename__ = "vaccine_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)

    vaccine_name = Column(String, nullable=False, index=True) # Hepatitis B, Tétanos, Influenza, COVID, etc.
    dose = Column(String, default="1ra Dosis") # 1ra Dosis, 2da Dosis, Refuerzo, Única
    application_date = Column(Date, nullable=False)
    next_due_date = Column(Date, nullable=True) # Próximo refuerzo
    lot_number = Column(String, nullable=True) # Lote del biológico
    administered_by = Column(String, nullable=True) # Quien administró
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    patient = relationship("Patient", backref="vaccines")
