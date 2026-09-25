import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ARTIFACT_DIR = Path(r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\74ffd630-eeb9-4590-8437-5084b16b56a0")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

def run_visual_verification():
    print("=== [VERIFICACIÓN VISUAL] INICIANDO PRUEBAS E2E CON PLAYWRIGHT ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        # -------------------------------------------------------------
        # PARTE 1: VERIFICACIÓN EN ESCRITORIO (PANEL DE AJUSTES & QR)
        # -------------------------------------------------------------
        print("\n[1/4] Probando sesión de Administrador y Panel de Ajustes...")
        context_desktop = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context_desktop.new_page()

        # Login admin
        page.goto("http://127.0.0.1:8080/login")
        page.wait_for_load_state("networkidle")
        page.fill('input[name="username"]', "admin@sscp.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Ir a Ajustes
        page.goto("http://127.0.0.1:8080/settings")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Scroll hacia la tarjeta de conectividad móvil
        card = page.locator('text="Conectividad Móvil y APK (Doctor y Secretaría)"').locator('xpath=../..')
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(500)

        # Captura 1: Tarjeta con QR de APK
        img_settings_apk = ARTIFACT_DIR / "evidence_settings_mobile_qr.png"
        card.screenshot(path=str(img_settings_apk))
        print(f"  [OK] Captura guardada: {img_settings_apk.name}")

        # Probar cambio a pestaña "Abrir Web"
        btn_web = page.locator('#btn-qr-web')
        btn_web.click()
        page.wait_for_timeout(500)
        img_settings_web = ARTIFACT_DIR / "evidence_settings_web_qr.png"
        card.screenshot(path=str(img_settings_web))
        print(f"  [OK] Captura alternancia QR Web guardada: {img_settings_web.name}")

        page.close()
        context_desktop.close()

        # -------------------------------------------------------------
        # PARTE 2: VERIFICACIÓN EN DISPOSITIVO MÓVIL (DOCTOR & SECRETARIA)
        # -------------------------------------------------------------
        print("\n[2/4] Probando vista móvil responsiva (Viewport Android/iPhone: 390x844)...")
        context_mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Mobile Safari/537.36"
        )
        page_m = context_mobile.new_page()

        # Pantalla de Login Móvil
        page_m.goto("http://127.0.0.1:8080/mobile")
        page_m.wait_for_load_state("networkidle")
        img_mobile_login = ARTIFACT_DIR / "evidence_mobile_login.png"
        page_m.screenshot(path=str(img_mobile_login))
        print(f"  [OK] Captura pantalla Login Móvil: {img_mobile_login.name}")

        # Login como Doctor
        print("\n[3/4] Probando flujo y Dashboard del Doctor...")
        page_m.click('text="Doctor"')
        page_m.wait_for_timeout(300)
        page_m.click('button[type="submit"]')
        page_m.wait_for_load_state("networkidle")
        page_m.wait_for_timeout(1000)

        img_doc_dash = ARTIFACT_DIR / "evidence_mobile_doctor_dashboard.png"
        page_m.screenshot(path=str(img_doc_dash))
        print(f"  [OK] Captura Dashboard Doctor: {img_doc_dash.name}")

        # Logout Doctor
        page_m.on("dialog", lambda dialog: dialog.accept())
        page_m.click('button[title="Cerrar Sesión"]')
        page_m.wait_for_timeout(500)

        # Login como Secretaria
        print("\n[4/4] Probando flujo y Dashboard de la Secretaria...")
        page_m.click('text="Secretaria"')
        page_m.wait_for_timeout(300)
        page_m.click('button[type="submit"]')
        page_m.wait_for_load_state("networkidle")
        page_m.wait_for_timeout(1000)

        img_sec_dash = ARTIFACT_DIR / "evidence_mobile_secretary_dashboard.png"
        page_m.screenshot(path=str(img_sec_dash))
        print(f"  [OK] Captura Dashboard Secretaria: {img_sec_dash.name}")

        # Abrir modal Agendar Cita Express
        page_m.click('text="Agendar Cita Rápida"')
        page_m.wait_for_timeout(500)
        img_sec_modal = ARTIFACT_DIR / "evidence_mobile_quick_appt_modal.png"
        page_m.screenshot(path=str(img_sec_modal))
        print(f"  [OK] Captura Modal Agendamiento Secretaria: {img_sec_modal.name}")

        # Cerrar modal
        page_m.click('#modal-quick-appt button:has-text("×")')
        page_m.wait_for_timeout(300)

        page_m.close()
        context_mobile.close()
        browser.close()

    print("\n=================================================================")
    print("[SUCCESS] TODAS LAS VERIFICACIONES VISUALES COMPLETADAS CON ÉXITO")
    print("=================================================================")

if __name__ == "__main__":
    run_visual_verification()
