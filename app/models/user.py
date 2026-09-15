from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)  # admin, doctor, secretaria
    permissions = Column(String, nullable=True)  # JSON array con permisos personalizados si aplica
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def has_permission(self, perm_key: str) -> bool:
        """Verifica si el usuario tiene un permiso específico por rol o personalización."""
        if self.role == "admin":
            return True
        # Si el permiso fue desactivado globalmente por el administrador, se bloquea el acceso
        from app.core.permissions import get_inactive_permission_keys
        if perm_key in get_inactive_permission_keys():
            return False
        # El rol secretaria nunca puede realizar actos médicos estrictos (consultas, recetas, licencias, referencias)
        if self.role == "secretaria" and perm_key in ["consultations", "prescriptions", "licenses", "references"]:
            return False
        if self.permissions:
            try:
                import json
                custom_perms = json.loads(self.permissions)
                if isinstance(custom_perms, list):
                    return perm_key in custom_perms
            except Exception:
                pass
        from app.core.permissions import DEFAULT_ROLE_PERMISSIONS
        return perm_key in DEFAULT_ROLE_PERMISSIONS.get(self.role, [])

