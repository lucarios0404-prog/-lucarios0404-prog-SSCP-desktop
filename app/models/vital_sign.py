from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class VitalSign(Base):
    __tablename__ = "vital_signs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True, index=True)

    weight_kg = Column(Float, nullable=True) # Peso en kg
    height_cm = Column(Float, nullable=True) # Altura en cm
    bmi = Column(Float, nullable=True) # IMC calculado
    systolic_bp = Column(Integer, nullable=True) # Presión sistólica
    diastolic_bp = Column(Integer, nullable=True) # Presión diastólica
    heart_rate = Column(Integer, nullable=True) # Frecuencia cardíaca (bpm)
    respiratory_rate = Column(Integer, nullable=True) # Frecuencia respiratoria
    temperature_c = Column(Float, nullable=True) # Temperatura °C
    oxygen_saturation = Column(Float, nullable=True) # SatO2 %
    glucose_mg_dl = Column(Float, nullable=True) # Glucosa mg/dL
    notes = Column(Text, nullable=True)

    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    patient = relationship("Patient", backref="vital_signs")
    consultation = relationship("Consultation", backref="vital_signs")
    recorded_by = relationship("User")
