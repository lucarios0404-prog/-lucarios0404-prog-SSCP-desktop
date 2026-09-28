import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient

def test_patient_autocomplete():
    print(">>> Probando /patients/autocomplete (Fase 2)...")
    client = TestClient(app)

    # 1. Login
    login_resp = client.post(
        "/login",
        data={"username": "admin@sscp.com", "password": "password123"},
        follow_redirects=False
    )
    assert login_resp.status_code == 302, f"Login falló: {login_resp.status_code}"

    # 2. Get a patient from DB
    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.is_active == True).first()
        if not patient:
            patient = Patient(first_name="Carlos", last_name="Santana", document_id="402-1234567-8", is_active=True)
            db.add(patient)
            db.commit()
            db.refresh(patient)
        p_name = patient.first_name
        p_doc = patient.document_id
    finally:
        db.close()

    # 3. Autocomplete by first_name
    print(f"Buscando por nombre: '{p_name}'...")
    res = client.get(f"/patients/autocomplete?q={p_name}")
    assert res.status_code == 200, f"Error en endpoint: {res.status_code}"
    items = res.json()
    assert isinstance(items, list)
    assert len(items) > 0, f"No se obtuvieron resultados para '{p_name}'"
    first = items[0]
    for key in ["id", "name", "first_name", "last_name", "document_id", "phone", "insurance_name", "gender"]:
        assert key in first, f"Falta clave '{key}' en resultado"
    print(f"  -> Encontrado: {first['name']} (DNI: {first['document_id']})")

    # 4. Autocomplete by document ID if available
    if p_doc:
        doc_part = p_doc[:4]
        print(f"Buscando por documento parcial: '{doc_part}'...")
        res_doc = client.get(f"/patients/autocomplete?q={doc_part}")
        assert res_doc.status_code == 200
        items_doc = res_doc.json()
        assert len(items_doc) > 0
        print(f"  -> Encontrado por DNI: {items_doc[0]['name']}")

    # 5. Verify excluded if archived
    db = SessionLocal()
    try:
        archived = Patient(first_name="ArchivadoTest", last_name="NoAparece", is_active=False)
        db.add(archived)
        db.commit()
        db.refresh(archived)
        archived_name = archived.first_name
    finally:
        db.close()

    res_archived = client.get(f"/patients/autocomplete?q={archived_name}")
    assert res_archived.status_code == 200
    assert len(res_archived.json()) == 0, "Los pacientes archivados NO deben aparecer en autocomplete"
    print("  -> Exclusión de pacientes archivados: CORRECTA")

    # 6. Check UI elements in create.html
    create_resp = client.get("/consultations/create")
    assert create_resp.status_code == 200
    html = create_resp.text
    assert "patient_live_search" in html
    assert "patient_search_dropdown" in html
    assert "fetchPatientSearchResults" in html
    print("  -> Componente UI de Live Search verificado en create.html: CORRECTO")

    print("\n>>> PRUEBAS DE FASE 2 (LIVE SEARCH AUTOCOMPLETE) EXITOSAS AL 100% <<<")

if __name__ == "__main__":
    test_patient_autocomplete()
