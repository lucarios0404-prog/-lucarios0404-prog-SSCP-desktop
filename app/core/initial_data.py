from sqlalchemy.orm import Session
from app.models.user import User
from app.models.setting import Setting
from app.core.security import get_password_hash

def seed_initial_data_if_empty(db: Session) -> None:
    """
    Inicializa datos fundamentales en una instalación limpia de SSCP Desktop:
    1. Usuario doctor y secretaria por defecto si no existen usuarios.
    2. Configuración inicial de la clínica si la tabla settings está vacía.
    """
    # 1. Sembrar usuarios si la tabla está vacía
    if db.query(User).count() == 0:
        default_users = [
            {
                "name": "Dr. Carlos Mendoza",
                "email": "doctor@sscp.com",
                "password": "password123",
                "role": "doctor",
            },
            {
                "name": "Ana Pérez (Recepción)",
                "email": "secretaria@sscp.com",
                "password": "password123",
                "role": "secretaria",
            },
        ]
        for u in default_users:
            new_user = User(
                name=u["name"],
                email=u["email"],
                hashed_password=get_password_hash(u["password"]),
                role=u["role"],
                is_active=True,
            )
            db.add(new_user)
        db.commit()
        print("[Initial Seed] Usuarios iniciales sembrados con éxito.")

    # 2. Sembrar settings si la tabla está vacía
    if db.query(Setting).count() == 0:
        default_setting = Setting(
            clinic_name="Centro Médico SSCP",
            doctor_name="Dr. Carlos Mendoza",
            specialty="Medicina General",
            phone="809-555-0199",
            email="contacto@sscp.local",
            address="Av. Principal #100",
            currency="RD$",
            sede_name="Sede Principal",
        )
        db.add(default_setting)
        db.commit()
        print("[Initial Seed] Configuración de clínica inicial creada con éxito.")
