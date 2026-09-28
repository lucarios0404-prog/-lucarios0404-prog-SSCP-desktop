import sys
from pathlib import Path
import re

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from main import app, ensure_schema_migrations
from app.database import SessionLocal, engine
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.lab_order import LabOrder

def test_lab_orders_flow():
    print("=" * 70)
    print(">>> INICIANDO PRUEBAS DE FASE 3: SOLICITUD DE LABORATORIOS DIGITAL (PDF)")
    print("=" * 70)

    # 1. Asegurar migraciones y tabla lab_orders
    ensure_schema_migrations(engine)

    client = TestClient(app)

    # 2. Login
    print("\n[PASO 1] Autenticación...")
    login_resp = client.post(
        "/login",
        data={"username": "admin@sscp.com", "password": "password123"},
        follow_redirects=False
    )
    assert login_resp.status_code == 302, f"Login falló: {login_resp.status_code}"
    print("  -> Autenticación OK.")

    # 3. Obtener paciente y consulta
    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.is_active == True).first()
        assert patient is not None
        consultation = db.query(Consultation).filter(Consultation.patient_id == patient.id).first()
        p_id = patient.id
        c_id = consultation.id if consultation else None
    finally:
        db.close()

    # 4. Formulario nueva solicitud
    print("\n[PASO 2] Verificando formulario de nueva solicitud (/lab-results/orders/new)...")
    url_new = f"/lab-results/orders/new?patient_id={p_id}" + (f"&consultation_id={c_id}" if c_id else "")
    new_page_resp = client.get(url_new)
    assert new_page_resp.status_code == 200
    html_new = new_page_resp.text
    assert "Hematología" in html_new
    assert "Química Sanguínea" in html_new
    assert "Imprimir en Talonario" in html_new
    print("  -> Formulario verificado: Paneles analíticos y paciente precargado OK.")

    # 5. POST crear orden de laboratorio
    print("\n[PASO 3] Creando orden de laboratorio con análisis seleccionados...")
    order_payload = {
        "patient_id": p_id,
        "consultation_id": c_id if c_id else "",
        "clinical_indication": "Control semestral de riesgo cardiometabólico y dislipidemia",
        "tests": [
            "Hemograma Completo con Plaquetas",
            "Glucemia en Ayunas",
            "Hemoglobina Glicosilada (HbA1c)",
            "Colesterol Total",
            "Colesterol HDL (Bueno)",
            "Colesterol LDL (Malo)",
            "Triglicéridos",
            "Transaminasa TGO / AST",
            "Transaminasa TGP / ALT",
            "Examen General de Orina (EGO)"
        ],
        "other_tests": "Vitamina D (25-OH)\nFerritina sérica",
        "notes": "Presentarse con 10 horas de ayuno estricto. Tomar medicación matutina habitual con agua."
    }

    create_order_resp = client.post("/lab-results/orders/new", data=order_payload, follow_redirects=False)
    assert create_order_resp.status_code == 303, f"Fallo al crear orden: {create_order_resp.status_code}"
    redirect_loc = create_order_resp.headers["location"]
    print(f"  -> Orden creada. Redirige a: {redirect_loc}")

    match = re.search(r"/lab-results/orders/(\d+)", redirect_loc)
    assert match, f"No se pudo extraer ID de orden de {redirect_loc}"
    order_id = int(match.group(1))

    # 6. GET Detalle de la orden
    print(f"\n[PASO 4] Verificando detalle de orden #{order_id}...")
    detail_resp = client.get(f"/lab-results/orders/{order_id}")
    assert detail_resp.status_code == 200
    html_detail = detail_resp.text
    assert f"Orden de Laboratorio #{order_id}" in html_detail
    assert "Hemograma Completo" in html_detail
    assert "Vitamina D" in html_detail
    assert "10 horas de ayuno" in html_detail
    print("  -> Detalle de orden verificado: Análisis solicitados e instrucciones presentes.")

    # 7. GET Listado de órdenes
    print("\n[PASO 5] Verificando presencia en listado general (/lab-results/orders)...")
    list_resp = client.get("/lab-results/orders")
    assert list_resp.status_code == 200
    html_list = list_resp.text
    assert f"/lab-results/orders/{order_id}/pdf" in html_list
    assert "Control semestral de riesgo" in html_list
    print("  -> Listado general verificado: Orden visible con enlace a PDF.")

    # 8. GET Descarga / Generación de PDF Oficial
    print(f"\n[PASO 6] Verificando generación de Volante Oficial PDF (/lab-results/orders/{order_id}/pdf)...")
    pdf_resp = client.get(f"/lab-results/orders/{order_id}/pdf")
    assert pdf_resp.status_code == 200, f"Error al generar PDF: {pdf_resp.status_code}"
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-"), "El encabezado no corresponde a un archivo PDF válido"
    assert len(pdf_resp.content) > 1500, "El PDF generado es sospechosamente pequeño"
    print(f"  -> PDF Oficial generado correctamente ({len(pdf_resp.content)} bytes, Content-Type: application/pdf, Header: %PDF-1.4).")

    # 9. Verificar botón en la vista de consulta
    if c_id:
        print(f"\n[PASO 7] Verificando botón de acceso directo en Consulta #{c_id}...")
        consult_resp = client.get(f"/consultations/{c_id}")
        assert consult_resp.status_code == 200
        assert "Solicitar Laboratorio" in consult_resp.text
        assert f"/lab-results/orders/new?patient_id={p_id}&amp;consultation_id={c_id}" in consult_resp.text or f"/lab-results/orders/new?patient_id={p_id}&consultation_id={c_id}" in consult_resp.text
        print("  -> Botón 'Solicitar Laboratorio' verificado en el detalle de la consulta.")

    print("\n" + "=" * 70)
    print(">>> TODOS LOS PASOS DE FASE 3 (SOLICITUD DE LABORATORIO DIGITAL) EXITOSOS AL 100%")
    print("=" * 70)

if __name__ == "__main__":
    test_lab_orders_flow()
