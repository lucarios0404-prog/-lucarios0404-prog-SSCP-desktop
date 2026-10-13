import sys
import os
import json
import urllib.request
from datetime import datetime, date

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Path a sscp-desktop
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal, engine, Base
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.setting import Setting
from app.models.relay_message import RelayMessage
from app.services.relay_service import RelayService

print("=" * 75)
print("TEST SUITE: SOPORTE MULTI-DOCTOR & AISLAMIENTO EN CLOUD RELAY")
print("=" * 75)

Base.metadata.create_all(bind=engine)
with engine.connect() as conn:
    res_s = conn.execute(text("PRAGMA table_info(settings)")).fetchall()
    s_cols = [r[1] for r in res_s]
    if "relay_channel_id" not in s_cols:
        conn.execute(text("ALTER TABLE settings ADD COLUMN relay_channel_id TEXT DEFAULT 'dr_carlos_heredia'"))
        conn.commit()

client = TestClient(app)

# ----------------------------------------------------------------------
# PRUEBA 1: Detección Dinámica de Canal por Doctor en Base de Datos Local
# ----------------------------------------------------------------------
print("\n[TEST 1] Verificando detección de canal según configuración del médico...")
with SessionLocal() as db:
    setting = db.query(Setting).first()
    if not setting:
        setting = Setting(doctor_name="Dr. Carlos Heredia", relay_channel_id="dr_carlos_heredia")
        db.add(setting)
        db.commit()
        db.refresh(setting)

    orig_channel = setting.relay_channel_id
    orig_name = setting.doctor_name

    try:
        # Caso 1.1: Canal explícito configurado
        setting.relay_channel_id = "dr_manuel_ramirez"
        db.commit()
        detected_id = RelayService.get_clinic_id(db)
        assert detected_id == "dr_manuel_ramirez", f"Fallo: esperado 'dr_manuel_ramirez', obtenido '{detected_id}'"
        print(f"  ✓ Caso 1.1: Canal explícito detectado correctamente -> '{detected_id}'")

        # Caso 1.2: Generación automática de slug por nombre del médico
        setting.relay_channel_id = ""
        setting.doctor_name = "Dra. Laura Gómez Peña"
        db.commit()
        auto_slug = RelayService.get_clinic_id(db)
        assert "laura_gomez" in auto_slug, f"Fallo al generar slug: '{auto_slug}'"
        print(f"  ✓ Caso 1.2: Slug automático por nombre del médico generado -> '{auto_slug}'")

    finally:
        # Restaurar configuración original
        setting.relay_channel_id = orig_channel
        setting.doctor_name = orig_name
        db.commit()
        print("  ✓ Configuración original del doctor restaurada.")

# ----------------------------------------------------------------------
# PRUEBA 2: Aislamiento estricto de buzones en la Nube (sscp.laxarusdevs.com)
# ----------------------------------------------------------------------
print("\n[TEST 2] Verificando aislamiento multi-doctor en la Nube (Buzón A vs Buzón B)...")
DOC_A = "dr_carlos_heredia"
DOC_B = "dr_manuel_ramirez"
TS = int(datetime.utcnow().timestamp())

pat_a_doc = f"DOCA-{TS}"
pat_b_doc = f"DOCB-{TS}"

# Enviar paciente al Doctor A
payload_a = {
    "device_id": "tablet_secretaria_doc_a",
    "message_type": "delta",
    "data": {
        "patients": [{"client_uuid": f"uuid-a-{TS}", "first_name": "PacienteA", "last_name": "DeHeredia", "document_id": pat_a_doc}],
        "appointments": [{"client_uuid": f"uuid-apt-a-{TS}", "patient_client_uuid": f"uuid-a-{TS}", "date": date.today().isoformat(), "start_time": "08:00", "reason": "Consulta Doctor A"}]
    }
}
req_a = urllib.request.Request(
    f"https://sscp.laxarusdevs.com/api/relay/{DOC_A}/push",
    data=json.dumps(payload_a).encode('utf-8'),
    headers={"User-Agent": "SSCP-Test-A", "Content-Type": "application/json"}
)
res_a = json.loads(urllib.request.urlopen(req_a, timeout=10).read().decode('utf-8'))
assert res_a.get("success") is True, "Error en push a Doctor A"
msg_id_a = res_a.get("message_id")
print(f"  ✓ Mensaje depositado en Buzón A ({DOC_A}) -> ID: {msg_id_a}")

