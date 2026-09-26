import sys
from pathlib import Path
import json
import uuid

# Asegurar codificación UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Añadir directorio raíz de sscp-desktop
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.permission_catalog import PermissionCatalog
from app.core.deps import get_current_user, require_current_user, require_admin, require_permission
from app.core.permissions import (
    AVAILABLE_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    get_available_permissions,
    get_all_permissions,
    get_permissions_by_category,
    invalidate_permissions_cache,
)

def run_tests():
    print("=" * 70)
    print("TEST RIGUROSO: GESTION DE AREAS, PERMISOS Y EFECTO EN OTROS USUARIOS")
    print("=" * 70)

    db = SessionLocal()
    client = TestClient(app)

    try:
        # 1. Recuperar o verificar usuarios
        admin = db.query(User).filter(User.role == "admin").first()
        doctor = db.query(User).filter(User.role == "doctor").first()
        secretaria = db.query(User).filter(User.role == "secretaria").first()

        assert admin is not None, "El usuario admin debe existir"
        assert doctor is not None, "El usuario doctor debe existir"
        assert secretaria is not None, "El usuario secretaria debe existir"

        # Asegurar estado limpio inicial
        admin.permissions = None
        doctor.permissions = None
        secretaria.permissions = None
        db.commit()

        print(f"Usuarios encontrados: Admin (#{admin.id}), Doctor (#{doctor.id}), Secretaria (#{secretaria.id})")


        # -------------------------------------------------------------
        # FASE 1: Comportamiento Base por Rol
        # -------------------------------------------------------------
        print("\n[FASE 1] Verificando permisos base por rol predeterminado...")
        # Admin siempre tiene todo
        assert admin.has_permission("users") is True
        assert admin.has_permission("settings") is True
        assert admin.has_permission("consultations") is True

        # Doctor tiene clínica, pero no admin
        assert doctor.has_permission("consultations") is True
        assert doctor.has_permission("prescriptions") is True
        assert doctor.has_permission("vaccines") is True
        assert doctor.has_permission("users") is False
        assert doctor.has_permission("settings") is False

        # Secretaria tiene atención/caja, pero NUNCA actos médicos
        assert secretaria.has_permission("appointments") is True
        assert secretaria.has_permission("payments") is True
        assert secretaria.has_permission("consultations") is False
        assert secretaria.has_permission("prescriptions") is False
        assert secretaria.has_permission("users") is False
        print("  OK: Roles base delimitados correctamente segun politicas del sistema.")

        # -------------------------------------------------------------
        # FASE 2: Admin Quita Permiso Especifico a un Medico
        # -------------------------------------------------------------
        print("\n[FASE 2] Probando cuando el Administrador QUITA un permiso a un Medico...")
        # Tomamos los permisos del doctor y le quitamos 'consultations'
        doc_default_perms = [p for p in DEFAULT_ROLE_PERMISSIONS["doctor"] if p != "consultations"]
        doctor.permissions = json.dumps(doc_default_perms)
        db.commit()

        # El doctor ahora NO debe tener permiso 'consultations'
        assert doctor.has_permission("consultations") is False, "El doctor debe haber perdido el permiso 'consultations'"
        assert doctor.has_permission("prescriptions") is True, "El doctor conserva sus otros permisos"
        print("  OK: has_permission('consultations') devuelve False para el Medico modificado.")

        # Comprobar proteccion a nivel endpoint (403 Forbidden)
        app.dependency_overrides[require_current_user] = lambda: doctor
        perm_check = require_permission("consultations")
        from fastapi import HTTPException
        blocked = False
        try:
            perm_check(current_user=doctor)
        except HTTPException as e:
            blocked = True
            assert e.status_code == 403
            assert "consultations" in str(e.detail)
            print(f"  OK: Endpoint bloquea al Medico con HTTP 403 ({e.detail}).")
        assert blocked, "El endpoint debio bloquear al medico sin permiso."

        # Comprobar renderizado del Sidebar: 'Consultas' no debe aparecer para este medico
        app.dependency_overrides[get_current_user] = lambda: doctor
        dash_resp = client.get("/dashboard")
        assert dash_resp.status_code == 200
        # El enlace al modulo de consultas en sidebar es /consultations
        assert 'href="/consultations"' not in dash_resp.text
        print("  OK: Sidebar oculta el modulo 'Consultas' para el Medico restringido.")

        # Restaurar permisos del doctor
        doctor.permissions = None
        db.commit()
        assert doctor.has_permission("consultations") is True
        print("  OK: Permisos del Medico restaurados a predeterminados.")

        # -------------------------------------------------------------
        # FASE 3: Admin AGREGA Permiso a Secretaria (ej. Inventario)
        # -------------------------------------------------------------
        print("\n[FASE 3] Probando cuando el Administrador AGREGA un permiso a Secretaria...")
        sec_perms = list(DEFAULT_ROLE_PERMISSIONS["secretaria"]) + ["inventory"]
        secretaria.permissions = json.dumps(sec_perms)
        db.commit()

        assert secretaria.has_permission("inventory") is True
        print("  OK: has_permission('inventory') devuelve True para la Secretaria.")

        # Verificar que la secretaria ahora puede acceder a require_permission('inventory')
        inv_check = require_permission("inventory")
        allowed_user = inv_check(current_user=secretaria)
        assert allowed_user.id == secretaria.id
        print("  OK: Endpoint permite el acceso a Inventario para la Secretaria.")

        # Verificar en el sidebar
        app.dependency_overrides[get_current_user] = lambda: secretaria
        app.dependency_overrides[require_current_user] = lambda: secretaria
        dash_sec = client.get("/dashboard")
        assert dash_sec.status_code == 200
        assert 'href="/inventory"' in dash_sec.text
        print("  OK: Sidebar de Secretaria ahora muestra 'Inventario & Insumos'.")

        # Restaurar secretaria
        secretaria.permissions = None
        db.commit()

        # -------------------------------------------------------------
        # FASE 4: Admin DESACTIVA un Permiso Globalmente en el Catalogo
        # -------------------------------------------------------------
        print("\n[FASE 4] Probando cuando el Administrador DESACTIVA un permiso en el Catalogo...")
        app.dependency_overrides[require_current_user] = lambda: admin
        app.dependency_overrides[require_admin] = lambda: admin
        
        # Buscar el permiso 'vaccines' en la BD
        vaccine_perm = db.query(PermissionCatalog).filter(PermissionCatalog.key == "vaccines").first()
        assert vaccine_perm is not None, "El permiso vaccines debe existir en la BD"
        assert vaccine_perm.is_active is True

        # El doctor normalmente tiene acceso a vacunas
        assert doctor.has_permission("vaccines") is True

        # Administrador desactiva 'vaccines' llamando al endpoint /permissions/{id}/toggle
        toggle_resp = client.post(f"/permissions/{vaccine_perm.id}/toggle", follow_redirects=False)
        assert toggle_resp.status_code == 303
        db.refresh(vaccine_perm)
        assert vaccine_perm.is_active is False
        print("  OK: Administrador desactivo 'vaccines' en el catalogo.")

        # Verificar que inmediatamente el Medico PIERDE el acceso
        assert doctor.has_permission("vaccines") is False, "El medico NO debe tener acceso a un permiso desactivado"
        print("  OK: has_permission('vaccines') devuelve False en tiempo real para el Medico.")

        # Verificar que el endpoint de vacunas lo bloquea con 403
        app.dependency_overrides[require_current_user] = lambda: doctor
        vaccine_check = require_permission("vaccines")
        blocked_vaccine = False
        try:
            vaccine_check(current_user=doctor)
        except HTTPException as e:
            blocked_vaccine = True
            assert e.status_code == 403
            print(f"  OK: Acceso al modulo desactivado bloqueado con HTTP 403 ({e.detail}).")
        assert blocked_vaccine is True

        # Verificar que en el sidebar del medico ya no sale vacunas
        app.dependency_overrides[get_current_user] = lambda: doctor
        dash_doc = client.get("/dashboard")
        assert dash_doc.status_code == 200
        assert 'href="/vaccines"' not in dash_doc.text
        print("  OK: Sidebar del Medico oculta automaticamente el modulo desactivado 'Vacunas'.")

        # Reactivar permiso 'vaccines' para dejar el sistema limpio
        app.dependency_overrides[require_current_user] = lambda: admin
        app.dependency_overrides[require_admin] = lambda: admin
        toggle_back = client.post(f"/permissions/{vaccine_perm.id}/toggle", follow_redirects=False)
        assert toggle_back.status_code == 303
        db.refresh(vaccine_perm)
        assert vaccine_perm.is_active is True
        assert doctor.has_permission("vaccines") is True
        print("  OK: Permiso reactivado y acceso restablecido para los usuarios.")

        # -------------------------------------------------------------
        # FASE 5: Admin CREA una Nueva Area y Nuevo Permiso Organizado
        # -------------------------------------------------------------
        print("\n[FASE 5] Probando creacion de Nueva Area y Nuevo Permiso por el Administrador...")
        uid = uuid.uuid4().hex[:4]
        new_key = f"investigacion_{uid}"
        new_label = f"Ensayos Clinicos {uid}"
        new_category = "Investigacion & Bioetica"

        create_perm_resp = client.post("/permissions/create", data={
            "key": new_key,
            "label": new_label,
            "description": "Gestion de protocolos de ensayos clinicos y bioetica",
            "category": "General",
            "new_category": new_category,
        }, follow_redirects=False)

        assert create_perm_resp.status_code == 303
        created_perm = db.query(PermissionCatalog).filter(PermissionCatalog.key == new_key).first()
        assert created_perm is not None
        assert created_perm.category == new_category
        assert created_perm.label == new_label
        print(f"  OK: Permiso '{new_key}' creado bajo la nueva area '{new_category}'.")

        # Verificar que get_permissions_by_category() agrupa la nueva area
        grouped = get_permissions_by_category(db)
        assert new_category in grouped
        assert any(p["key"] == new_key for p in grouped[new_category])
        print(f"  OK: Nueva area '{new_category}' renderizada correctamente en la agrupacion del catalogo.")

        # Asignar este permiso al doctor
        doctor.permissions = json.dumps([new_key, "consultations", "patients"])
        db.commit()
        assert doctor.has_permission(new_key) is True
        print(f"  OK: Nuevo permiso '{new_key}' asignado y activo para el Medico.")

        # Limpieza: Desasignar y eliminar el permiso de prueba
        doctor.permissions = None
        db.commit()
        
        del_resp = client.post(f"/permissions/{created_perm.id}/delete", follow_redirects=False)
        assert del_resp.status_code == 303
        deleted_check = db.query(PermissionCatalog).filter(PermissionCatalog.id == created_perm.id).first()
        assert deleted_check is None
        print("  OK: Permiso temporal eliminado exitosamente del catalogo.")

        print("\n" + "=" * 70)
        print("TODAS LAS PRUEBAS PASARON EXITOSAMENTE (100% OK)")
        print("EL ADMINISTRADOR CONTROLA AREAS Y PERMISOS Y AFECTA DIRECTAMENTE A OTROS USUARIOS")
        print("=" * 70)

    finally:
        app.dependency_overrides.clear()
        invalidate_permissions_cache()
        db.close()

if __name__ == "__main__":
    run_tests()
