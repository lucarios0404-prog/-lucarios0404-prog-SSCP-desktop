import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.template import ClinicalTemplate

def run_tests():
    print("============================================================")
    print("PROBANDO SISTEMA DE PLANTILLAS PARA LICENCIAS Y REFERENCIAS")
    print("============================================================")

    client = TestClient(app)

    # 1. Login como admin/médico
    login_res = client.post("/login", data={"username": "admin@sscp.com", "password": "password123"}, follow_redirects=False)
    assert login_res.status_code in [200, 302, 303], f"Login falló: {login_res.status_code}"
    cookies = login_res.cookies

    # 2. Verificar listado de plantillas categoría 'license'
    print("\n[1/6] Verificando plantillas de licencias (/templates?category=license)...")
    res_lic_tpl = client.get("/templates?category=license", cookies=cookies)
    assert res_lic_tpl.status_code == 200
    assert "Reposo Laboral" in res_lic_tpl.text
    assert "Síndrome Gripal" in res_lic_tpl.text
    assert "Autocompletado Inteligente" in res_lic_tpl.text
    print("  [OK] Plantillas de licencias médicas renderizadas y filtradas correctamente.")

    # 3. Verificar listado de plantillas categoría 'reference'
    print("\n[2/6] Verificando plantillas de referencias (/templates?category=reference)...")
    res_ref_tpl = client.get("/templates?category=reference", cookies=cookies)
    assert res_ref_tpl.status_code == 200
    assert "Cardiología" in res_ref_tpl.text
    assert "Cirugía General" in res_ref_tpl.text
    print("  [OK] Plantillas de cartas de referencia renderizadas y filtradas correctamente.")

    # 4. Verificar formulario de emisión de licencia (/licenses/create)
    print("\n[3/6] Verificando formulario de emisión de licencia (/licenses/create)...")
    res_lic_create = client.get("/licenses/create", cookies=cookies)
    assert res_lic_create.status_code == 200
    assert "Plantilla de Licencia / Reposo Médico" in res_lic_create.text
    assert "license_template_select" in res_lic_create.text
    assert "applyLicenseTemplate" in res_lic_create.text
    print("  [OK] Selector dinámico de plantillas presente en /licenses/create.")

    # 5. Verificar formulario de emisión de referencia (/references/create)
    print("\n[4/6] Verificando formulario de emisión de referencia (/references/create)...")
    res_ref_create = client.get("/references/create", cookies=cookies)
    assert res_ref_create.status_code == 200
    assert "Plantilla de Carta de Referencia / Interconsulta" in res_ref_create.text
    assert "reference_template_select" in res_ref_create.text
    assert "applyReferenceTemplate" in res_ref_create.text
    print("  [OK] Selector dinámico de plantillas presente en /references/create.")

    # 6. Probar emisión real de licencia médica con datos de plantilla
    print("\n[5/6] Emitiendo licencia médica generada con datos estructurados de plantilla...")
    db = SessionLocal()
    patient = db.query(Patient).first()
    assert patient is not None, "Debe existir al menos un paciente para la prueba."

    lic_data = {
        "patient_id": patient.id,
        "diagnosis": "Infección Respiratoria Aguda de Vías Aéreas Superiores / Síndrome Gripal",
        "days_rest": 3,
        "start_date": "2026-09-15",
        "end_date": "2026-09-17",
        "workplace_or_school": "Empresa / Gestión Humana",
        "notes": "Reposo médico domiciliario con aislamiento preventivo. Hidratación oral y tratamiento prescrito."
    }
    lic_res = client.post("/licenses/create", data=lic_data, cookies=cookies, follow_redirects=False)
    assert lic_res.status_code in [200, 302, 303], f"Error al emitir licencia: {lic_res.status_code}"
    print("  [OK] Licencia médica emitida con éxito.")

    # 7. Probar emisión real de carta de referencia con datos de plantilla
    print("\n[6/6] Emitiendo carta de referencia generada con datos de plantilla...")
    ref_data = {
        "patient_id": patient.id,
        "referred_to_doctor_or_specialty": "Especialista en Cardiología",
        "institution": "Centro Cardiovascular",
        "reason_for_referral": "Evaluación integral de riesgo cardiovascular y cifras tensionales",
        "clinical_summary": "Paciente hipertenso que amerita ecocardiograma y valoración especializada.",
        "notes": "Se anexan analíticas recientes."
    }
    ref_res = client.post("/references/create", data=ref_data, cookies=cookies, follow_redirects=False)
    assert ref_res.status_code in [200, 302, 303], f"Error al emitir referencia: {ref_res.status_code}"
    print("  [OK] Carta de referencia emitida con éxito.")

    db.close()

    print("\n============================================================")
    print("RESULTADO: TODAS LAS PRUEBAS DE PLANTILLAS PASARON CON ÉXITO")
    print("============================================================")

if __name__ == "__main__":
    run_tests()
