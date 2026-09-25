import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Agregar directorio raiz de sscp-desktop al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from main import app
from app.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash
from app.core.initial_data import seed_initial_data_if_empty

def run_mobile_api_tests():
    print("=== [TEST] INICIANDO PRUEBAS DE LA API MÓVIL (DOCTOR Y SECRETARIA) ===")

    # 1. Asegurar usuarios y datos iniciales en SQLite
    with SessionLocal() as db:
        seed_initial_data_if_empty(db)

    client = TestClient(app)

    # 2. Prueba de Ping Público
    print("\n[1/6] Probando GET /api/mobile/ping...")
    res_ping = client.get("/api/mobile/ping")
    assert res_ping.status_code == 200, f"Error en ping: {res_ping.text}"
    ping_data = res_ping.json()
    assert ping_data.get("status") == "online"
    print(f"  -> Conectividad OK. Clínica: '{ping_data.get('clinic_name')}'")

    # 3. Prueba de Login Doctor
    print("\n[2/6] Probando POST /api/mobile/login (Doctor)...")
    res_doc = client.post("/api/mobile/login", json={
        "email": "doctor@sscp.com",
        "password": "password123"
    })
    assert res_doc.status_code == 200, f"Error login doctor: {res_doc.text}"
    doc_data = res_doc.json()
    doc_token = doc_data["access_token"]
    assert doc_data["user"]["role"] == "doctor"
    print(f"  -> Login Doctor OK. Token obtenido. Rol: {doc_data['user']['role']}")

    # 4. Prueba de Login Secretaria
    print("\n[3/6] Probando POST /api/mobile/login (Secretaria)...")
    res_sec = client.post("/api/mobile/login", json={
        "email": "secretaria@sscp.com",
        "password": "password123"
    })
    assert res_sec.status_code == 200, f"Error login secretaria: {res_sec.text}"
    sec_data = res_sec.json()
    sec_token = sec_data["access_token"]
    assert sec_data["user"]["role"] == "secretaria"
    print(f"  -> Login Secretaria OK. Rol: {sec_data['user']['role']}")

    # 5. Dashboard Móvil
    print("\n[4/6] Probando GET /api/mobile/dashboard...")
    res_dash = client.get("/api/mobile/dashboard", headers={"Authorization": f"Bearer {doc_token}"})
    assert res_dash.status_code == 200, f"Error dashboard: {res_dash.text}"
    dash_data = res_dash.json()
    assert "stats" in dash_data
    assert "appointments" in dash_data
    print(f"  -> Dashboard OK. Citas hoy: {dash_data['stats']['total']}, En espera: {dash_data['stats']['waiting']}")

    # 6. Agendamiento Express y Cambio de Estado a 'En Espera'
    print("\n[5/6] Probando creación express y recepción 1-tap...")
    res_create = client.post("/api/mobile/appointments/quick-create", 
        json={
            "patient_name": "Paciente Móvil Test",
            "patient_phone": "8095559999",
            "date": dash_data["date"],
            "start_time": "11:30",
            "reason": "Control de Presión Arterial"
        },
        headers={"Authorization": f"Bearer {sec_token}"}
    )
    assert res_create.status_code == 200, f"Error creación cita: {res_create.text}"
    new_appt = res_create.json()
    appt_id = new_appt["appointment_id"]
    patient_id = new_appt["patient_id"]
    print(f"  -> Cita creada ID {appt_id} para Paciente ID {patient_id}")

    # Recepción: Secretaria marca 'En Espera'
    res_wait = client.post(f"/api/mobile/appointments/{appt_id}/status",
        json={"status": "En Espera"},
        headers={"Authorization": f"Bearer {sec_token}"}
    )
    assert res_wait.status_code == 200
    assert res_wait.json()["new_status"] == "En Espera"
    print(f"  -> Cita ID {appt_id} marcada como 'En Espera' correctamente.")

    # 7. Doctor atiende y guarda evolución
    print("\n[6/6] Probando guardado de evolución clínica y cobro rápido...")
    res_cons = client.post("/api/mobile/consultations/quick",
        json={
            "patient_id": patient_id,
            "appointment_id": appt_id,
            "diagnosis": "Hipertensión controlada",
            "treatment": "Enalapril 10mg diario",
            "notes": "Paciente evoluciona favorablemente"
        },
        headers={"Authorization": f"Bearer {doc_token}"}
    )
    assert res_cons.status_code == 200, f"Error consulta: {res_cons.text}"
    print(f"  -> Consulta guardada con éxito (ID {res_cons.json()['consultation_id']}). Cita finalizada.")

    # Cobro rápido por parte de secretaria
    res_pay = client.post("/api/mobile/payments/quick",
        json={
            "patient_id": patient_id,
            "amount": 1500.0,
            "payment_method": "Efectivo",
            "notes": "Cobro de consulta rápida"
        },
        headers={"Authorization": f"Bearer {sec_token}"}
    )
    assert res_pay.status_code == 200, f"Error cobro: {res_pay.text}"
    print(f"  -> Cobro de {res_pay.json()['amount']} registrado con éxito.")

    # 8. Reportes Móviles Consolidados (Pagos, Vistos, Citas Previas)
    print("\n[7/8] Probando GET /api/mobile/reports/summary (Doctor y Secretaria)...")
    res_rep = client.get("/api/mobile/reports/summary", headers={"Authorization": f"Bearer {doc_token}"})
    assert res_rep.status_code == 200, f"Error reportes: {res_rep.text}"
    rep_data = res_rep.json()
    assert "payments" in rep_data
    assert "attended" in rep_data
    assert "appointments" in rep_data
    assert rep_data["payments"]["total_collected"] >= 1500.0
    assert rep_data["attended"]["count"] >= 1
    assert "pdf_export_url" in rep_data
    print(f"  -> Reportes OK: Total Pagos={rep_data['payments']['total_collected']}, Atendidos={rep_data['attended']['count']}, Citas={rep_data['appointments']['stats']['total']}")

    # 9. Descarga de PDF con Token en Query Param
    print("\n[8/8] Probando GET /reports/export/secretary-daily-pdf con token en query param...")
    res_pdf = client.get(f"/reports/export/secretary-daily-pdf?token={doc_token}")
    assert res_pdf.status_code == 200, f"Error descarga PDF: {res_pdf.text}"
    assert res_pdf.headers.get("content-type") == "application/pdf"
    assert len(res_pdf.content) > 1000
    print(f"  -> Exportación PDF con token en URL OK. Tamaño: {len(res_pdf.content)} bytes.")

    print("\n=======================================================")
    print("[SUCCESS] TODAS LAS PRUEBAS DE LA API MOVIL PASARON EXITOSAMENTE")
    print("=======================================================")

if __name__ == "__main__":
    run_mobile_api_tests()
