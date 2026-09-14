import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.consultation import Consultation

def test_secretary_restriction():
    print("============================================================")
    print("PROBANDO RESTRICCIÓN DE CONSULTAS MÉDICAS PARA SECRETARIA")
    print("============================================================")

    client = TestClient(app)
    db = SessionLocal()

    # 1. Verificar modelo y permisos a nivel de objeto User
    print("\n[1/5] Verificando permisos del rol 'secretaria' en el modelo User...")
    sec_user = db.query(User).filter(User.role == "secretaria").first()
    assert sec_user is not None, "Debe existir un usuario con rol 'secretaria'."
    assert sec_user.has_permission("consultations") is False, "Secretaria NO debe tener permiso 'consultations'."
    assert sec_user.has_permission("prescriptions") is False, "Secretaria NO debe tener permiso 'prescriptions'."
    assert sec_user.has_permission("licenses") is False, "Secretaria NO debe tener permiso 'licenses'."
    assert sec_user.has_permission("references") is False, "Secretaria NO debe tener permiso 'references'."
    assert sec_user.has_permission("appointments") is True, "Secretaria SÍ debe tener permiso de 'appointments'."
    assert sec_user.has_permission("payments") is True, "Secretaria SÍ debe tener permiso de 'payments'."
    print("  [OK] Modelo User valida y bloquea permisos clínicos para el rol 'secretaria'.")

    # 2. Iniciar sesión como secretaria
    print(f"\n[2/5] Iniciando sesión web como {sec_user.email}...")
    login_res = client.post("/login", data={"username": sec_user.email, "password": "password123"}, follow_redirects=False)
    assert login_res.status_code in [200, 302, 303]
    sec_cookies = login_res.cookies
    print("  [OK] Sesión de secretaria iniciada correctamente.")

    # 3. Intentar acceder a rutas de creación y edición de consultas (debe dar HTTP 403)
    print("\n[3/5] Verificando bloqueo HTTP 403 en endpoints clínicos para secretaria...")
    
    # GET /consultations/create
    res_get_create = client.get("/consultations/create", cookies=sec_cookies)
    assert res_get_create.status_code == 403, f"Esperado 403, obtenido {res_get_create.status_code}"
    print("  [OK] GET /consultations/create -> HTTP 403 FORBIDDEN.")

    # POST /consultations/create
    patient = db.query(Patient).first()
    res_post_create = client.post("/consultations/create", data={
        "patient_id": patient.id,
        "reason": "Intento no autorizado"
    }, cookies=sec_cookies, follow_redirects=False)
    assert res_post_create.status_code == 403, f"Esperado 403, obtenido {res_post_create.status_code}"
    print("  [OK] POST /consultations/create -> HTTP 403 FORBIDDEN.")

    # GET /consultations
    res_list = client.get("/consultations", cookies=sec_cookies)
    assert res_list.status_code == 403, f"Esperado 403, obtenido {res_list.status_code}"
    print("  [OK] GET /consultations -> HTTP 403 FORBIDDEN.")

    # GET /consultations/{id}/edit
    consultation = db.query(Consultation).first()
    if consultation:
        res_edit = client.get(f"/consultations/{consultation.id}/edit", cookies=sec_cookies)
        assert res_edit.status_code == 403, f"Esperado 403, obtenido {res_edit.status_code}"
        print(f"  [OK] GET /consultations/{consultation.id}/edit -> HTTP 403 FORBIDDEN.")

    # 4. Verificar que en la UI no se muestren botones de consulta médica a la secretaria
    print("\n[4/5] Verificando ocultación de botones clínicos en la UI para la secretaria...")
    
    # Dashboard
    res_dash = client.get("/dashboard", cookies=sec_cookies)
    assert res_dash.status_code == 200
    assert "/consultations/create" not in res_dash.text, "Dashboard no debe contener enlace a /consultations/create para secretaria."
    print("  [OK] Dashboard: Oculto botón 'Nueva Consulta'.")

    # Ficha del Paciente
    res_p_view = client.get(f"/patients/{patient.id}", cookies=sec_cookies)
    assert res_p_view.status_code == 200
    assert f"/consultations/create?patient_id={patient.id}" not in res_p_view.text, "Ficha no debe mostrar botón de consulta a la secretaria."
    assert f"/prescriptions/quick?patient_id={patient.id}" not in res_p_view.text, "Ficha no debe mostrar receta rápida a la secretaria."
    assert f"/licenses/create?patient_id={patient.id}" not in res_p_view.text, "Ficha no debe mostrar licencia médica a la secretaria."
    assert f"/references/create?patient_id={patient.id}" not in res_p_view.text, "Ficha no debe mostrar referencia a la secretaria."
    print("  [OK] Ficha de Paciente: Ocultos botones de acción clínica (Consulta, Receta, Licencia, Referencia).")

    # Directorio de Pacientes
    res_p_index = client.get("/patients", cookies=sec_cookies)
    assert res_p_index.status_code == 200
    assert 'title="Nueva Consulta"' not in res_p_index.text, "Listado de pacientes no debe mostrar botón de Consulta a secretaria."
    print("  [OK] Directorio de Pacientes: Oculto acceso de consulta para secretaria.")

    # Citas Médicas
    res_app_index = client.get("/appointments", cookies=sec_cookies)
    assert res_app_index.status_code == 200
    assert 'title="Atender Consulta"' not in res_app_index.text, "Listado de citas no debe mostrar 'Atender' a la secretaria."
    print("  [OK] Citas Médicas: Oculto enlace 'Atender Consulta' para secretaria.")

    # 5. Verificar que el médico SÍ puede acceder a realizar consultas
    print("\n[5/5] Verificando que el rol 'doctor' o 'admin' conserva acceso pleno...")
    doc_user = db.query(User).filter(User.role == "doctor").first()
    if not doc_user:
        doc_user = db.query(User).filter(User.role == "admin").first()
    
    doc_login = client.post("/login", data={"username": doc_user.email, "password": "password123"}, follow_redirects=False)
    doc_cookies = doc_login.cookies

    res_doc_create = client.get("/consultations/create", cookies=doc_cookies)
    assert res_doc_create.status_code == 200, f"Médico debería acceder a /consultations/create (obtenido {res_doc_create.status_code})"
    print(f"  [OK] {doc_user.email} (Rol: {doc_user.role}) accede a /consultations/create exitosamente (HTTP 200).")

    db.close()

    print("\n============================================================")
    print("RESULTADO: RESTRICCIÓN DE CONSULTAS PARA SECRETARIA 100% OK")
    print("============================================================")

if __name__ == "__main__":
    test_secretary_restriction()
