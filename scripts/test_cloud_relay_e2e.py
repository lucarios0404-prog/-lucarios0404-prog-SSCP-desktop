import sys
import os
import json
import urllib.request
from datetime import datetime, date

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


# Asegurar path de sscp-desktop
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal, engine, Base
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.relay_message import RelayMessage
from app.services.relay_service import RelayService

print("=" * 70)
print("PRUEBA E2E: PUENTE CLOUD RELAY (TABLET <-> PC EN REDES SEPARADAS)")
print("=" * 70)

# Asegurar tablas locales
Base.metadata.create_all(bind=engine)
client = TestClient(app)
CLINIC_ID = "dr_carlos_heredia"
TIMESTAMP_TAG = int(datetime.utcnow().timestamp())
TEST_DOC = f"TEST-RELAY-{TIMESTAMP_TAG}"
TEST_FN = f"PacienteRelay{TIMESTAMP_TAG}"
TEST_LN = "CloudTest"

print(f"\n1. Tablet (Secretaría) en red móvil/Wi-Fi separada...")
print(f"   -> Depositando paciente '{TEST_FN}' en buzón de la nube: https://sscp.laxarusdevs.com/api/relay/{CLINIC_ID}/push")

cloud_push_payload = {
    "device_id": "tablet_secretaria_e2e",
    "message_type": "delta",
    "data": {
        "patients": [
            {
                "client_uuid": f"uuid-p-{TIMESTAMP_TAG}",
                "first_name": TEST_FN,
                "last_name": TEST_LN,
                "document_id": TEST_DOC,
                "phone": f"809-555-{TIMESTAMP_TAG % 10000:04d}",
                "insurance_name": "Senasa Contributivo"
            }
        ],
        "appointments": [
            {
                "client_uuid": f"uuid-apt-{TIMESTAMP_TAG}",
                "patient_client_uuid": f"uuid-p-{TIMESTAMP_TAG}",
                "date": date.today().isoformat(),
                "start_time": "09:15",
                "reason": "Evaluación Ginecológica por Cloud Relay",
                "price": 2500.0
            }
        ]
    }
}

req_data = json.dumps(cloud_push_payload).encode('utf-8')
req = urllib.request.Request(
    f"https://sscp.laxarusdevs.com/api/relay/{CLINIC_ID}/push",
    data=req_data,
    headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14; Tablet) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SSCP-Tablet/1.5.0", "Content-Type": "application/json"}
)

res = urllib.request.urlopen(req, timeout=10)
push_response = json.loads(res.read().decode('utf-8'))
print(f"   -> Respuesta del Buzón Nube: {push_response}")
assert push_response.get("success") is True, "Fallo al depositar en la nube"
msg_id = push_response.get("message_id")
print(f"   ✓ Mensaje depositado exitosamente en la nube. Message ID: {msg_id}")

print(f"\n2. Doctor enciende su PC (cable red 'net', sin Wi-Fi, sin Tailscale)...")
print(f"   -> Ejecutando auto-sincronización /api/relay/{CLINIC_ID}/sync-local...")

sync_res = client.post(f"/api/relay/{CLINIC_ID}/sync-local")
print(f"   -> Status Code: {sync_res.status_code}")
sync_data = sync_res.json()
print(f"   -> Datos de sincronización: {sync_data}")
assert sync_res.status_code == 200, f"Error en sync-local: {sync_res.text}"
assert sync_data.get("success") is True, "Sync success debe ser True"

print(f"\n3. Verificando que SQLite local absorbió los datos...")
with SessionLocal() as db:
    patient = db.query(Patient).filter(Patient.document_id == TEST_DOC).first()
    assert patient is not None, f"El paciente con documento {TEST_DOC} no fue encontrado en SQLite local"
    print(f"   ✓ Paciente verificado en SQLite: ID={patient.id}, Nombre={patient.first_name} {patient.last_name}")

    appt = db.query(Appointment).filter(Appointment.patient_id == patient.id).first()
    assert appt is not None, f"La cita para el paciente {patient.id} no fue encontrada en SQLite local"
    print(f"   ✓ Cita médica verificada en SQLite: ID={appt.id}, Fecha={appt.date}, Motivo={appt.reason}")

print(f"\n4. Prueba de Idempotencia (segundo pull no debe duplicar)...")
sync_res_2 = client.post(f"/api/relay/{CLINIC_ID}/sync-local")
sync_data_2 = sync_res_2.json()
print(f"   -> Datos del 2do sync: {sync_data_2}")

with SessionLocal() as db:
    count_p = db.query(Patient).filter(Patient.document_id == TEST_DOC).count()
    assert count_p == 1, f"Se duplicó el paciente! Conteo: {count_p}"
    print(f"   ✓ Idempotencia confirmada: El paciente existe exactamente 1 vez (sin duplicados).")

    # Limpieza del registro de prueba
    db.query(Appointment).filter(Appointment.patient_id == patient.id).delete()
    db.query(Patient).filter(Patient.document_id == TEST_DOC).delete()
    db.query(RelayMessage).filter(RelayMessage.device_id == f"cloud_{msg_id}").delete()
    db.commit()
    print("   ✓ Registros de prueba limpiados correctamente.")

print("\n" + "=" * 70)
print("¡TODAS LAS PRUEBAS E2E DEL PUENTE CLOUD RELAY PASARON CON 100% DE ÉXITO!")
print("=" * 70)
