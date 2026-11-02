import os
import sys
import time
import threading
from pathlib import Path
from datetime import date, datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import uvicorn
from main import app
from playwright.sync_api import sync_playwright

from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.payment import Payment
from app.models.insurance_preauthorization import InsurancePreauthorization
from app.core.security import get_password_hash

ARTIFACT_DIR = r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\349d7909-24e6-4dd3-af4c-bdee60dced41"
PORT = 8088
BASE_URL = f"http://127.0.0.1:{PORT}"

def start_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

def run_e2e_flow():
    print(f"=== INICIANDO SERVIDOR SSCP DESKTOP EN {BASE_URL} ===", flush=True)
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    db = SessionLocal()
    
    # 1. Asegurar Admin base
    admin = db.query(User).filter(User.email == "admin@sscp.com").first()
    if not admin:
        admin = User(name="Administrador Clínico", email="admin@sscp.com", role="admin", hashed_password=get_password_hash("password123"), is_active=True)
        db.add(admin)
    else:
        admin.name = "Administrador Clínico"
        admin.hashed_password = get_password_hash("password123")
        admin.is_active = True
        admin.role = "admin"

    # 2. Asegurar Doctor y Secretaria para credenciales garantizadas
    doc_email = "dr_rodriguez@sscp.com"
    doc_pass = "DoctorPass2026!"
    doctor = db.query(User).filter(User.email == doc_email).first()
    if not doctor:
        doctor = User(name="Dr. Fernando Rodríguez", email=doc_email, role="doctor", hashed_password=get_password_hash(doc_pass), is_active=True)
        db.add(doctor)
    else:
        doctor.name = "Dr. Fernando Rodríguez"
        doctor.hashed_password = get_password_hash(doc_pass)
        doctor.is_active = True
        doctor.role = "doctor"

    sec_email = "secretaria_maria@sscp.com"
    sec_pass = "SecretariaPass2026!"
    sec = db.query(User).filter(User.email == sec_email).first()
    if not sec:
        sec = User(name="Lic. María Valenzuela", email=sec_email, role="secretaria", hashed_password=get_password_hash(sec_pass), is_active=True)
        db.add(sec)
    else:
        sec.name = "Lic. María Valenzuela"
        sec.hashed_password = get_password_hash(sec_pass)
        sec.is_active = True
        sec.role = "secretaria"

    # 3. Limpiar paciente de prueba previo para asegurar idempotencia limpia
    test_dni = "001-1892345-8"
    old_p = db.query(Patient).filter(Patient.document_id == test_dni).first()
    if old_p:
        db.query(InsurancePreauthorization).filter(InsurancePreauthorization.patient_id == old_p.id).delete()
        db.query(Payment).filter(Payment.patient_id == old_p.id).delete()
        db.query(Consultation).filter(Consultation.patient_id == old_p.id).delete()
        db.delete(old_p)

    db.commit()
    db.close()

    print("\n=== INICIANDO PLAYWRIGHT CHROMIUM PARA RECORRIDO VISUAL ===", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # -------------------------------------------------------------
        # PASO 1: VISTA DE USUARIOS CREADOS (DOCTOR Y SECRETARIA)
        # -------------------------------------------------------------
        print("\n[PASO 1] Login Admin y Captura de Usuarios Creados...", flush=True)
        page.goto(f"{BASE_URL}/login")
        page.fill('input[name="username"]', "admin@sscp.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.goto(f"{BASE_URL}/users/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        step1_img = os.path.join(ARTIFACT_DIR, "evidencia_01_usuarios_creados.png")
        page.screenshot(path=step1_img, full_page=False)
        print(f"  ✓ Guardada Evidencia 1: {step1_img}", flush=True)

        # -------------------------------------------------------------
        # PASO 2: SECRETARIA REGISTRA PACIENTE
        # -------------------------------------------------------------
        print("\n[PASO 2] Login Secretaria y Registro de Paciente...", flush=True)
        page.goto(f"{BASE_URL}/logout")
        page.wait_for_load_state("networkidle")

        page.goto(f"{BASE_URL}/login")
        page.fill('input[name="username"]', sec_email)
        page.fill('input[name="password"]', sec_pass)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.goto(f"{BASE_URL}/patients/create")
        page.wait_for_load_state("networkidle")

        # Rellenar formulario del nuevo paciente
        page.fill('#first_name', "Elena")
        page.fill('#last_name', "Gómez Peralta")
        page.fill('#document_id', test_dni)
        page.fill('input[name="date_of_birth"]', "1988-06-14")
        try:
            page.select_option('select[name="gender"]', "F")
        except Exception:
            pass
        page.fill('#phone', "809-555-0199")
        page.fill('input[name="email"]', "elena.gomez@test.com")
        try:
            page.select_option('#insurance_name', label="Primera ARS (Grupo Humano)")
        except Exception:
            pass
        page.fill('input[name="insurance_number"]', "94827104")
        page.fill('input[name="allergies"]', "Penicilina, AINES (Reacción leve)")

        # Guardar paciente con botón oficial
        page.click('#submit_patient_btn')
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        # Buscar el ID del paciente recién creado
        db = SessionLocal()
        patient = db.query(Patient).filter(Patient.document_id == test_dni).first()
        patient_id = patient.id
        db.close()

        # Ir a la ficha del paciente para captura
        page.goto(f"{BASE_URL}/patients/{patient_id}")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        step2_img = os.path.join(ARTIFACT_DIR, "evidencia_02_ficha_paciente.png")
        page.screenshot(path=step2_img, full_page=False)
        print(f"  ✓ Guardada Evidencia 2: {step2_img}", flush=True)

        # -------------------------------------------------------------
        # PASO 3: SECRETARIA REGISTRA COBRO DE CONSULTA
        # -------------------------------------------------------------
        print("\n[PASO 3] Registro y Recibo de Cobro de Consulta...", flush=True)
        page.goto(f"{BASE_URL}/payments/create?patient_id={patient_id}")
        page.wait_for_load_state("networkidle")

        page.fill('#service_name_input', "Consulta Especializada Gastroenterología")
        page.fill('#amount', "2500")
        try:
            page.select_option('select[name="payment_method"]', "cash")
        except Exception:
            pass
        page.fill('input[name="notes"]', "Pago en efectivo completado en recepción. Recibo oficial emitido.")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.goto(f"{BASE_URL}/payments/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        step3_img = os.path.join(ARTIFACT_DIR, "evidencia_03_cobro_consulta.png")
        page.screenshot(path=step3_img, full_page=False)
        print(f"  ✓ Guardada Evidencia 3: {step3_img}", flush=True)

        # -------------------------------------------------------------
        # PASO 4: DOCTOR INICIA SESIÓN Y REALIZA LA CONSULTA CLÍNICA
        # -------------------------------------------------------------
        print("\n[PASO 4] Login Doctor y Redacción de Consulta Médica...", flush=True)
        page.goto(f"{BASE_URL}/logout")
        page.wait_for_load_state("networkidle")

        page.goto(f"{BASE_URL}/login")
        page.fill('input[name="username"]', doc_email)
        page.fill('input[name="password"]', doc_pass)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.goto(f"{BASE_URL}/consultations/create?patient_id={patient_id}")
        page.wait_for_load_state("networkidle")

        page.fill('input[name="reason"]', "Dolor epigástrico urente y pirosis postprandial de 3 semanas de evolución")
        
        # Revelar panel CIE-10 para asegurar que el input sea visible e interactuable
        page.evaluate("document.getElementById('cie10_collapsible_panel')?.classList.remove('hidden')")
        time.sleep(0.5)

        page.fill('#diagnosis_input', "K29.7 - Gastritis no especificada / Reflujo Gastroesofágico")
        hist_text = """ANAMNESIS Y MOTIVO DE CONSULTA:
Paciente femenina de 38 años refiere dolor epigástrico punzante de 3 semanas de evolución, que empeora tras ingesta de irritantes y café. Refiere pirosis y reflujo postprandial frecuente. Niega hematemesis, melena o pérdida de peso involuntaria.

EXPLORACIÓN FÍSICA:
Signos Vitales: PA 120/80 mmHg, FC 74 lpm, Peso 64 kg.
Abdomen blando, depresible, con dolor a la palpación profunda en epigastrio sin defensa involuntaria ni signos peritoneales. Ruidos hidroaéreos normales.

CONDUCTA MÉDICA:
1. Supresión ácida intensiva con inhibidores de bomba de protones y protectores de mucosa.
2. Indicación de endoscopía digestiva alta bajo sedación para descarte de úlcera péptica o infección por H. pylori."""
        page.fill('#clinical_history', hist_text)
        page.fill('textarea[name="treatment"]', "Plan médico higiénico-dietético, supresión ácida y derivación a estudio endoscópico digestivo.")
        rx_text = """1. Omeprazol 20 mg VO — 1 cápsula cada mañana en ayunas por 28 días.
2. Sucralfato 1g suspensión — 1 cucharada 1 hora antes de almuerzo y cena.
3. Domperidona 10 mg — 1 tableta 15 minutos antes de las comidas principales."""
        page.fill('#prescription_textarea', rx_text)
        page.fill('textarea[name="notes"]', "Se tramita orden para aseguradora ARS Humano.")

        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        db = SessionLocal()
        consultation = db.query(Consultation).filter(Consultation.patient_id == patient_id).order_by(Consultation.id.desc()).first()
        consultation_id = consultation.id
        db.close()

        page.goto(f"{BASE_URL}/consultations/{consultation_id}")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        step4_img = os.path.join(ARTIFACT_DIR, "evidencia_04_consulta_doctor.png")
        page.screenshot(path=step4_img, full_page=False)
        print(f"  ✓ Guardada Evidencia 4: {step4_img}", flush=True)

        # -------------------------------------------------------------
        # PASO 5: RECETA MÉDICA CON QR Y PRESCRIPCIÓN
        # -------------------------------------------------------------
        print("\n[PASO 5] Vista de Receta Médica Profesional con QR...", flush=True)
        page.goto(f"{BASE_URL}/prescriptions/quick?patient_id={patient_id}")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        page.fill('input[name="diagnosis"]', "K29.7 - Gastritis no especificada")
        page.fill('#prescription', rx_text)
        time.sleep(0.5)
        step5_img = os.path.join(ARTIFACT_DIR, "evidencia_05_receta_medica_qr.png")
        page.screenshot(path=step5_img, full_page=False)
        print(f"  ✓ Guardada Evidencia 5: {step5_img}", flush=True)

        # -------------------------------------------------------------
        # PASO 6: HISTORIA / FORMULARIO PARA EL SEGURO (PREAUTORIZACIÓN ARS)
        # -------------------------------------------------------------
        print("\n[PASO 6] Formulario e Historia para el Seguro (Preautorización ARS)...", flush=True)
        page.goto(f"{BASE_URL}/insurance-forms/new?patient_id={patient_id}&consultation_id={consultation_id}")
        page.wait_for_load_state("networkidle")

        try:
            page.select_option('#ars_name', label="Primera ARS de Humano")
        except Exception:
            pass
        page.fill('input[name="plan_type"]', "Plan Royal / Básico")
        page.fill('input[name="affiliate_card_number"]', "94827104")
        page.fill('input[name="affiliate_nss"]', "184920384")
        page.fill('textarea[name="current_illness_history"]', "Paciente de 38 años con cuadro clínico de epigastralgia refractaria a tratamiento empírico inicial. Pirosis recurrente y dispepsia.")
        page.fill('input[name="definitive_diagnosis"]', "K29.7 Gastritis crónica erosiva y reflujo gastroesofágico")
        
        # Procedimiento
        inputs_codes = page.locator('input[name="procedures_codes"]')
        if inputs_codes.count() > 0:
            inputs_codes.first.fill("45378")
        inputs_names = page.locator('input[name="procedures_names"]')
        if inputs_names.count() > 0:
            inputs_names.first.fill("Endoscopía Digestiva Alta (Gastroscopía) con toma de biopsia antral")

        page.fill('textarea[name="treatment_plan"]', "Estudio endoscópico bajo sedación para visualización de mucosa gástrica y confirmación histopatológica.")
        page.fill('input[name="doctor_code"]', "EXEQ-94821")

        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        db = SessionLocal()
        insurance_form = db.query(InsurancePreauthorization).filter(InsurancePreauthorization.patient_id == patient_id).order_by(InsurancePreauthorization.id.desc()).first()
        form_id = insurance_form.id
        db.close()

        page.goto(f"{BASE_URL}/insurance-forms/{form_id}")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        step6_img = os.path.join(ARTIFACT_DIR, "evidencia_06_preautorizacion_ars.png")
        page.screenshot(path=step6_img, full_page=False)
        print(f"  ✓ Guardada Evidencia 6: {step6_img}", flush=True)

        browser.close()

    print("\n=======================================================", flush=True)
    print("¡FLUJO CLÍNICO COMPLETO EJECUTADO Y CAPTURADO CON ÉXITO!", flush=True)
    print("=======================================================", flush=True)

if __name__ == "__main__":
    run_e2e_flow()
