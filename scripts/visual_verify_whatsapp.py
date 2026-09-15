"""
Verificación Visual y Captura de Evidencia: Módulo WhatsApp (1-Clic + Gateway QR)
Utiliza Playwright con Chrome para validar la interfaz de usuario en SSCP Desktop.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ARTIFACT_DIR = Path(r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\4cdadf9c-cbba-4aa5-9fc3-51d2377ba3d3")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

def run_visual_verification():
    print("Iniciando verificación visual con Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # 1. Login
        print("[1/6] Iniciando sesión como Administrador (admin@sscp.com)...")
        page.goto("http://127.0.0.1:8080/")
        page.wait_for_load_state("networkidle")
        page.fill('input[name="username"]', "admin@sscp.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # 2. Configuración: Módulo WhatsApp y Plantillas
        print("[2/6] Navegando a Configuración...")
        page.goto("http://127.0.0.1:8080/settings")
        page.wait_for_load_state("networkidle")
        settings_img = ARTIFACT_DIR / "whatsapp_settings_card.png"
        page.screenshot(path=str(settings_img), full_page=True)
        print(f"  ✓ Captura guardada: {settings_img}")

        # 3. Modal de Código QR
        print("[3/6] Abriendo modal de Código QR para vinculación de WhatsApp...")
        page.click('text="Vincular / Ver Código QR"')
        page.wait_for_timeout(1500)
        qr_modal_img = ARTIFACT_DIR / "whatsapp_qr_modal.png"
        page.screenshot(path=str(qr_modal_img))
        print(f"  ✓ Captura guardada: {qr_modal_img}")

        # Confirmar vinculación
        print("    Confirmando vinculación del Gateway...")
        page.on("dialog", lambda dialog: dialog.accept())
        page.click('button:has-text("Confirmar Vinculación")')
        page.wait_for_timeout(2000)

        # 4. Agenda de Citas
        print("[4/6] Navegando a Agenda de Citas Médicas...")
        page.goto("http://127.0.0.1:8080/appointments")
        page.wait_for_load_state("networkidle")
        appts_img = ARTIFACT_DIR / "whatsapp_appointments_agenda.png"
        page.screenshot(path=str(appts_img), full_page=False)
        print(f"  ✓ Captura guardada: {appts_img}")

        # 5. Modal de Recordatorio Individual
        print("[5/7] Abriendo modal de recordatorio individual de cita...")
        wa_btn = page.locator('#appointmentsTable button:has-text("Recordar"), #appointmentsTable button[title="Reenviar o ver mensaje"]').first
        if wa_btn.count() == 0:
            wa_btn = page.locator('button:has-text("Recordar"), button[title="Reenviar o ver mensaje"]').first
        if wa_btn.count() > 0:
            wa_btn.click()
            page.wait_for_timeout(1000)
            single_modal_img = ARTIFACT_DIR / "whatsapp_single_reminder_modal.png"
            page.screenshot(path=str(single_modal_img))
            print(f"  ✓ Captura guardada: {single_modal_img}")
            page.click('#singleWaModal button:has-text("Cancelar")')
            page.wait_for_timeout(500)

        # 6. Modal Masivo de WhatsApp
        print("[6/7] Abriendo modal masivo de recordatorios...")
        page.click('button:has-text("Recordatorios WhatsApp")')
        page.wait_for_timeout(1000)
        bulk_modal_img = ARTIFACT_DIR / "whatsapp_bulk_modal.png"
        page.screenshot(path=str(bulk_modal_img))
        print(f"  ✓ Captura guardada: {bulk_modal_img}")
        page.click('#bulkWaModal button:has-text("Cancelar")')
        page.wait_for_timeout(500)

        # 7. Vista del Paciente (Botón WhatsApp)
        print("[7/7] Navegando a Expediente del Paciente...")
        page.goto("http://127.0.0.1:8080/patients/1")
        page.wait_for_load_state("networkidle")
        patient_view_img = ARTIFACT_DIR / "whatsapp_patient_view.png"
        page.screenshot(path=str(patient_view_img), full_page=False)
        print(f"  ✓ Captura guardada: {patient_view_img}")

        browser.close()
        print("\n¡Verificación visual de WhatsApp completada con éxito!")

if __name__ == "__main__":
    run_visual_verification()
