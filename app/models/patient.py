from sqlalchemy import Column, Integer, String, Date, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    
    # ARS y Seguro Médico
    insurance_name = Column(String, default="Privado", index=True, nullable=True) # ARS (ej: Senasa, Primera ARS, Mapfre, etc.)
    insurance_number = Column(String, nullable=True) # Número de afiliado / póliza

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
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    doctor = relationship("User", foreign_keys=[doctor_id], backref="patients")

    @property
    def birth_date(self):
        return self.date_of_birth

    @property
    def mobile(self):
        return self.phone

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        from datetime import date
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def chronic_conditions(self):
        return "Ninguna"
