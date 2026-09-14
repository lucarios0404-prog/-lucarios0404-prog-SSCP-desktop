import sys
from pathlib import Path

# Añadir raíz de sscp-desktop al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

def seed_users():
    db = SessionLocal()
    try:
        users_to_create = [
            {
                "name": "Dr. Carlos Mendoza",
                "email": "doctor@sscp.com",
                "password": "password123",
                "role": "doctor"
            },
            {
                "name": "Ana Pérez (Recepción)",
                "email": "secretaria@sscp.com",
                "password": "password123",
                "role": "secretaria"
            }
        ]

        print("Verificando y sembrando usuarios de demostración...")
        for u_data in users_to_create:
            existing = db.query(User).filter(User.email == u_data["email"]).first()
            if existing:
                print(f"  -> Usuario '{u_data['email']}' ya existe. Actualizando datos y rol...")
                existing.name = u_data["name"]
                existing.role = u_data["role"]
                existing.hashed_password = get_password_hash(u_data["password"])
                existing.is_active = True
            else:
                new_u = User(
                    name=u_data["name"],
                    email=u_data["email"],
                    hashed_password=get_password_hash(u_data["password"]),
                    role=u_data["role"],
                    is_active=True
                )
                db.add(new_u)
                print(f"  -> Creado: {u_data['name']} ({u_data['email']}) [Rol: {u_data['role']}]")
        
        db.commit()
        print("\nTodos los usuarios fueron registrados con éxito.")

        # Copiar / sincronizar con dist/SSCP-Desktop/data/sscp.db si existe
        dist_db = BASE_DIR / "dist" / "SSCP-Desktop" / "data" / "sscp.db"
        src_db = BASE_DIR / "data" / "sscp.db"
        if dist_db.parent.exists() and src_db.exists():
            import shutil
            shutil.copy2(src_db, dist_db)
            print(f"  -> Base de datos sincronizada con versión portable en {dist_db}")

    finally:
        db.close()

if __name__ == "__main__":
    seed_users()
