from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class PermissionCatalog(Base):
    """Catálogo dinámico de permisos del sistema, gestionado por el Administrador."""
    __tablename__ = "permissions_catalog"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    label = Column(String, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=False, default="General")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
