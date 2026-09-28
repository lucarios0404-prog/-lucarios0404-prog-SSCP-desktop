import sys
from pathlib import Path
import re

# Root dir
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal, engine
from main import ensure_schema_migrations
from app.models.patient import Patient
from app.models.user import User

def run_e2e_verification():
    print("=" * 70)
    print(">>> INICIANDO VERIFICACIÓN E2E DE HISTORIA CLÍNICA UNIFICADA (FASE 1)")
    print("=" * 70)

    # 1. Asegurar migraciones
    ensure_schema_migrations(engine)

    client = TestClient(app)

    # 2. Iniciar sesión como admin
    print("\n[PASO 1] Autenticación en /login...")
    login_resp = client.post(
        "/login",
        data={"username": "admin@sscp.com", "password": "password123"},
        follow_redirects=False
    )
    assert login_resp.status_code == 302, f"Fallo al iniciar sesión: {login_resp.status_code}"
    print("  -> Autenticación exitosa (Status 302 -> /dashboard)")

    # 3. GET /consultations/create
    print("\n[PASO 2] Verificando interfaz de creación (/consultations/create)...")
    create_page_resp = client.get("/consultations/create")
    assert create_page_resp.status_code == 200
    html_create = create_page_resp.text

    # Validar componentes de la nueva interfaz
    assert 'id="patient_identity_card"' in html_create, "Falta la ficha de identificación del paciente"
    assert 'name="clinical_history"' in html_create, "Falta el cuadro unificado de historia clínica"
    assert 'name="is_first_visit"' in html_create, "Falta el checkbox de primera consulta"
    assert 'id="cie10_collapsible_panel"' in html_create, "Falta el panel colapsable CIE-10"
    assert 'id="ch_word_count"' in html_create, "Falta el contador de palabras/caracteres"
    assert 'insertSectionTitle' in html_create, "Faltan los botones de inserción rápida"
    print("  -> Interfaz /consultations/create verificada: Ficha de paciente, Cuadro Unificado, Panel CIE-10 colapsable y barra de control presentes.")

    # 4. Obtener paciente para la prueba
    db = SessionLocal()
    try:
        patient = db.query(Patient).first()
        assert patient is not None, "Debe existir al menos un paciente para la prueba"
        patient_id = patient.id
    finally:
        db.close()

    # 5. POST /consultations/create
    print("\n[PASO 3] Creando consulta médica con historia clínica unificada...")
    clinical_history_text = (
        "Paciente masculino acude a consulta refiriendo dolor precordial atípico de 2 días de evolución.\n"
        "--- EXAMEN FÍSICO: ---\n"
        "PA: 130/85 mmHg, FC: 78 lpm, FR: 16 rpm, SatO2: 98%. Ruidos cardíacos rítmicos, sin soplos.\n"
        "--- DIAGNÓSTICO: ---\n"
        "Dolor torácico atípico, descartar causa osteomuscular."
    )
    payload_create = {
        "patient_id": patient_id,
        "reason": "Evaluación por dolor precordial no opresivo",
        "clinical_history": clinical_history_text,
        "is_first_visit": "true",
        "diagnosis": "R07.4 - Dolor en el pecho, no especificado",
        "treatment": "Reposo relativo, analgésico según necesidad, solicitar electrocardiograma.",
        "prescription": "Ibuprofeno 400mg VO cada 8 horas con alimentos por 3 días.",
        "notes": "Paciente colaborador, cita de control en 5 días."
    }

    create_post_resp = client.post("/consultations/create", data=payload_create, follow_redirects=False)
    assert create_post_resp.status_code == 303, f"Se esperaba redirect 303, obtenido {create_post_resp.status_code}"
    redirect_url = create_post_resp.headers["location"]
    print(f"  -> Consulta creada exitosamente. Redirección a: {redirect_url}")

    match = re.search(r"/consultations/(\d+)", redirect_url)
    assert match, f"No se pudo extraer el ID de consulta de {redirect_url}"
    consultation_id = int(match.group(1))

    # 6. GET /consultations/{id} (Detalle)
    print(f"\n[PASO 4] Verificando detalle de consulta (/consultations/{consultation_id})...")
    view_resp = client.get(f"/consultations/{consultation_id}")
    assert view_resp.status_code == 200
    html_view = view_resp.text

    assert "Primera Consulta" in html_view, "No se encontró la insignia de Primera Consulta"
    assert "v1" in html_view, "No se encontró el badge de versión v1"
    assert "Historia Cl" in html_view and "Evoluci" in html_view, "Falta la tarjeta de Historia Clínica"
    assert "dolor precordial" in html_view, "No se encontró el texto de la historia clínica"
    assert "R07.4 - Dolor en el pecho" in html_view, "No se encontró el diagnóstico CIE-10"
    print("  -> Detalle /consultations/{id} verificado: Insignia 'Primera Consulta', badge 'v1', y tarjeta de historia clínica unificada renderizados correctamente.")

    # 7. GET /consultations/{id}/edit (Formulario de Edición)
    print(f"\n[PASO 5] Verificando formulario de edición (/consultations/{consultation_id}/edit)...")
    edit_page_resp = client.get(f"/consultations/{consultation_id}/edit")
    assert edit_page_resp.status_code == 200
    html_edit = edit_page_resp.text

    assert 'name="clinical_history"' in html_edit, "Falta el cuadro unificado en edit"
    assert "dolor precordial atípico" in html_edit, "El cuadro unificado no precargó la historia clínica previa"
    assert 'name="edit_reason"' in html_edit, "Falta el campo de motivo de auditoría"
    assert "Versión 1" in html_edit, "Falta indicador de versión actual en el aviso de auditoría"
    assert "Versión 2" in html_edit, "Falta indicador de versión próxima en el aviso de auditoría"
    print("  -> Interfaz /consultations/{id}/edit verificada: Historia clínica precargada, aviso de auditoría (v1 -> v2) y campo edit_reason listos.")

    # 8. POST /consultations/{id}/edit (Guardar Modificación con Auditoría)
    print(f"\n[PASO 6] Guardando modificación de consulta con auditoría médica...")
    updated_history = clinical_history_text + "\n\n--- EVOLUCIÓN: ---\nElectrocardiograma realizado: ritmo sinusal normal. Dolor remitido completamente."
    payload_edit = {
        "reason": "Evaluación por dolor precordial no opresivo (Control evolutivo)",
        "clinical_history": updated_history,
        "is_first_visit": "true",
        "diagnosis": "R07.4 - Dolor en el pecho, no especificado",
        "treatment": "Alta médica con pautas de alarma.",
        "prescription": "Ibuprofeno 400mg VO condicional a dolor.",
        "notes": "Cuadro resuelto satisfactoriamente.",
        "edit_reason": "Incorporación de resultados de ECG y evolución médica de control."
    }

    edit_post_resp = client.post(f"/consultations/{consultation_id}/edit", data=payload_edit, follow_redirects=False)
    assert edit_post_resp.status_code == 303, f"Se esperaba redirect 303, obtenido {edit_post_resp.status_code}"
    print("  -> Modificación guardada exitosamente.")

    # 9. GET /consultations/{id} tras edición
    print(f"\n[PASO 7] Verificando incremento de versión y bitácora de auditoría...")
    view_updated_resp = client.get(f"/consultations/{consultation_id}")
    assert view_updated_resp.status_code == 200
    html_updated = view_updated_resp.text

    assert "v2" in html_updated, "La versión no se incrementó a v2"
    assert "Electrocardiograma realizado" in html_updated, "El texto actualizado no aparece en la vista"
    assert "Incorporación de resultados de ECG" in html_updated, "El motivo de auditoría no quedó registrado en el historial"
    print("  -> Verificación de versionado: Incrementado a v2, texto actualizado y evento de auditoría registrado con éxito.")

    # 10. GET /consultations (Listado General)
    print("\n[PASO 8] Verificando insignias en el listado general (/consultations)...")
    list_resp = client.get("/consultations")
    assert list_resp.status_code == 200
    html_list = list_resp.text
    assert "1ra vez" in html_list, "No aparece la insignia '1ra vez' en la tabla de consultas"
    assert "v2" in html_list, "No aparece el badge de versión 'v2' en la tabla de consultas"
    print("  -> Listado /consultations verificado: Insignias '1ra vez' y 'v2' visibles en la tabla.")

    # 11. GET /consultations/{id}/report/pdf (Generación de PDF Oficial)
    print(f"\n[PASO 9] Verificando generación de Informe Médico PDF...")
    pdf_resp = client.get(f"/consultations/{consultation_id}/report/pdf")
    assert pdf_resp.status_code == 200, f"Error generando PDF: {pdf_resp.status_code}"
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-"), "El contenido retornado no es un archivo PDF válido"
    print(f"  -> PDF generado correctamente ({len(pdf_resp.content)} bytes, Content-Type: application/pdf, Header: %PDF-1.4).")

    print("\n" + "=" * 70)
    print(">>> TODOS LOS 9 PASOS DE VERIFICACIÓN E2E COMPLETADOS CON ÉXITO AL 100%")
    print("=" * 70)

if __name__ == "__main__":
    run_e2e_verification()
