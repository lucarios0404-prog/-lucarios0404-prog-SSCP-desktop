import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from main import app
from app.database import SessionLocal
from app.models.patient import Patient

ARTIFACT_DIR = r"C:\Users\Ecommerce\.gemini\antigravity-ide\brain\349d7909-24e6-4dd3-af4c-bdee60dced41"

def capture():
    print("Obteniendo HTML autenticado con TestClient...")
    client = TestClient(app)
    login_resp = client.post("/login", data={"username": "admin@sscp.com", "password": "password123"}, follow_redirects=False)
    assert login_resp.status_code == 302, "Login falló"

    db = SessionLocal()
    patient = db.query(Patient).filter(Patient.is_active == True).first()
    p_id = patient.id if patient else 1
    db.close()

    resp = client.get(f"/lab-results/orders/new?patient_id={p_id}")
    assert resp.status_code == 200, f"Error cargando formulario: {resp.status_code}"
    html_content = resp.text

    temp_html_path = ROOT_DIR / "scratch" / "temp_rendered_order_create.html"
    temp_html_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Asegurar que los assets estáticos carguen de forma absoluta o directa si están en /static
    # Reemplazar rutas relativas /static/ con file:// para Playwright
    static_abs = str((ROOT_DIR / "app" / "static").resolve()).replace("\\", "/")
    fixed_html = html_content.replace('href="/static/', f'href="file:///{static_abs}/')
    fixed_html = fixed_html.replace('src="/static/', f'src="file:///{static_abs}/')
    
    with open(temp_html_path, "w", encoding="utf-8") as f:
        f.write(fixed_html)

    print("Iniciando Playwright para capturar tarjeta de Sonografía...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(f"file:///{str(temp_html_path.resolve()).replace(chr(92), '/')}")
        page.wait_for_load_state("networkidle")

        # Localizar la tarjeta de Sonografía
        card = page.locator(".panel-card:has-text('Sonografía')")
        card.scroll_into_view_if_needed()
        card_screenshot_path = os.path.join(ARTIFACT_DIR, "sonografia_panel_actualizado.png")
        card.screenshot(path=card_screenshot_path)
        print(f"Captura guardada en: {card_screenshot_path}")

        browser.close()

    if temp_html_path.exists():
        temp_html_path.unlink()

if __name__ == "__main__":
    capture()
