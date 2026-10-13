import sys
from pathlib import Path

desktop_dir = Path("sscp-desktop").resolve()
sys.path.insert(0, str(desktop_dir))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal, Base, engine
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.payment import Payment
from app.models.relay_message import RelayMessage

print("=" * 70)
print("INICIANDO PRUEBAS DEL BUZÓN RELAY LOCAL-FIRST (FASE 1 & FASE 2)")
print("=" * 70)

# 1. Asegurar tabla relay_messages
Base.metadata.create_all(bind=engine)
print("1. Tabla relay_messages creada/verificada en SQLite.")

client = TestClient(app)
clinic_id = "dr_carlos_heredia"

# 2. Status inicial del buzón
res_status = client.get(f"/api/relay/{clinic_id}/status")
assert res_status.status_code == 200
print(f"2. Estado del Buzón Relay: status={res_status.status_code}, data={res_status.json()}")

# 3. Simular que la tablet de la secretaria a las 7:00 AM deposita un lote en el buzón
push_payload = {
    "device_id": "tablet_secretaria_01",
    "message_type": "delta",
    "data": {
        "patients": [
            {
                "client_uuid": "pat-rel-001",
                "first_name": "Ana Sofia",
                "last_name": "Rosario",
                "document_id": "402-1928374-5",
                "phone": "8095551234",
                "insurance_name": "SeNaSa (Régimen Contributivo)"
            }
        ],
        "appointments": [
            {
                "patient_client_uuid": "pat-rel-001",
                "date": "2026-10-11",
                "start_time": "07:30",
                "reason": "Consulta Prenatal",
                "status": "En Espera",
                "price": 1500.0,
                "queue_number": 1
            }
        ],
        "payments": [
            {
                "patient_id": None, # Se asociará tras crear paciente
                "amount": 1500.0,
                "service_name": "Consulta Prenatal",
                "receipt_number": "REC-RELAY-001",
                "status": "paid"
            }
        ]
    }
}

res_push = client.post(f"/api/relay/{clinic_id}/push", json=push_payload)
assert res_push.status_code == 200
push_data = res_push.json()
assert push_data["success"] == True
msg_id = push_data["message_id"]
print(f"3. Lote depositado por la Tablet en el Buzón Relay con éxito (Message ID: {msg_id}).")

# 4. Pull desde el buzón (simulando que otra tablet o PC lee los cambios)
res_pull = client.get(f"/api/relay/{clinic_id}/pull?device_id=otra_estacion")
assert res_pull.status_code == 200
pull_data = res_pull.json()
assert pull_data["deltas_count"] >= 1
print(f"4. Recuperación de deltas del buzón OK: {pull_data['deltas_count']} mensaje(s) encontrados.")

# 5. Sincronización local en la PC del Doctor (PC se enciende y descarga del buzón)
res_sync = client.post(f"/api/relay/{clinic_id}/sync-local")
assert res_sync.status_code == 200
sync_data = res_sync.json()
assert sync_data["success"] == True
print(f"5. Sincronización local ejecutada en la PC del Doctor: {sync_data}")

# 6. Verificar que Ana Sofia Rosario existe en la base SQLite del doctor con su cita y pago
db = SessionLocal()
p_check = db.query(Patient).filter(Patient.document_id == "402-1928374-5").first()
assert p_check is not None, "El paciente no se encontró en la base local tras la reconciliación"
appt_check = db.query(Appointment).filter(Appointment.patient_id == p_check.id).first()
assert appt_check is not None, "La cita no se encontró en la base local"
assert appt_check.reason == "Consulta Prenatal"
assert appt_check.status == "En Espera"
print(f"6. Verificación en SQLite local: Paciente #{p_check.id} '{p_check.first_name} {p_check.last_name}', Cita '{appt_check.reason}' ({appt_check.status}) guardados correctamente.")

# 7. Probar generación de Código QR de enlace
res_qr = client.get("/api/relay/qr-link")
assert res_qr.status_code == 200
assert res_qr.headers["content-type"] == "image/png"
assert len(res_qr.content) > 500
print(f"7. Código QR dinámico generado con éxito ({len(res_qr.content)} bytes, image/png).")

# Limpiar datos de prueba
db.query(Appointment).filter(Appointment.patient_id == p_check.id).delete()
db.delete(p_check)
db.query(RelayMessage).filter(RelayMessage.id == msg_id).delete()
db.commit()
db.close()

print("\n" + "=" * 70)
print(">>> TODAS LAS PRUEBAS DEL BUZÓN RELAY LOCAL-FIRST PASARON AL 100%")
print("=" * 70)