# Enviar paciente al Doctor B
payload_b = {
    "device_id": "tablet_secretaria_doc_b",
    "message_type": "delta",
    "data": {
        "patients": [{"client_uuid": f"uuid-b-{TS}", "first_name": "PacienteB", "last_name": "DeRamirez", "document_id": pat_b_doc}],
        "appointments": [{"client_uuid": f"uuid-apt-b-{TS}", "patient_client_uuid": f"uuid-b-{TS}", "date": date.today().isoformat(), "start_time": "09:00", "reason": "Consulta Doctor B"}]
    }
}
req_b = urllib.request.Request(
    f"https://sscp.laxarusdevs.com/api/relay/{DOC_B}/push",
    data=json.dumps(payload_b).encode('utf-8'),
    headers={"User-Agent": "SSCP-Test-B", "Content-Type": "application/json"}
)
res_b = json.loads(urllib.request.urlopen(req_b, timeout=10).read().decode('utf-8'))
assert res_b.get("success") is True, "Error en push a Doctor B"
msg_id_b = res_b.get("message_id")
print(f"  ✓ Mensaje depositado en Buzón B ({DOC_B}) -> ID: {msg_id_b}")

# Descargar desde Buzón A: NO debe contener datos del Doctor B
pull_req_a = urllib.request.Request(f"https://sscp.laxarusdevs.com/api/relay/{DOC_A}/pull?device_id=test_verifier", headers={"User-Agent": "SSCP-Test-A"})
pull_res_a = json.loads(urllib.request.urlopen(pull_req_a, timeout=10).read().decode('utf-8'))
deltas_a = pull_res_a.get("deltas", [])
doc_b_leak = any(pat_b_doc in json.dumps(d) for d in deltas_a)
assert not doc_b_leak, "¡CRITICAL ERROR! Fuga de datos: Doctor A recibió datos del Doctor B."
print(f"  ✓ Aislamiento verificado en Buzón A: {len(deltas_a)} deltas recibidos, CERO contaminación del Doctor B.")

# Descargar desde Buzón B: NO debe contener datos del Doctor A
pull_req_b = urllib.request.Request(f"https://sscp.laxarusdevs.com/api/relay/{DOC_B}/pull?device_id=test_verifier", headers={"User-Agent": "SSCP-Test-B"})
pull_res_b = json.loads(urllib.request.urlopen(pull_req_b, timeout=10).read().decode('utf-8'))
deltas_b = pull_res_b.get("deltas", [])
doc_a_leak = any(pat_a_doc in json.dumps(d) for d in deltas_b)
assert not doc_a_leak, "¡CRITICAL ERROR! Fuga de datos: Doctor B recibió datos del Doctor A."
print(f"  ✓ Aislamiento verificado en Buzón B: {len(deltas_b)} deltas recibidos, CERO contaminación del Doctor A.")

# ----------------------------------------------------------------------
# PRUEBA 3: Endpoint de Estado y Código QR Dinámico en Desktop
# ----------------------------------------------------------------------
print("\n[TEST 3] Verificando endpoints locales de Relay y QR dinámico...")
res_status = client.get("/api/relay/status")
assert res_status.status_code == 200, f"Error en /api/relay/status: {res_status.text}"
status_data = res_status.json()
print(f"  ✓ /api/relay/status -> Canal activo: '{status_data.get('clinic_id')}', Online: {status_data.get('status')}")

res_qr = client.get("/api/relay/qr-link")
assert res_qr.status_code == 200, f"Error en /api/relay/qr-link: {res_qr.status_code}"
assert res_qr.headers["content-type"] == "image/png", "QR debe ser image/png"
assert len(res_qr.content) > 100, "Imagen QR vacía"
print(f"  ✓ /api/relay/qr-link -> PNG generado exitosamente ({len(res_qr.content)} bytes)")

# Limpieza local de registros de prueba si llegaron a sincronizarse
with SessionLocal() as db:
    p_a = db.query(Patient).filter(Patient.document_id == pat_a_doc).first()
    if p_a:
        db.query(Appointment).filter(Appointment.patient_id == p_a.id).delete()
        db.delete(p_a)
    p_b = db.query(Patient).filter(Patient.document_id == pat_b_doc).first()
    if p_b:
        db.query(Appointment).filter(Appointment.patient_id == p_b.id).delete()
        db.delete(p_b)
    db.commit()

print("\n" + "=" * 75)
print("¡TODAS LAS PRUEBAS MULTI-DOCTOR Y AISLAMIENTO PASARON AL 100%!")
print("=" * 75)
