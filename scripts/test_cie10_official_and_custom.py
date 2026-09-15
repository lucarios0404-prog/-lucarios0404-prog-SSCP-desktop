import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal, Base, engine
from app.models.user import User
from app.models.patient import Patient
from app.models.cie10 import Cie10Code
from app.models.consultation import Consultation
from app.data.cie10_catalog import seed_cie10_catalog

def test_cie10_system():
    print("==================================================================")
    print("TEST: CATÁLOGO OFICIAL CIE-10, BÚSQUEDA Y CÓDIGOS PERSONALIZADOS")
    print("==================================================================")

    client = TestClient(app)
    db = SessionLocal()

    # 1. Asegurar creación de tablas y sembrado de catálogo oficial
    print("\n[1/6] Inicializando y verificando sembrado del catálogo oficial CIE-10...")
    Base.metadata.create_all(bind=engine)
    total_codes = seed_cie10_catalog(db)
    print(f"  [OK] Catálogo sembrado en base de datos. Total de códigos: {total_codes}")
    assert total_codes >= 100, "El catálogo oficial debe tener al menos 100 códigos oficiales precargados."

    # Verificar existencia de códigos oficiales clave
    for code_check in ["I10", "J00", "E11.9", "A09", "M54.5", "J45.9"]:
        item = db.query(Cie10Code).filter(Cie10Code.code == code_check).first()
        assert item is not None, f"El código oficial {code_check} debe existir en el catálogo."
        assert item.is_custom is False, f"El código {code_check} debe ser oficial (is_custom=False)."
    print("  [OK] Códigos oficiales clave (Hipertensión, Resfriado, Diabetes, etc.) verificados.")

    # 2. Login como médico
    doc_user = db.query(User).filter(User.role.in_(["doctor", "admin"])).first()
    assert doc_user is not None, "Debe existir un usuario doctor/admin"
    print(f"\n[2/6] Iniciando sesión como médico ({doc_user.email})...")
    res_login = client.post("/login", data={"username": doc_user.email, "password": "password123"}, follow_redirects=False)
    assert res_login.status_code in [200, 302, 303]
    doc_cookies = res_login.cookies
    print("  [OK] Sesión de médico activa.")

    # 3. Probar endpoint de búsqueda de CIE-10
    print("\n[3/6] Probando endpoint de búsqueda en vivo (/consultations/cie10/search)...")
    
    # Búsqueda por código exacto "I10"
    res_search_code = client.get("/consultations/cie10/search?q=I10", cookies=doc_cookies)
    assert res_search_code.status_code == 200
    results_code = res_search_code.json()
    assert len(results_code) > 0
    assert results_code[0]["code"] == "I10"
    assert "Hipertensión" in results_code[0]["description"]
    print("  [OK] Búsqueda por código 'I10' exitosa.")

    # Búsqueda por descripción en español "asma"
    res_search_desc = client.get("/consultations/cie10/search?q=asma", cookies=doc_cookies)
    assert res_search_desc.status_code == 200
    results_desc = res_search_desc.json()
    assert any("J45" in r["code"] for r in results_desc)
    print("  [OK] Búsqueda por descripción 'asma' exitosa.")

    # Búsqueda por término parcial "cefalea"
    res_search_part = client.get("/consultations/cie10/search?q=cefalea", cookies=doc_cookies)
    assert res_search_part.status_code == 200
    results_part = res_search_part.json()
    assert any("Cefalea" in r["description"] for r in results_part)
    print("  [OK] Búsqueda por síntoma 'cefalea' exitosa.")

    # 4. Probar creación de código/diagnóstico personalizado por el médico
    print("\n[4/6] Probando botón y endpoint de diagnóstico personalizado (/consultations/cie10/custom)...")
    custom_desc = "Síndrome de fatiga crónica post-infecciosa persistente"
    custom_code = "PERS-TEST-01"
    
    res_custom = client.post("/consultations/cie10/custom", data={
        "code": custom_code,
        "description": custom_desc,
        "chapter": "Medicina Interna Personalizada"
    }, cookies=doc_cookies)
    assert res_custom.status_code == 200
    custom_data = res_custom.json()
    assert custom_data["success"] is True
    assert custom_data["item"]["code"] == custom_code
    assert custom_data["item"]["description"] == custom_desc
    assert custom_data["item"]["is_custom"] is True
    print("  [OK] Diagnóstico personalizado guardado en base de datos.")

    # Verificar que ahora aparece en las búsquedas en vivo
    res_search_custom = client.get(f"/consultations/cie10/search?q={custom_code}", cookies=doc_cookies)
    assert res_search_custom.status_code == 200
    found_custom = res_search_custom.json()
    assert len(found_custom) > 0
    assert found_custom[0]["code"] == custom_code
    assert found_custom[0]["is_custom"] is True
    print("  [OK] El diagnóstico personalizado aparece disponible en el buscador en vivo.")

    # 5. Verificar elementos en las vistas HTML de consulta
    print("\n[5/6] Verificando elementos de UI en /consultations/create y /consultations/edit...")
    res_create_view = client.get("/consultations/create", cookies=doc_cookies)
    assert res_create_view.status_code == 200
    assert "Diagnóstico Clínico y Código CIE-10 Oficial" in res_create_view.text
    assert "Agregar Diagnóstico / Código Personalizado" in res_create_view.text
    assert "cie10_results_dropdown" in res_create_view.text
    assert "customCie10Modal" in res_create_view.text
    print("  [OK] /consultations/create contiene buscador, dropdown y modal de diagnósticos personalizados.")

    # 6. Guardar una consulta médica usando diagnósticos oficiales y personalizados
    print("\n[6/6] Guardando consulta médica con diagnósticos CIE-10 integrados...")
    patient = db.query(Patient).first()
    combined_diag = f"I10 - Hipertensión esencial (primaria); {custom_code} - {custom_desc}"
    
    res_post_consult = client.post("/consultations/create", data={
        "patient_id": patient.id,
        "reason": "Control de presión arterial y fatiga",
        "diagnosis": combined_diag,
        "treatment": "Losartán 50mg diario, reposo relativo",
        "prescription": "Losartán 50mg tabletas"
    }, cookies=doc_cookies, follow_redirects=False)
    assert res_post_consult.status_code == 303
    
    # Verificar en BD
    latest_consult = db.query(Consultation).filter(Consultation.patient_id == patient.id).order_by(Consultation.id.desc()).first()
    assert latest_consult is not None
    assert "I10" in latest_consult.diagnosis
    assert custom_code in latest_consult.diagnosis
    print("  [OK] Consulta guardada exitosamente con el diagnóstico combinado en BD.")

    print("\n==================================================================")
    print("¡TODAS LAS PRUEBAS DE CIE-10 OFICIAL Y PERSONALIZADO PASARON CON ÉXITO!")
    print("==================================================================")

if __name__ == "__main__":
    test_cie10_system()
