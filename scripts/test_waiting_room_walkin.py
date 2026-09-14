import sys
from pathlib import Path
from datetime import date, datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.consultation import Consultation

def test_waiting_room_and_walkin_workflow():
    print("==================================================================")
    print("TEST: SALA DE ESPERA, LLEGADA SIN CITA PREVIA Y ATENCIÓN INMEDIATA")
    print("==================================================================")

    client = TestClient(app)
    db = SessionLocal()

    # 1. Obtener usuarios de prueba
    sec_user = db.query(User).filter(User.role == "secretaria").first()
    doc_user = db.query(User).filter(User.role.in_(["doctor", "admin"])).first()
    patient = db.query(Patient).first()

    assert sec_user is not None, "Debe existir un usuario secretaria"
    assert doc_user is not None, "Debe existir un usuario doctor/admin"
    assert patient is not None, "Debe existir al menos un paciente"

    # Login de secretaria
    print(f"\n[1/7] Iniciando sesión como secretaria ({sec_user.email})...")
    res_sec_login = client.post("/login", data={"username": sec_user.email, "password": "password123"}, follow_redirects=False)
    assert res_sec_login.status_code in [200, 302, 303]
    sec_cookies = res_sec_login.cookies
    print("  [OK] Sesión de secretaria activa.")

    # Login de doctor
    print(f"\n[2/7] Iniciando sesión como doctor ({doc_user.email})...")
    res_doc_login = client.post("/login", data={"username": doc_user.email, "password": "password123"}, follow_redirects=False)
    assert res_doc_login.status_code in [200, 302, 303]
    doc_cookies = res_doc_login.cookies
    print("  [OK] Sesión de doctor activa.")

    # 2. Secretaria registra llegada de paciente sin cita previa (Poner en Espera)
    print(f"\n[3/7] Secretaria indica que {patient.first_name} {patient.last_name} llegó sin cita y está esperando...")
    res_walkin = client.post("/appointments/check-in-walkin", data={
        "patient_id": patient.id,
        "notes": "Llegó a recepción con malestar general, sin cita agendada",
        "redirect_to": "appointments"
    }, cookies=sec_cookies, follow_redirects=False)
    assert res_walkin.status_code == 303, f"Esperado 303, obtenido {res_walkin.status_code}"
    assert "status=En+Espera" in res_walkin.headers.get("location", "")
    print("  [OK] Solicitud procesada y redirigida a listado de En Espera.")

    # Verificar registro en base de datos
    today = date.today()
    waiting_appt = db.query(Appointment).filter(
        Appointment.patient_id == patient.id,
        Appointment.date == today,
        Appointment.status == "En Espera"
    ).first()
    assert waiting_appt is not None, "La cita en estado 'En Espera' debe haberse guardado en la BD."
    assert "Sin cita" in waiting_appt.reason or "espontánea" in waiting_appt.reason
    print(f"  [OK] Cita en espera verificada en BD (ID: {waiting_appt.id}, Estado: {waiting_appt.status}).")

    # 3. Doctor ve la notificación en su Dashboard y Agenda
    print("\n[4/7] Verificando que el Doctor ve la Sala de Espera Activa en su Dashboard...")
    res_dashboard = client.get("/dashboard", cookies=doc_cookies)
    assert res_dashboard.status_code == 200
    assert "Sala de Espera Activa" in res_dashboard.text
    assert patient.last_name in res_dashboard.text
    assert "Atender Ahora" in res_dashboard.text
    print("  [OK] Dashboard del doctor muestra la alerta con botón 'Atender Ahora'.")

    # Verificar ficha del paciente
    res_pat_view = client.get(f"/patients/{patient.id}", cookies=doc_cookies)
    assert res_pat_view.status_code == 200
    assert "Paciente en Sala de Espera" in res_pat_view.text
    assert "Atender Ahora" in res_pat_view.text
    print("  [OK] Ficha del paciente muestra banner de sala de espera y 'Atender Ahora'.")

    # 4. Doctor atiende al paciente y completa la consulta
    print("\n[5/7] Doctor atiende al paciente en espera y registra la consulta médica...")
    res_doc_consult_get = client.get(
        f"/consultations/create?patient_id={patient.id}&appointment_id={waiting_appt.id}&walk_in=1",
        cookies=doc_cookies
    )
    assert res_doc_consult_get.status_code == 200
    assert "Atención Inmediata" in res_doc_consult_get.text

    # Guardar consulta médica
    res_create_consult = client.post("/consultations/create", data={
        "patient_id": patient.id,
        "appointment_id": waiting_appt.id,
        "reason": "Evaluación médica inmediata por llegada espontánea",
        "diagnosis": "Cefalea tensional",
        "treatment": "Paracetamol 500mg c/8h",
        "prescription": "Paracetamol 500mg tabletas"
    }, cookies=doc_cookies, follow_redirects=False)
    assert res_create_consult.status_code == 303
    print("  [OK] Consulta creada exitosamente.")

    # Verificar que la cita pasó automáticamente a 'Completada'
    db.refresh(waiting_appt)
    assert waiting_appt.status == "Completada", f"La cita debía pasar a 'Completada', pero está en '{waiting_appt.status}'"
    print("  [OK] La cita en sala de espera pasó automáticamente a estado 'Completada'.")

    # 5. Doctor atiende a un paciente que entra directo ('Atender Ahora')
    print("\n[6/7] Probando entrada directa de paciente ('Atender Ahora' sin espera previa)...")
    res_attend_now = client.post("/appointments/attend-now", data={
        "patient_id": patient.id,
        "notes": "Entrada directa al consultorio"
    }, cookies=doc_cookies, follow_redirects=False)
    assert res_attend_now.status_code == 303
    location = res_attend_now.headers.get("location", "")
    assert "/consultations/create" in location
    assert f"patient_id={patient.id}" in location
    assert "walk_in=1" in location
    print("  [OK] 'Atender Ahora' creó la atención inmediata y redirigió a la consulta médica.")

    # 6. Seguridad de roles: Secretaria no puede usar /appointments/attend-now (requiere 'consultations')
    print("\n[7/7] Verificando que la Secretaria NO puede ejecutar 'attend-now' directo a consulta...")
    res_sec_attend = client.post("/appointments/attend-now", data={
        "patient_id": patient.id
    }, cookies=sec_cookies, follow_redirects=False)
    assert res_sec_attend.status_code == 403, f"Esperado 403, obtenido {res_sec_attend.status_code}"
    print("  [OK] Secretaria bloqueada con HTTP 403 FORBIDDEN en /appointments/attend-now.")

    print("\n==================================================================")
    print("¡TODAS LAS PRUEBAS DE SALA DE ESPERA Y ATENCIÓN INMEDIATA PASARON!")
    print("==================================================================")

if __name__ == "__main__":
    test_waiting_room_and_walkin_workflow()
