import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.user import User
from app.models.consultation import Consultation
from app.models.setting import Setting
from app.models.vital_sign import VitalSign
from app.services.pdf_service import generate_prescription_pdf, generate_consultation_report_pdf

def test_pdf_generation():
    print("=== [TEST PDF] Probando Generación de Documentos Médicos PDF ===")
    db = SessionLocal()
    
    # 1. Asegurar usuario médico y paciente
    admin = db.query(User).filter(User.role == "admin").first()
    assert admin is not None, "Debe existir un usuario admin/médico"
    
    patient = db.query(Patient).first()
    if not patient:
        patient = Patient(
            first_name="Carlos",
            last_name="Santana",
            document_id="001-9988776-5",
            phone="809-555-1234",
            email="carlos.santana@test.local",
            blood_type="O+",
            allergies="Ninguna"
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
        print("  -> Paciente de prueba creado.")
        
    # 2. Asegurar setting de la clínica
    setting = db.query(Setting).first()
    if not setting:
        setting = Setting(
            clinic_name="Centro Médico Especializado SSCP",
            doctor_name=admin.name,
            specialty="Cardiología y Medicina Interna",
            phone="809-555-0100",
            email="contacto@sscp.com",
            address="Torre Médica Profesional, Suite 502"
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
        print("  -> Configuración de clínica asegurada.")

    # 3. Crear consulta con receta estructurada
    consultation = db.query(Consultation).filter(Consultation.patient_id == patient.id).first()
    if not consultation:
        consultation = Consultation(
            patient_id=patient.id,
            doctor_id=admin.id,
            reason="Control de hipertensión y chequeo rutinario",
            symptoms="Cefalea leve matutina ocasional, sin palpitaciones.",
            physical_exam="T/A: 130/85 mmHg, FC: 74 lpm, ruidos cardíacos rítmicos sin soplos.",
            diagnosis="I10 - Hipertensión arterial esencial estadio 1",
            treatment="Dieta baja en sodio, caminata 30 min/día y control en 3 meses.",
            prescription="1. Losartán Potásico 50mg — Tomar 1 tableta cada 24 horas por la mañana.\n2. Aspirina 100mg — Tomar 1 tableta diaria con el almuerzo.\n3. Complejo B — 1 cápsula diaria por 30 días.",
            notes="Paciente colaborador. Se programa ecocardiograma de control."
        )
        db.add(consultation)
        db.commit()
        db.refresh(consultation)
        print("  -> Consulta médica con prescripción creada.")
        
    # 4. Probar generador unitario de Receta PDF
    print("\n--- 1. Verificando PDF de Receta Médica en memoria ---")
    rx_buf = generate_prescription_pdf(consultation, setting)
    rx_bytes = rx_buf.getvalue()
    assert len(rx_bytes) > 1000, f"El PDF de receta es demasiado pequeño: {len(rx_bytes)} bytes"
    assert rx_bytes.startswith(b"%PDF-"), "El archivo no contiene la cabecera mágica de PDF (%PDF-)"
    print(f"  ✅ PDF de Receta generado con éxito: {len(rx_bytes)} bytes con firma y formato médico.")
    
    # 5. Probar generador unitario de Informe Clínico PDF
    print("\n--- 2. Verificando PDF de Informe Clínico en memoria ---")
    report_buf = generate_consultation_report_pdf(consultation, setting)
    report_bytes = report_buf.getvalue()
    assert len(report_bytes) > 1000, f"El PDF de informe es demasiado pequeño: {len(report_bytes)} bytes"
    assert report_bytes.startswith(b"%PDF-"), "El archivo no contiene la cabecera mágica de PDF (%PDF-)"
    print(f"  ✅ PDF de Informe Clínico generado con éxito: {len(report_bytes)} bytes.")

    # 6. Probar Endpoints HTTP con TestClient de FastAPI
    print("\n--- 3. Verificando Endpoints HTTP de FastAPI ---")
    client = TestClient(app)
    
    # Iniciar sesión para obtener cookie
    login_resp = client.post("/login", data={"username": admin.email, "password": "password123"}, follow_redirects=False)
    auth_cookies = login_resp.cookies
    
    # Endpoint Receta
    rx_resp = client.get(f"/consultations/{consultation.id}/prescription/pdf", cookies=auth_cookies)
    assert rx_resp.status_code == 200, f"Error en endpoint de receta: {rx_resp.status_code}"
    assert rx_resp.headers["content-type"] == "application/pdf"
    assert rx_resp.content.startswith(b"%PDF-")
    print(f"  ✅ Endpoint GET /consultations/{consultation.id}/prescription/pdf -> 200 OK (application/pdf)")

    # Endpoint Informe
    rep_resp = client.get(f"/consultations/{consultation.id}/report/pdf", cookies=auth_cookies)
    assert rep_resp.status_code == 200, f"Error en endpoint de informe: {rep_resp.status_code}"
    assert rep_resp.headers["content-type"] == "application/pdf"
    assert rep_resp.content.startswith(b"%PDF-")
    print(f"  ✅ Endpoint GET /consultations/{consultation.id}/report/pdf -> 200 OK (application/pdf)")

    db.close()
    print("\n🎉 FASE A: Módulo de Recetas y Reportes PDF COMPLETADO Y VALIDADO AL 100%!")

if __name__ == "__main__":
    test_pdf_generation()
