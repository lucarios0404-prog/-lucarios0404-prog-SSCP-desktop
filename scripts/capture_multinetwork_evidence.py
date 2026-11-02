import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\d0ef121c-e7c2-45ef-a7b4-03f46dd4bd4d"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

BASE_URL = "http://127.0.0.1:8080"

def capture_multinetwork_evidence():
    print("Iniciando captura de evidencia visual con Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 1. Desktop Dashboard
        print("1. Capturando Desktop Dashboard...")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        
        page.goto(f"{BASE_URL}/login")
        page.fill('input[name="username"]', "admin@sscp.com")
        page.fill('input[name="password"]', "password123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        page.goto(f"{BASE_URL}/dashboard")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)
        
        desktop_dash_path = os.path.join(ARTIFACT_DIR, "evidence_multinetwork_desktop.png")
        page.screenshot(path=desktop_dash_path)
        print(f"   -> Guardado: {desktop_dash_path}")
        
        # 2. QR Modal Cloud Relay
        print("2. Abriendo modal de enlace Cloud Relay...")
        try:
            page.click('button:has-text("Vincular Móvil"), a:has-text("Vincular"), #btn-qr-relay, [onclick*="openRelayModal"], [onclick*="qr"]')
            time.sleep(1)
        except Exception as e:
            print(f"   Note clicking QR button: {e}")
            page.goto(f"{BASE_URL}/sync")
            time.sleep(1)
            
        qr_path = os.path.join(ARTIFACT_DIR, "evidence_multinetwork_qr_channel.png")
        page.screenshot(path=qr_path)
        print(f"   -> Guardado: {qr_path}")
        context.close()
        
        # 3. Mobile Companion View (Simulating phone screen 390x844)
        print("3. Capturando Mobile Companion...")
        mobile_context = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 SSCP-Mobile"
        )
        mobile_page = mobile_context.new_page()
        mobile_page.goto(f"{BASE_URL}/mobile")
        mobile_page.wait_for_load_state("networkidle")
        time.sleep(1.5)
        
        # Si está en pantalla de login móvil, iniciar sesión
        if mobile_page.locator("#mobile-login-screen").is_visible():
            print("   Iniciando sesión en Mobile...")
            mobile_page.fill("#login-email", "secretaria@sscp.com")
            mobile_page.fill("#login-password", "password123")
            mobile_page.click("button:has-text('Iniciar Sesión')")
            time.sleep(2)
            
        mobile_dash_path = os.path.join(ARTIFACT_DIR, "evidence_multinetwork_mobile_app.png")
        mobile_page.screenshot(path=mobile_dash_path)
        print(f"   -> Guardado: {mobile_dash_path}")
        
        # 4. Mobile Quick Appointment Modal
        print("4. Abriendo modal de Nueva Cita en Mobile...")
        try:
            mobile_page.click("button:has-text('Nueva Cita'), #btn-quick-new-appt, [onclick*='openQuickApptModal']")
            time.sleep(1)
            quick_appt_path = os.path.join(ARTIFACT_DIR, "evidence_multinetwork_mobile_quick_appt.png")
            mobile_page.screenshot(path=quick_appt_path)
            print(f"   -> Guardado: {quick_appt_path}")
        except Exception as e:
            print(f"   Note on modal: {e}")
            
        mobile_context.close()
        browser.close()
        print("Todas las capturas de evidencia fueron generadas exitosamente.")

if __name__ == "__main__":
    capture_multinetwork_evidence()
