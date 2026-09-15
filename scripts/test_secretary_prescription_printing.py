import sys
import os
import json
from datetime import date, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.appointment import Appointment
from app.core.security import get_password_hash, create_access_token
from app.core.permissions import AVAILABLE_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS

def run_tests():
    db = SessionLocal()
    client = TestClient(app)

    print("=== TEST 1: Verificar definición de permisos en app/core/permissions.py ===")
    perm_keys = [p["key"] for p in AVAILABLE_PERMISSIONS]
    assert "print_prescriptions" in perm_keys, "print_prescriptions debe estar en AVAILABLE_PERMISSIONS"
    assert "print_prescriptions" in DEFAULT_ROLE_PERMISSIONS["doctor"], "print_prescriptions debe estar en doctor"
    assert "print_prescriptions" in DEFAULT_ROLE_PERMISSIONS["secretaria"], "print_prescriptions debe estar en secretaria"
    assert "prescriptions" not in DEFAULT_ROLE_PERMISSIONS["secretaria"], "prescriptions NO debe estar en secretaria"
    assert "consultations" not in DEFAULT_ROLE_PERMISSIONS["secretaria"], "consultations NO debe estar en secretaria"
    print("[OK] Permisos definidos correctamente en AVAILABLE_PERMISSIONS y DEFAULT_ROLE_PERMISSIONS.")

    print("\n=== TEST 2: Verificar lógica de has_permission en User ===")
    sec_user = db.query(User).filter(User.role == "secretaria", User.email == "secretaria@sscp.com").first()
    assert sec_user is not None, "Usuario secretaria@sscp.com debe existir"
    assert sec_user.has_permission("print_prescriptions") is True, "Secretaria DEBE tener permiso print_prescriptions"
    assert sec_user.has_permission("prescriptions") is False, "Secretaria NO DEBE tener permiso prescriptions (emitir)"
    assert sec_user.has_permission("consultations") is False, "Secretaria NO DEBE tener permiso consultations (atender)"
    assert sec_user.has_permission("licenses") is False, "Secretaria NO DEBE tener permiso licenses"
    assert sec_user.has_permission("references") is False, "Secretaria NO DEBE tener permiso references"
    print("[OK] Modelo User evalúa has_permission con la delimitación médica correcta.")

    # Crear paciente y consulta de prueba con receta
    patient = db.query(Patient).filter(Patient.document_id == "TEST-SEC-RX").first()
    if not patient:
        patient = Patient(
            first_name="PacientePrueba",
            last_name="RecetaSecretaria",
            document_id="TEST-SEC-RX",
            date_of_birth=date(1990, 5, 20),
            phone="809-555-9988"
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)

    doctor = db.query(User).filter(User.role == "doctor").first()
    consultation = db.query(Consultation).filter(Consultation.patient_id == patient.id).first()
    if not consultation:
        consultation = Consultation(
            patient_id=patient.id,
            doctor_id=doctor.id if doctor else 1,
            reason="Dolor de garganta e inflamación",
            diagnosis="Faringitis aguda (J02.9)",
            treatment="Hidratación abundante y reposo",
            prescription="Amoxicilina 500mg VO c/8h por 7 días\nIbuprofeno 400mg VO c/8h por 3 días",
            notes="Control en 5 días si persiste fiebre"
        )
        db.add(consultation)
        db.commit()
        db.refresh(consultation)

    # Login de secretaria
    res_sec_login = client.post("/login", data={"username": sec_user.email, "password": "password123"}, follow_redirects=False)
    sec_cookies = res_sec_login.cookies

    print("\n=== TEST 3: Secretaria descarga PDF de Receta Médica ===")
    res = client.get(f"/consultations/{consultation.id}/prescription/pdf", cookies=sec_cookies)
    assert res.status_code == 200, f"Error al obtener PDF: {res.status_code}"
    assert res.headers["content-type"] == "application/pdf", "El tipo de medio debe ser application/pdf"
    assert len(res.content) > 500, "El PDF generado no debe estar vacío"
    print(f"[OK] Secretaria descargó el PDF de receta correctamente ({len(res.content)} bytes, application/pdf).")

    print("\n=== TEST 4: Secretaria ve la consulta médica en modo lectura con botón de imprimir receta ===")
    res = client.get(f"/consultations/{consultation.id}", cookies=sec_cookies)
    assert res.status_code == 200, f"Error al ver consulta: {res.status_code}"
    assert "Imprimir Receta (PDF)" in res.text, "Debe mostrar botón Imprimir Receta (PDF)"
    assert f"/consultations/{consultation.id}/prescription/pdf" in res.text, "Enlace a PDF de receta debe estar presente"
    # Verificar que NO se muestre el botón de edición para la secretaria
    assert f"/consultations/{consultation.id}/edit" not in res.text, "NO debe mostrar enlace de edición para secretaria"
    print("[OK] Secretaria puede acceder a la nota de consulta en solo-lectura con botón de imprimir receta.")

    print("\n=== TEST 5: Seguridad - Secretaria NO puede acceder a acciones médicas prohibidas ===")
    # 5.1 No puede emitir consulta
    res = client.post("/consultations/create", data={"patient_id": patient.id, "reason": "Hack"}, cookies=sec_cookies)
    assert res.status_code == 403, f"Secretaria no debe poder crear consulta (esperado 403, obtenido {res.status_code})"
    
    # 5.2 No puede editar consulta
    res = client.post(f"/consultations/{consultation.id}/edit", data={"reason": "Hack"}, cookies=sec_cookies)
    assert res.status_code == 403, f"Secretaria no debe poder editar consulta (esperado 403, obtenido {res.status_code})"

    # 5.3 No puede emitir receta rápida
    res = client.post("/prescriptions/quick", data={"patient_id": patient.id, "prescription": "Medicamento"}, cookies=sec_cookies)
    assert res.status_code == 403, f"Secretaria no debe poder emitir receta rápida (esperado 403, obtenido {res.status_code})"

    # 5.4 No puede descargar informe clínico confidencial
    res = client.get(f"/consultations/{consultation.id}/report/pdf", cookies=sec_cookies)
    assert res.status_code == 403, f"Secretaria no debe poder descargar informe clínico (esperado 403, obtenido {res.status_code})"
    print("[OK] Seguridad validada: Secretaria bloqueada con HTTP 403 en creación/edición de consultas, recetas rápidas e informes confidenciales.")

    print("\n=== TEST 6: Botón de Imprimir Receta visible en Expediente del Paciente ===")
    res = client.get(f"/patients/{patient.id}", cookies=sec_cookies)
    assert res.status_code == 200, f"Error al abrir expediente: {res.status_code}"
    assert "Imprimir Receta" in res.text, "Debe mostrar 'Imprimir Receta' en el expediente del paciente"
    assert f"/consultations/{consultation.id}/prescription/pdf" in res.text, "Enlace directo al PDF debe estar en el expediente"
    print("[OK] Botón 'Imprimir Receta' visible y funcional en /patients/{id} para la secretaria.")

    print("\n=== TEST 7: Formulario de Usuarios en Administración muestra el nuevo permiso ===")
    admin_user = db.query(User).filter(User.role == "admin").first()
    res_admin_login = client.post("/login", data={"username": admin_user.email, "password": "password123"}, follow_redirects=False)
    admin_cookies = res_admin_login.cookies
    
    res = client.get(f"/users/{sec_user.id}/edit", cookies=admin_cookies)
    assert res.status_code == 200
    assert "perm_print_prescriptions" in res.text, "El checkbox perm_print_prescriptions debe estar presente en edición de usuario"
    assert "Imprimir Recetas Médicas" in res.text, "La etiqueta 'Imprimir Recetas Médicas' debe estar presente"
    print("[OK] El permiso 'print_prescriptions' aparece en la gestión de usuarios del administrador.")

    db.close()
    print("==============================================")
    print("SUCCESS: TODOS LOS TESTS DE PERMISOS DE RECETAS PASARON CON EXITO (7/7)")
    print("==============================================")

if __name__ == "__main__":
    run_tests()
