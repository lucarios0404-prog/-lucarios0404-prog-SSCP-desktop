import sys
from pathlib import Path
import uuid
import json

# Asegurar UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Añadir raíz de sscp-desktop al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.core.deps import get_current_user, require_current_user, require_admin, require_permission
from app.core.permissions import AVAILABLE_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.security import verify_password

def run_tests():
    print("=" * 60)
    print("INICIANDO PRUEBAS: GESTIÓN DE USUARIOS Y CONTROL DE PERMISOS")
    print("=" * 60)

    db = SessionLocal()
    client = TestClient(app)

    try:
        # 1. Recuperar usuarios base
        admin_user = db.query(User).filter(User.role == "admin").first()
        doctor_user = db.query(User).filter(User.role == "doctor").first()
        sec_user = db.query(User).filter(User.role == "secretaria").first()

        assert admin_user is not None, "El usuario admin debe existir"
        assert doctor_user is not None, "El usuario doctor debe existir"
        assert sec_user is not None, "El usuario secretaria debe existir"

        # 2. Test: Modelo User y método has_permission()
        print("\n[1/5] Probando delimitación de permisos a nivel de Modelo...")
        assert admin_user.has_permission("users") == True
        assert admin_user.has_permission("settings") == True
        assert admin_user.has_permission("prescriptions") == True

        # Doctor tiene clínica y recetas, pero NO configuración ni usuarios
        assert doctor_user.has_permission("consultations") == True
        assert doctor_user.has_permission("prescriptions") == True
        assert doctor_user.has_permission("licenses") == True
        assert doctor_user.has_permission("users") == False
        assert doctor_user.has_permission("settings") == False
        print("  OK: Permisos por defecto de Médico validados (acceso a clínica, sin acceso a admin).")

        # Secretaria tiene citas y caja, pero NO recetas ni clínica avanzada
        assert sec_user.has_permission("appointments") == True
        assert sec_user.has_permission("patients") == True
        assert sec_user.has_permission("payments") == True
        assert sec_user.has_permission("prescriptions") == False
        assert sec_user.has_permission("licenses") == False
        assert sec_user.has_permission("users") == False
        assert sec_user.has_permission("settings") == False
        print("  OK: Permisos por defecto de Secretaria validados (recepción y caja, sin acceso a recetas ni admin).")

        # 3. Test: Endpoints protegidos para Admin (/users)
        print("\n[2/5] Probando protección de rutas y autorización por rol...")
        # Simular sesión Admin
        app.dependency_overrides[require_current_user] = lambda: admin_user
        app.dependency_overrides[require_admin] = lambda: admin_user

        resp_admin_users = client.get("/users")
        assert resp_admin_users.status_code == 200
        assert "Gestión de Usuarios" in resp_admin_users.text
        print("  OK: Administrador accede a /users (HTTP 200).")

        # Simular sesión Secretaria
        app.dependency_overrides[require_current_user] = lambda: sec_user
        # Para require_admin, usamos la función real que evalúa al usuario actual
        from app.core.deps import require_admin as real_require_admin
        from fastapi import HTTPException
        try:
            real_require_admin(current_user=sec_user)
            assert False, "Debe rechazar a la secretaria en require_admin"
        except HTTPException as e:
            assert e.status_code == 403
            print(f"  OK: Bloqueo de require_admin para Secretaria verificado (HTTP {e.status_code}: {e.detail}).")

        # Probar bloqueo en recetas para Secretaria
        from app.core.deps import require_permission as real_require_perm
        check_rx = real_require_perm("prescriptions")
        try:
            check_rx(current_user=sec_user)
            assert False, "Debe rechazar a la secretaria en recetas"
        except HTTPException as e:
            assert e.status_code == 403
            print(f"  OK: Bloqueo de recetas para Secretaria verificado (HTTP {e.status_code}: {e.detail}).")

        # Doctor sí pasa en recetas
        doc_rx_pass = check_rx(current_user=doctor_user)
        assert doc_rx_pass.id == doctor_user.id
        print("  OK: Autorización de recetas para Médico validada con éxito.")

        # 4. Test: Crear nuevo usuario desde el router /users/create
        print("\n[3/5] Probando creación de usuario nuevo con permisos personalizados...")
        app.dependency_overrides[require_current_user] = lambda: admin_user
        app.dependency_overrides[require_admin] = lambda: admin_user
        uid = uuid.uuid4().hex[:5]
        new_email = f"asistente_{uid}@sscp.local"
        
        create_resp = client.post("/users/create", data={
            "name": f"Asistente Especial {uid}",
            "email": new_email,
            "password": "PasswordSecret123",
            "role": "secretaria",
            "is_active": True,
            "use_custom_perms": "1",
            "custom_permissions": ["dashboard", "patients", "appointments", "inventory"]
        }, follow_redirects=False)

        assert create_resp.status_code == 303, f"Fallo al crear usuario: {create_resp.status_code}"

        created_u = db.query(User).filter(User.email == new_email).first()
        assert created_u is not None, "El usuario debe persistir en base de datos"
        assert created_u.role == "secretaria"
        assert verify_password("PasswordSecret123", created_u.hashed_password) == True
        assert created_u.has_permission("inventory") == True
        assert created_u.has_permission("payments") == False # Fue desmarcado en custom_permissions
        print(f"  OK: Usuario #{created_u.id} creado con permisos personalizados delimitados.")

        # 5. Test: Modificar usuario y permisos
        print("\n[4/5] Probando modificación de usuario y actualización de credenciales...")
        edit_resp = client.post(f"/users/{created_u.id}/edit", data={
            "name": f"Asistente Coordinador {uid}",
            "email": new_email,
            "password": "NewPassword456",
            "role": "secretaria",
            "is_active": "1",
            "use_custom_perms": "1",
            "custom_permissions": ["dashboard", "patients", "appointments", "payments", "inventory"]
        }, follow_redirects=False)

        assert edit_resp.status_code == 303
        db.refresh(created_u)
        assert created_u.name == f"Asistente Coordinador {uid}"
        assert verify_password("NewPassword456", created_u.hashed_password) == True
        assert created_u.has_permission("payments") == True
        print(f"  OK: Usuario #{created_u.id} actualizado y contraseña cambiada con éxito.")

        # 6. Test: Renderizado del Sidebar con permisos delimitados
        print("\n[5/5] Probando renderizado del Sidebar según rol...")
        # Renderizar dashboard con Secretaria: NO debe contener 'Receta Rápida' ni 'Plantillas Clínicas'
        app.dependency_overrides[get_current_user] = lambda: sec_user
        app.dependency_overrides[require_current_user] = lambda: sec_user
        dash_sec = client.get("/dashboard")
        assert dash_sec.status_code == 200
        assert "Receta Rápida" not in dash_sec.text
        assert "Plantillas Clínicas" not in dash_sec.text
        assert "Usuarios & Permisos" not in dash_sec.text
        assert "Citas Médicas" in dash_sec.text
        assert "Facturación & Pagos" in dash_sec.text
        print("  OK: Sidebar de Secretaria delimitado: Oculta recetas, plantillas y administración.")

        # Renderizar dashboard con Doctor: Debe contener 'Receta Rápida' pero NO 'Usuarios & Permisos'
        app.dependency_overrides[get_current_user] = lambda: doctor_user
        app.dependency_overrides[require_current_user] = lambda: doctor_user
        dash_doc = client.get("/dashboard")
        assert dash_doc.status_code == 200
        assert "Receta Rápida" in dash_doc.text
        assert "Plantillas" in dash_doc.text
        assert "Usuarios & Permisos" not in dash_doc.text
        print("  OK: Sidebar de Médico delimitado: Muestra clínica y prescripciones, oculta usuarios.")

        # Renderizar dashboard con Admin: Debe contener TODO
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[require_current_user] = lambda: admin_user
        dash_admin = client.get("/dashboard")
        assert dash_admin.status_code == 200
        assert "Usuarios & Permisos" in dash_admin.text
        assert "Receta Rápida" in dash_admin.text
        print("  OK: Sidebar de Administrador completo: Muestra todos los módulos y gestión de usuarios.")

        print("\n" + "=" * 60)
        print("RESULTADO: TODOS LOS TESTS DE USUARIOS Y PERMISOS PASARON (100% OK)")
        print("=" * 60)

    finally:
        app.dependency_overrides.clear()
        db.close()

if __name__ == "__main__":
    run_tests()
