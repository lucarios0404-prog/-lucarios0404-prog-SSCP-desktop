import sys
import uuid
from pathlib import Path
from datetime import date, timedelta
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.core.initial_data import seed_initial_data_if_empty

def run_test():
    print("======================================================================")
    print("  TEST: OFFLINE-FIRST MOBILE STORE-AND-FORWARD SYNCHRONIZATION")
    print("======================================================================")

    # 1. Asegurar base de datos inicializada
    with SessionLocal() as db:
        seed_initial_data_if_empty(db)

    client = TestClient(app)

    # 2. Login de Secretaria en Móvil
    print("\n[1/5] Autenticación de Secretaria móvil...")
    res_login = client.post("/api/mobile/login", json={
        "email": "secretaria@sscp.com",
        "password": "password123"
    })
    assert res_login.status_code == 200, f"Error de login: {res_login.text}"
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  -> Login exitoso. Token de sesión obtenido.")

    # 3. Simular lote generado en el celular mientras la PC estuvo apagada
    print("\n[2/5] Enviando lote de datos creados Offline en el celular (POST /api/mobile/sync/batch)...")
    suffix = uuid.uuid4().hex[:6]
    uid_p1 = f"patient-uuid-{suffix}"
    uid_a1 = f"appt-uuid-{suffix}-1"
    uid_a2 = f"appt-uuid-{suffix}-2"
    unique_phone = f"809-{suffix[:3]}-{suffix[3:]}"
    unique_fn = f"Marcos_{suffix}"

    target_test_date = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")

    payload = {
        "patients": [
            {
                "client_uuid": uid_p1,
                "first_name": unique_fn,
                "last_name": "OfflineTest",
                "document_id": f"TEST-{suffix}",
                "phone": unique_phone,
                "date_of_birth": "1992-05-14",
                "gender": "M",
                "allergies": "Amoxicilina",
                "insurance_name": "Senasa Contributivo"
            }
        ],
        "appointments": [
            # Cita para el paciente nuevo creado offline
            {
                "client_uuid": uid_a1,
                "patient_client_uuid": uid_p1,
                "date": target_test_date,
                "start_time": "09:30",
                "reason": "Evaluación Cardiológica Diferida",
                "price": 2500.0
            },
            # Cita rápida para un paciente por nombre (resuelto al vuelo)
            {
                "client_uuid": uid_a2,
                "patient_name": "Laura",
                "patient_last_name": "GomezOffline",
                "patient_phone": "829-555-7766",
                "date": target_test_date,
                "start_time": "10:30",
                "reason": "Chequeo General Offline",
                "price": 1800.0
            }
        ]
    }

    res_batch = client.post("/api/mobile/sync/batch", headers=headers, json=payload)
    assert res_batch.status_code == 200, f"Error en batch sync: {res_batch.text}"
    batch_data = res_batch.json()
    print("  -> Respuesta de Central:", batch_data)
    assert batch_data["success"] is True
    assert batch_data["processed_patients"] >= 1
    assert batch_data["processed_appointments"] >= 2
    assert uid_p1 in batch_data["patient_id_map"]
    assert uid_a1 in batch_data["appointment_id_map"]
    assert uid_a2 in batch_data["appointment_id_map"]

    assigned_pid = batch_data["patient_id_map"][uid_p1]
    assigned_aid = batch_data["appointment_id_map"][uid_a1]
    print(f"  -> Paciente UUID '{uid_p1}' reconciliado en SQLite como ID #{assigned_pid}")
    print(f"  -> Cita UUID '{uid_a1}' asignada en SQLite como ID #{assigned_aid}")

    # 4. Probar Idempotencia (re-envío de la misma cola offline no duplica)
    print("\n[3/5] Probando Idempotencia: reenviar el mismo lote no debe duplicar registros...")
    res_idempotent = client.post("/api/mobile/sync/batch", headers=headers, json=payload)
    assert res_idempotent.status_code == 200
    idem_data = res_idempotent.json()
    assert idem_data["appointment_id_map"][uid_a1] == assigned_aid
    print(f"  -> Idempotencia confirmada: La cita {assigned_aid} fue reconocida y preservada sin duplicarse.")

    # 5. Probar Delta Pull para que la APK hidrate su caché local
    print("\n[4/5] Probando Delta Pull (GET /api/mobile/sync/delta)...")
    res_delta = client.get(f"/api/mobile/sync/delta?target_date={target_test_date}", headers=headers)
    assert res_delta.status_code == 200, f"Error en delta: {res_delta.text}"
    delta_data = res_delta.json()
    print(f"  -> Delta recibido: {delta_data['total_patients']} pacientes, {delta_data['total_appointments']} citas.")
    assert delta_data["total_patients"] > 0
    assert any(a["id"] == assigned_aid for a in delta_data["appointments"])
    print("  -> La cita sincronizada aparece correctamente en la agenda delta del doctor.")

    # 6. Verificación en Base de Datos SQLite
    print("\n[5/5] Verificación directa en base de datos SQLite...")
    with SessionLocal() as db:
        p = db.query(Patient).filter(Patient.id == assigned_pid).first()
        assert p is not None
        assert p.first_name == unique_fn
        assert p.allergies == "Amoxicilina"

        a = db.query(Appointment).filter(Appointment.id == assigned_aid).first()
        assert a is not None
        assert a.patient_id == assigned_pid
        assert str(a.date) == target_test_date
        assert a.start_time.strftime("%H:%M") == "09:30"
        print(f"  -> Registro en SQLite verificado al 100%: Cita '{a.reason}' para '{p.first_name} {p.last_name}' el {a.date} a las {a.start_time}.")

    print("\n======================================================================")
    print("  TODAS LAS PRUEBAS DE SINCRONIZACIÓN OFFLINE-FIRST PASARON CON ÉXITO")
    print("======================================================================")

if __name__ == "__main__":
    run_test()
