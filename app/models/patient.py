from sqlalchemy import Column, Integer, String, Date, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    document_id = Column(String, unique=True, index=True, nullable=True) # Cédula/DNI
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    blood_type = Column(String, nullable=True)
    allergies = Column(Text, nullable=True) # Alergias conocidas (ej. Penicilina, Sulfas, etc.)
    
    # Datos de contacto de emergencia
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String, nullable=True)
    
    # Estado de actividad y archivo clínico (Soft Delete / Gobernanza)
    is_active = Column(Boolean, default=True, index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_reason = Column(Text, nullable=True)
    archived_by_id = Column(Integer, nullable=True)

    # Relaciones de sincronización
    sede_origen = Column(String, default="local")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
