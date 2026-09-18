from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base


class LicenseConfig(Base):
    """Tabla local que almacena la configuracion de la licencia instalada."""
    __tablename__ = "license_configs"

    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String, default="offline")          # 'offline' | 'online'
    license_key = Column(Text, nullable=True)          # Clave de activacion
    machine_id = Column(String, nullable=True)         # ID de equipo en el que se activo
    doctor_name = Column(String, nullable=True)
    plan = Column(String, nullable=True)               # 'Standard', 'Pro', 'lifetime'
    activated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # None = lifetime
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
