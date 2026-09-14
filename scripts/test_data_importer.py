"""
Verification script: Data Importer for 'Consulta Práctica' (MDB), CSV and Excel.
"""
import sys
import io
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.audit_log import ClinicalAuditLog
from app.services.data_importer import DataImporterService, split_name, parse_date

def test_importer_full():
    print("============================================================")
    print("INICIANDO PRUEBAS: IMPORTADOR DE DATOS DE CONSULTA PRÁCTICA")
    print("============================================================")

    # 1. Helper parsing tests
    print("\n[1/5] Probando funciones auxiliares de normalización...")
    first, last = split_name("Pérez, Juan Carlos")
    assert first == "Juan Carlos" and last == "Pérez", f"Error split_name: {first}, {last}"
    
    first2, last2 = split_name("María Rodríguez López")
    assert f"{first2} {last2}".strip() == "María Rodríguez López", f"Error split_name: {first2}, {last2}"
    
    d1 = parse_date("1985-06-15")
    d2 = parse_date("15/06/1985")
    assert d1.year == 1985 and d2.year == 1985
    print("  [OK] Normalización de nombres y fechas verificada.")

    # 2. CSV parsing and preview logic
    print("\n[2/5] Probando análisis de archivo CSV con pacientes y consultas...")
    sample_csv = """Nombre;Cedula;Fecha Nacimiento;Telefono;Genero;Diagnostico;Tratamiento;Historia
Carlos Manuel Benitez;V-18456789;1990-03-22;0414-1234567;Masculino;Hipertension Arterial Grado I;Losartan 50mg cada 12 horas;Paciente refiere cefalea matutina recurrente.
Elena Beatriz Ramos;V-22987654;1995-11-10;0424-7654321;Femenino;Rinitis Alergica Estacional;Cetirizina 10mg diario;Congestion nasal y estornudos frecuentes.
    """
    records = DataImporterService.parse_csv(sample_csv.encode("utf-8"))
    assert records[0]["first_name"] == "Carlos Manuel"
    assert records[0]["last_name"] == "Benitez"
    assert records[0]["document_id"] == "V-18456789"
    assert len(records[0]["consultations"]) == 1
    assert records[0]["consultations"][0]["diagnosis"] == "Hipertension Arterial Grado I"
    print(f"  [OK] {len(records)} pacientes y sus historias extraídos correctamente del CSV.")

    # 3. Database preview cross-referencing
    print("\n[3/5] Probando previsualización contra base de datos...")
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.role == "admin").first()
        assert admin_user, "No se encontró usuario admin"

        preview = DataImporterService.preview_data(records, db)
        assert preview["total_patients"] == 2
        assert preview["total_consultations"] == 2
        print(f"  [OK] Estadísticas de previsualización: {preview['new_patients']} nuevos, {preview['existing_patients']} existentes, {preview['total_consultations']} consultas.")

    # 4. Execute import transaction
    print("\n[4/5] Probando ejecución de importación en base de datos...")
    with SessionLocal() as db:
        res = DataImporterService.execute_import(records, db, doctor_id=admin_user.id)
        assert res["success"] is True
        print(f"  [OK] Resultado: {res['message']}")

        # Verify patient and consultation records created in DB
        p1 = db.query(Patient).filter(Patient.document_id == "V-18456789").first()
        assert p1 is not None, "El paciente Carlos Manuel Benitez no fue encontrado en DB"
        assert p1.phone == "0414-1234567"

        c1 = db.query(Consultation).filter(Consultation.patient_id == p1.id).all()
        assert len(c1) >= 1, "No se encontraron consultas asociadas al paciente"
        assert "Losartan" in (c1[0].treatment or "")
        print(f"  [OK] Paciente #{p1.id} e historial clínico verificados en base de datos.")

        # Test updating existing patient
        res_update = DataImporterService.execute_import(records, db, doctor_id=admin_user.id)
        assert res_update["updated_patients"] >= 2, "Los pacientes repetidos debieron ser actualizados"
        print(f"  [OK] Detección y actualización de pacientes existentes validada ({res_update['updated_patients']} actualizados).")

    # 5. HTTP Endpoints testing with TestClient
    print("\n[5/5] Probando endpoints HTTP del wizard (/patients/import)...")
    client = TestClient(app)

    # Login as admin
    login_res = client.post("/login", data={"username": "admin@sscp.com", "password": "password123"}, follow_redirects=False)
    assert login_res.status_code in [200, 302, 303], f"Login failed: {login_res.status_code}"
    cookies = login_res.cookies

    # GET /patients/import
    wizard_res = client.get("/patients/import", cookies=cookies)
    assert wizard_res.status_code == 200
    assert "Consulta Práctica" in wizard_res.text
    assert "dropArea" in wizard_res.text
    print("  [OK] GET /patients/import responde HTTP 200 con el wizard de importación.")

    # POST /patients/import/preview with CSV file
    file_bytes = io.BytesIO(sample_csv.encode("utf-8"))
    upload_res = client.post(
        "/patients/import/preview",
        files={"file": ("pacientes_consulta_practica.csv", file_bytes, "text/csv")},
        cookies=cookies
    )
    assert upload_res.status_code == 200, f"Upload preview failed: {upload_res.status_code} -> {upload_res.text}"
    preview_json = upload_res.json()
    assert preview_json["success"] is True
    assert "cache_token" in preview_json
    token = preview_json["cache_token"]
    print(f"  [OK] POST /patients/import/preview responde HTTP 200 con token de sesión.")

    # POST /patients/import/confirm with cache_token
    confirm_res = client.post(
        "/patients/import/confirm",
        data={"cache_token": token},
        cookies=cookies
    )
    assert confirm_res.status_code == 200, f"Confirm failed: {confirm_res.status_code} -> {confirm_res.text}"
    confirm_json = confirm_res.json()
    assert confirm_json["success"] is True
    print(f"  [OK] POST /patients/import/confirm ejecutado con éxito: {confirm_json['message']}")

    print("\n============================================================")
    print("RESULTADO: TODOS LOS TESTS DEL IMPORTADOR PASARON (100% OK)")
    print("============================================================")

if __name__ == "__main__":
    test_importer_full()
