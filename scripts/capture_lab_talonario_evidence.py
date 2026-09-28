import time
import os
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\396df109-072f-4b03-b774-25c19c92507d"

def capture_evidence():
    print("Iniciando captura de evidencia visual con Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 960})
        page = context.new_page()

        # 1. Login
        page.goto('http://127.0.0.1:8080/login')
        page.fill('input[name="username"]', 'admin@sscp.com')
        page.fill('input[name="password"]', 'password123')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        print("[OK] Sesion iniciada")

        # 2. Captura: /lab-results (Checklist directo al hacer clic en Laboratorios)
        page.goto('http://127.0.0.1:8080/lab-results')
        page.wait_for_load_state('networkidle')
        time.sleep(1)
        path1 = os.path.join(ARTIFACT_DIR, 'v120_lab_checklist_direct.png')
        page.screenshot(path=path1, full_page=True)
        print(f"[OK] Captura 1 guardada: {path1}")

        # 3. Captura: /lab-results con paciente seleccionado y varios analisis marcados
        page.goto('http://127.0.0.1:8080/lab-results?patient_id=1')
        page.wait_for_load_state('networkidle')
        time.sleep(0.5)

        # Marcar algunos checkboxes de paneles
        test_inputs = page.query_selector_all('input[type="checkbox"][name="tests"]')
        for i, cb in enumerate(test_inputs[:6]):
            cb.check()
        
        # Escribir indicacion
        page.fill('input[name="clinical_indication"]', 'Evaluación metabólica preventiva y perfil lipídico')
        time.sleep(1)

        path2 = os.path.join(ARTIFACT_DIR, 'v120_lab_checklist_patient_selected.png')
        page.screenshot(path=path2, full_page=True)
        print(f"[OK] Captura 2 guardada: {path2}")

        # 4. Captura: /lab-results/orders (Listado con boton Talonario y 3 pestañas)
        page.goto('http://127.0.0.1:8080/lab-results/orders')
        page.wait_for_load_state('networkidle')
        time.sleep(1)
        path3 = os.path.join(ARTIFACT_DIR, 'v120_lab_orders_list_talonario.png')
        page.screenshot(path=path3, full_page=True)
        print(f"[OK] Captura 3 guardada: {path3}")

        # 5. Captura: /lab-results/orders/{id} (Ficha de la orden con boton de Talonario)
        # Obtener primer enlace de detalle
        order_links = page.query_selector_all('a[href^="/lab-results/orders/"]')
        for link in order_links:
            href = link.get_attribute('href')
            if href and '/pdf' not in href and href != '/lab-results/orders':
                page.goto(f'http://127.0.0.1:8080{href}')
                page.wait_for_load_state('networkidle')
                time.sleep(1)
                path4 = os.path.join(ARTIFACT_DIR, 'v120_lab_order_talonario_view.png')
                page.screenshot(path=path4, full_page=True)
                print(f"[OK] Captura 4 guardada: {path4}")
                break

        browser.close()
        print("=== TODAS LAS CAPTURAS COMPLETADAS EXITOSAMENTE ===")

if __name__ == "__main__":
    capture_evidence()
