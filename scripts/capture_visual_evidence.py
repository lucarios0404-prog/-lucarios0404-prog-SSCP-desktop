import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\396df109-072f-4b03-b774-25c19c92507d"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

BASE_URL = "http://127.0.0.1:8080"

def capture_all():
    print("Iniciando captura visual Playwright en", BASE_URL)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # 1. Login
        print("1. Accediendo al sistema...")
        page.goto(f"{BASE_URL}/login")
        page.fill('input[name="username"]', "admin@sscp.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # 2. Captura: Dashboard con nuevos badges de estación y sync
        print("2. Capturando Dashboard con badges...")
        page.goto(f"{BASE_URL}/dashboard")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        dash_path = os.path.join(ARTIFACT_DIR, "v120_dashboard_station.png")
        page.screenshot(path=dash_path, full_page=False)
        print("   Guardado:", dash_path)

        # 2b. Captura: Listado de Citas Médicas Blindado
        print("2b. Capturando Citas Médicas...")
        page.goto(f"{BASE_URL}/appointments")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        appt_path = os.path.join(ARTIFACT_DIR, "v120_appointments_fixed.png")
        page.screenshot(path=appt_path, full_page=False)
        print("   Guardado:", appt_path)

        # 2c. Captura: Pacientes con Live Search y Autocomplete
        print("2c. Capturando Pacientes con Live Search...")
        page.goto(f"{BASE_URL}/patients")
        page.wait_for_load_state("networkidle")
        try:
            page.fill('#patients_index_search', 'Carmen')
            time.sleep(0.5)
        except Exception:
            pass
        pat_path = os.path.join(ARTIFACT_DIR, "v120_patients_live_search.png")
        page.screenshot(path=pat_path, full_page=False)
        print("   Guardado:", pat_path)

        # 3. Captura: Centro de Sincronización con Tarjeta P2P Doctor <-> Secretaría
        print("3. Capturando Centro de Sincronización P2P...")
        page.goto(f"{BASE_URL}/sync")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        sync_path = os.path.join(ARTIFACT_DIR, "v120_sync_p2p_station.png")
        page.screenshot(path=sync_path, full_page=False)
        print("   Guardado:", sync_path)

        # 4. Captura: Creación de Historia Clínica Unificada + Autocomplete en vivo
        print("4. Capturando Creación de Historia Clínica Unificada...")
        page.goto(f"{BASE_URL}/consultations/create")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        # Interactuar con el buscador de paciente para mostrar el autocomplete
        try:
            page.fill('#patient_search_input', 'Carmen')
            time.sleep(0.5)
        except Exception:
            pass
        hc_create_path = os.path.join(ARTIFACT_DIR, "v120_unified_history_create.png")
        page.screenshot(path=hc_create_path, full_page=False)
        print("   Guardado:", hc_create_path)

        # 5. Captura: Solicitud de Laboratorios Digital (Checklist de paneles)
        print("5. Capturando Solicitud de Laboratorios Digital...")
        page.goto(f"{BASE_URL}/lab-results/orders/new")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        lab_create_path = os.path.join(ARTIFACT_DIR, "v120_lab_order_create.png")
        page.screenshot(path=lab_create_path, full_page=False)
        print("   Guardado:", lab_create_path)

        # 6. Captura: Expediente de Paciente y Bitácora de Auditoría Legal
        print("6. Capturando Expediente y Auditoría Clínica...")
        page.goto(f"{BASE_URL}/patients")
        page.wait_for_load_state("networkidle")
        # Ir al primer paciente
        try:
            first_view = page.locator('a[href*="/patients/"]').first
            if first_view:
                first_view.click()
                page.wait_for_load_state("networkidle")
                time.sleep(1)
        except Exception:
            page.goto(f"{BASE_URL}/patients/1")
            page.wait_for_load_state("networkidle")

        audit_path = os.path.join(ARTIFACT_DIR, "v120_patient_audit_log.png")
        page.screenshot(path=audit_path, full_page=False)
        print("   Guardado:", audit_path)

        # 7. Captura: Configuración de Rol de Estación y Red
        print("7. Capturando Configuración de Estación...")
        page.goto(f"{BASE_URL}/settings")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        settings_path = os.path.join(ARTIFACT_DIR, "v120_settings_station_role.png")
        page.screenshot(path=settings_path, full_page=False)
        print("   Guardado:", settings_path)

        # 8. Captura: Talonario Físico Preimpreso en Recetas Rápidas
        print("8. Capturando Emisión en Talonario Preimpreso...")
        page.goto(f"{BASE_URL}/prescriptions/quick")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        quick_path = os.path.join(ARTIFACT_DIR, "v120_prescriptions_talonario.png")
        page.screenshot(path=quick_path, full_page=False)
        print("   Guardado:", quick_path)

        browser.close()
        print("Todas las capturas visuales han sido completadas con éxito.")

if __name__ == "__main__":
    capture_all()
