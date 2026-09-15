import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from datetime import datetime
from app.database import SessionLocal
from app.models.patient import Patient

ARTIFACT_DIR = Path(r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\066cc96c-b60b-4a9b-b4a8-343b9a909b6a")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

def run_archive_visual_verification():
    # Asegurar un paciente archivado para la demostración visual
    db = SessionLocal()
    demo_patient = db.query(Patient).filter(Patient.document_id == "DEMO-ARCH-01").first()
    if not demo_patient:
        demo_patient = Patient(
            first_name="Carlos",
            last_name="Fernández de Castro",
            document_id="DEMO-ARCH-01",
            phone="809-555-8833",
            email="carlos.fernandez@ejemplo.com",
            blood_type="O+",
            allergies="Dipirona, Sulfamidas",
            is_active=False,
            archived_reason="Traslado de clínica / centro médico",
            archived_at=datetime.utcnow()
        )
        db.add(demo_patient)
        db.commit()
        db.refresh(demo_patient)
    else:
        demo_patient.is_active = False
        demo_patient.archived_reason = "Traslado de clínica / centro médico"
        db.commit()

    # Paciente activo para mostrar botón y modal de archivo
    active_patient = db.query(Patient).filter(Patient.document_id == "DEMO-ACT-01").first()
    if not active_patient:
        active_patient = Patient(
            first_name="Mariana",
            last_name="Gómez Reyes",
            document_id="DEMO-ACT-01",
            phone="809-555-1212",
            email="mariana.gomez@ejemplo.com",
            blood_type="A+",
            is_active=True
        )
        db.add(active_patient)
        db.commit()
        db.refresh(active_patient)
    else:
        active_patient.is_active = True
        db.commit()

    demo_id = demo_patient.id
    act_id = active_patient.id
    db.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # 1. Login como Admin para capturar pestaña de Archivados
        print("[1/4] Iniciando sesión como Administrador...")
        page.goto("http://127.0.0.1:8080/")
        page.wait_for_load_state("networkidle")
        page.fill('input[name="username"]', "admin@sscp.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # 2. Navegar a lista de archivados
        print("[2/4] Capturando listado de pacientes archivados (Admin)...")
        page.goto("http://127.0.0.1:8080/patients?status=archived")
        page.wait_for_load_state("networkidle")
        arch_tab_path = ARTIFACT_DIR / "admin_patients_archived_tab.png"
        page.screenshot(path=str(arch_tab_path), full_page=True)
        print(f"  [OK] Listado de archivados capturado: {arch_tab_path}")

        # 3. Abrir ficha del paciente archivado con banner y controles de restauración/borrado
        print("[3/4] Capturando ficha del paciente archivado (Gobernanza Admin)...")
        page.goto(f"http://127.0.0.1:8080/patients/{demo_id}")
        page.wait_for_load_state("networkidle")
        arch_view_path = ARTIFACT_DIR / "admin_patient_archived_view.png"
        page.screenshot(path=str(arch_view_path), full_page=True)
        print(f"  [OK] Ficha de paciente archivado capturada: {arch_view_path}")

        # 4. Abrir paciente activo y mostrar modal de archivo
        print("[4/4] Capturando modal de archivo en paciente activo...")
        page.goto(f"http://127.0.0.1:8080/patients/{act_id}")
        page.wait_for_load_state("networkidle")
        # Hacer clic en el botón Archivar
        page.click('button:has-text("Archivar")')
        page.wait_for_timeout(500)
        modal_path = ARTIFACT_DIR / "patient_archive_modal.png"
        page.screenshot(path=str(modal_path))
        print(f"  [OK] Modal de archivo interactivo capturado: {modal_path}")

        browser.close()
        print("\n[VERIFICACIÓN VISUAL COMPLETADA CON ÉXITO]")

if __name__ == "__main__":
    run_archive_visual_verification()
