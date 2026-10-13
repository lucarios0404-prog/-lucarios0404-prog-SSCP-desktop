import sys
from pathlib import Path
import re
import json

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from main import app, ensure_schema_migrations
from app.database import SessionLocal, engine
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.insurance_preauthorization import InsurancePreauthorization

def test_flow():
    print("=" * 70)
    print(">>> INICIANDO PRUEBAS DEL FORMULARIO UNIFICADO DE PRE-AUTORIZACIÓN ARS")
    print("=" * 70)

    # 1. Asegurar migraciones y tabla insurance_preauthorizations
    print("\n[PASO 1] Ejecutando migraciones de base de datos...")
    ensure_schema_migrations(engine)
    print("  -> Migraciones de esquema ejecutadas con éxito.")

    client = TestClient(app)

    # 2. Login
    print("\n[PASO 2] Autenticación en SSCP Desktop...")
    login_resp = client.post(
        "/login",
        data={"username": "admin@sscp.com", "password": "password123"},
        follow_redirects=False
    )
    assert login_resp.status_code == 302, f"Login falló: {login_resp.status_code}"
    print("  -> Autenticación OK.")

    # 3. Obtener paciente y consulta
    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.is_active == True).first()
        assert patient is not None, "No se encontró ningún paciente activo para la prueba"
        consultation = db.query(Consultation).filter(Consultation.patient_id == patient.id).first()
        p_id = patient.id
        c_id = consultation.id if consultation else None
        p_name = f"{patient.first_name} {patient.last_name}"
    finally:
        db.close()

    print(f"  -> Paciente de prueba seleccionado: #{p_id} {p_name}")

    # 4. Verificar vista de formulario nueva solicitud (/insurance-forms/new)
    print("\n[PASO 3] Verificando formulario unificado (/insurance-forms/new)...")
    url_new = f"/insurance-forms/new?patient_id={p_id}" + (f"&consultation_id={c_id}" if c_id else "")
    new_page_resp = client.get(url_new)
    assert new_page_resp.status_code == 200, f"Error cargando formulario: {new_page_resp.status_code}"
    html_new = new_page_resp.text
    assert "SeNaSa" in html_new, "No se encontró opción SeNaSa"
    assert "Primera ARS de Humano" in html_new, "No se encontró opción Humano"
    assert "SIMON" in html_new, "No se encontró campo de código SIMON"
    assert "Hoja Carta" in html_new, "No se encontró referencia a Hoja Carta"
    assert "patient_live_search" in html_new, "No se encontró el buscador en vivo de paciente"
    print("  -> Formulario verificado: Controles de SeNaSa, Humano, Códigos SIMON y buscador en vivo de paciente OK.")

    # 5. POST crear solicitud unificada
    print("\n[PASO 4] Creando solicitud unificada con datos clínicos reales...")
    form_payload = {
        "patient_id": p_id,
        "consultation_id": c_id if c_id else "",
        "ars_name": "SeNaSa (Régimen Contributivo)",
        "request_type": "Cirugía Electiva",
        "request_date": "2026-05-07",
        "health_center": "Centro Médico María Dolores",
        "is_traffic_accident": False,
        "affiliate_nss": "109283746",
        "affiliate_card_number": "001-992834-0",
        "contract_number": "884920",
        "plan_type": "Régimen Contributivo Básico",
        "symptoms_onset_date": "Hace 7 meses (cuadro de sangrado uterino anormal)",
        "current_illness_history": "Paciente femenina con cuadro de hipermenorrea y dolor pélvico crónico refractario a tratamiento farmacológico. Se evidencia miomatosis uterina sintomática de grandes elementos.",
        "personal_family_history": "Quirúrgicos: Apendicectomía a los 18 años. Gineco-obstétricos: G2 P2 C0 A0. Sin alergias medicamentosas.",
        "diagnostic_tests": "1. Sonografía Pélvica: Útero aumentado de tamaño con miomas intramurales de hasta 6.5 cm.\n2. Hemograma: Hb 10.8 g/dL, Plaquetas normales.\n3. Biopsia endometrial: Negativa para malignidad.",
        "presumptive_diagnosis": "Miomatosis Uterina Sintomática",
        "definitive_diagnosis": "D25.9 Leiomioma del útero, sin otra especificación",
        "secondary_diagnoses": "D50.0 Anemia por pérdida de sangre",
        "procedures_codes": ["68.4", "54.11"],
        "procedures_names": ["Histerectomía total abdominal", "Laparoscopía exploratoria con lisis de adherencias"],
        "treatment_plan": "Protocolo quirúrgico programado bajo anestesia general. Profilaxis antibiótica preoperatoria.",
        "doctor_code": "24241",
        "notes": "Procedimiento requerido a la brevedad para prevenir complicaciones hematológicas."
    }

    create_resp = client.post("/insurance-forms/new", data=form_payload, follow_redirects=False)
    assert create_resp.status_code == 303, f"Fallo al guardar formulario: {create_resp.status_code}"
    redirect_loc = create_resp.headers["location"]
    print(f"  -> Solicitud creada con éxito. Redirige a: {redirect_loc}")

    match = re.search(r"/insurance-forms/(\d+)", redirect_loc)
    assert match, f"No se pudo extraer el ID de la solicitud desde {redirect_loc}"
    form_id = int(match.group(1))

    # 6. GET Detalle de la Solicitud
    print(f"\n[PASO 5] Verificando vista de ficha de solicitud #{form_id}...")
    view_resp = client.get(f"/insurance-forms/{form_id}")
    assert view_resp.status_code == 200, f"Error cargando detalle: {view_resp.status_code}"
    html_view = view_resp.text
    assert "SeNaSa" in html_view
    assert "Histerectomía total abdominal" in html_view
    assert "68.4" in html_view
    assert "D25.9" in html_view
    print("  -> Ficha verificada: Diagnósticos, códigos SIMON, procedimientos y datos de ARS renderizados.")

    # 7. GET Listado general
    print("\n[PASO 6] Verificando presencia en listado general (/insurance-forms)...")
    list_resp = client.get("/insurance-forms")
    assert list_resp.status_code == 200
    assert f"/insurance-forms/{form_id}" in list_resp.text
    print("  -> Listado general verificado: Registro visible en la tabla con enlaces directos.")

    # 8. GET Generación de PDF Oficial en Hoja Carta
    print(f"\n[PASO 7] Verificando generación de PDF Oficial en Hoja Carta (/insurance-forms/{form_id}/pdf)...")
    pdf_resp = client.get(f"/insurance-forms/{form_id}/pdf")
    assert pdf_resp.status_code == 200, f"Error generando PDF: {pdf_resp.status_code}"
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-"), "El encabezado del archivo no es un PDF válido"
    assert len(pdf_resp.content) > 3000, f"El PDF generado es sospechosamente pequeño: {len(pdf_resp.content)} bytes"
    print(f"  -> PDF Oficial en Hoja Carta generado exitosamente ({len(pdf_resp.content)} bytes, Content-Type: application/pdf, Header: %PDF-1.4).")

    print("\n" + "=" * 70)
    print(">>> TODAS LAS PRUEBAS DEL FORMULARIO UNIFICADO DE PRE-AUTORIZACIÓN PASARON AL 100%")
    print("=" * 70)

if __name__ == "__main__":
    test_flow()
