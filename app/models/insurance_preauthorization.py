from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class InsurancePreauthorization(Base):
    __tablename__ = "insurance_preauthorizations"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True, index=True)

    # Entidad Aseguradora y Solicitud
    ars_name = Column(String, nullable=False, default="SeNaSa") # SeNaSa, Humano, Universal, Mapfre Salud, Monumental, Renacer, etc.
    request_type = Column(String, default="Cirugía Electiva / Procedimiento") # Cirugía Electiva, Ambulatorio, Tratamiento Médico
    request_date = Column(Date, nullable=False, default=func.current_date())
    health_center = Column(String, nullable=True) # Centro donde se realizará el procedimiento
    is_traffic_accident = Column(Boolean, default=False) # Accidente de tránsito: SI / NO

    # Datos del Afiliado / Póliza (pueden venir precargados del paciente o afinarse aquí)
    affiliate_nss = Column(String, nullable=True) # Número de Seguridad Social
    affiliate_card_number = Column(String, nullable=True) # Carnet / Póliza No.
    contract_number = Column(String, nullable=True) # Contrato No.
    plan_type = Column(String, nullable=True) # Plan (Básico, Royal, Máximo, etc.)

    # Cuadro Clínico / Historia Clínica
    symptoms_onset_date = Column(String, nullable=True) # ¿Desde qué fecha iniciaron los síntomas?
    current_illness_history = Column(Text, nullable=True) # Historia de la Enfermedad Actual
    personal_family_history = Column(Text, nullable=True) # Antecedentes Personales y Familiares
    diagnostic_tests = Column(Text, nullable=True) # Laboratorios y Estudios Especiales Realizados (Anexar resultados)

    # Diagnósticos
    presumptive_diagnosis = Column(String, nullable=True) # Diagnóstico Presuntivo
    definitive_diagnosis = Column(String, nullable=True) # Diagnóstico Definitivo (con código CIE-10)
    secondary_diagnoses = Column(Text, nullable=True) # Diagnósticos secundarios 1, 2, 3 (JSON o texto)

    # Procedimientos Solicitados (Códigos SIMON / CUPS)
    # Formato JSON: [{"code": "54.11", "procedure": "Laparoscopía diagnóstica"}, ...]
    procedures_json = Column(Text, nullable=True)

    # Tratamiento y Observaciones
    treatment_plan = Column(Text, nullable=True) # Tratamiento propuesto
    doctor_code = Column(String, nullable=True) # Código prestador ARS / Exequátur
    notes = Column(Text, nullable=True) # Observaciones adicionales

    # Metadatos
    sede_origen = Column(String, default="local")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relaciones
    patient = relationship("Patient", backref="insurance_preauthorizations")
    doctor = relationship("User", foreign_keys=[doctor_id])
    consultation = relationship("Consultation", backref="insurance_preauthorizations")
