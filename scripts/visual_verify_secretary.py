import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = Path(r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\066cc96c-b60b-4a9b-b4a8-343b9a909b6a")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

def run_visual_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        print("[1/5] Cargando página de Login...")
        page.goto("http://127.0.0.1:8080/")
        page.wait_for_load_state("networkidle")

        # Login como secretaria usando el formulario
        print("[2/5] Iniciando sesión como Secretaria (secretaria@sscp.com)...")
        page.fill('input[name="username"]', "secretaria@sscp.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Captura Dashboard Secretaria
        dash_path = ARTIFACT_DIR / "sec_dashboard.png"
        page.screenshot(path=str(dash_path))
        print(f"  [OK] Dashboard capturado: {dash_path}")

        # Ir a listado de pacientes buscando a nuestro paciente con receta
        print("[3/5] Navegando a Expediente de Pacientes...")
        page.goto("http://127.0.0.1:8080/patients?q=RecetaSecretaria")
        page.wait_for_load_state("networkidle")
        patients_path = ARTIFACT_DIR / "sec_patients.png"
        page.screenshot(path=str(patients_path))
        print(f"  [OK] Listado de pacientes capturado: {patients_path}")

        # Abrir ficha del paciente
        print("[4/5] Abriendo ficha de paciente con receta...")
        patient_link = page.locator('a:has-text("Ficha")').first
        patient_link.click()
        page.wait_for_load_state("networkidle")

        patient_view_path = ARTIFACT_DIR / "sec_patient_view.png"
        page.screenshot(path=str(patient_view_path), full_page=True)
        print(f"  [OK] Ficha de paciente capturada (página completa): {patient_view_path}")

        # Verificar presencia de botones de impresión
        print_btns = page.locator('text="Imprimir Receta"').count()
        print(f"  --> Botones 'Imprimir Receta' encontrados en la vista: {print_btns}")

        # Ir a la consulta directamente en modo lectura
        view_ficha_link = page.locator('a:has-text("Ver Ficha")').first
        if view_ficha_link.count() > 0:
            print("[5/5] Abriendo detalle de consulta médica en modo lectura...")
            view_ficha_link.click()
            page.wait_for_load_state("networkidle")
            consultation_path = ARTIFACT_DIR / "sec_consultation_view.png"
            page.screenshot(path=str(consultation_path), full_page=True)
            print(f"  [OK] Detalle de consulta capturado: {consultation_path}")

        browser.close()
        print("\n¡Verificación visual completada exitosamente!")

if __name__ == "__main__":
    run_visual_verification()
