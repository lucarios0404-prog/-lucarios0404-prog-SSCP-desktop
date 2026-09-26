import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.core import security

client = TestClient(app)

def test_mobile_patients_and_quick_appt():
    db = SessionLocal()
    try:
        # 1. Asegurar usuario secretaria
        user = db.query(User).filter(User.email == "secretaria@sscp.com").first()
        if not user:
            user = User(
                email="secretaria@sscp.com",
                name="Ana Secretaria",
                role="secretary",
                hashed_password=security.get_password_hash("Secretaria2026*"),
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        token = security.create_access_token(data={"email": user.email, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Asegurar al menos dos pacientes en el sistema del doctor
        p1 = db.query(Patient).filter(Patient.document_id == "402-1234567-1").first()
        if not p1:
            p1 = Patient(
                first_name="Carlos",
                last_name="Gómez",
                document_id="402-1234567-1",
                phone="809-555-8888",
                allergies="Penicilina",
                is_active=True
            )
            db.add(p1)
            db.commit()
            db.refresh(p1)

        p2 = db.query(Patient).filter(Patient.document_id == "402-9876543-2").first()
        if not p2:
            p2 = Patient(
                first_name="Beatriz",
                last_name="Almonte",
                document_id="402-9876543-2",
                phone="829-555-9999",
                allergies="Ninguna",
                is_active=True
            )
            db.add(p2)
            db.commit()
            db.refresh(p2)

        print("[OK] Pacientes base listos:", p1.id, p1.first_name, p2.id, p2.first_name)

        # 3. Probar endpoint /api/mobile/patients/options
        res = client.get("/api/mobile/patients/options", headers=headers)
        assert res.status_code == 200, f"Error en options: {res.text}"
        data = res.json()
        assert "patients" in data, "No 'patients' field in response"
        assert len(data["patients"]) >= 2, "Menos de 2 pacientes en options"
        print(f"[OK] /api/mobile/patients/options devolvió {len(data['patients'])} pacientes.")
        
        # Verificar formato del display
        first_opt = data["patients"][0]
        print(f"     Muestra de paciente: {first_opt['display']}")
        assert "(" in first_opt["display"] and ")" in first_opt["display"], "Formato de display incorrecto"

        # 4. Probar agendar cita con paciente existente del sistema (sin duplicidad)
        count_before = db.query(Patient).count()
        res_appt = client.post("/api/mobile/appointments/quick-create", headers=headers, json={
            "patient_id": p1.id,
            "date": "2026-09-26",
            "start_time": "14:30",
            "reason": "Control de Presión Arterial"
        })
        assert res_appt.status_code == 200, f"Error creando cita: {res_appt.text}"
        appt_data = res_appt.json()
        assert appt_data["patient_id"] == p1.id, "No se asignó al paciente existente"
        count_after = db.query(Patient).count()
        assert count_after == count_before, "¡Error! Se creó un paciente duplicado cuando se seleccionó un paciente existente"
        print("[OK] Agendar cita con paciente existente funcionó sin crear duplicados.")

        # 5. Probar check-duplicate con teléfono existente
        res_dup = client.get(f"/api/mobile/patients/check-duplicate?phone={p1.phone}", headers=headers)
        assert res_dup.status_code == 200
        dup_data = res_dup.json()
        assert dup_data["is_duplicate"] == True, "No detectó duplicado por teléfono"
        print("[OK] Verificador de duplicados detectó teléfono existente:", dup_data["message"])

        # 6. Probar check-duplicate con cédula existente
        res_dup_doc = client.get(f"/api/mobile/patients/check-duplicate?document_id={p2.document_id}", headers=headers)
        assert res_dup_doc.status_code == 200
        dup_doc_data = res_dup_doc.json()
        assert dup_doc_data["is_duplicate"] == True, "No detectó duplicado por cédula"
        print("[OK] Verificador de duplicados detectó cédula existente:", dup_doc_data["message"])

        # 7. Probar agendar cita creando nuevo paciente (cuando no existe)
        new_phone = "849-555-7766"
        res_new = client.post("/api/mobile/appointments/quick-create", headers=headers, json={
            "patient_name": "Marcos",
            "patient_last_name": "Peña",
            "patient_document_id": "402-7776665-0",
            "patient_phone": new_phone,
            "patient_allergies": "Mariscos",
            "date": "2026-09-26",
            "start_time": "15:00",
            "reason": "Primera Consulta General"
        })
        assert res_new.status_code == 200, f"Error creando nuevo paciente con cita: {res_new.text}"
        created_id = res_new.json()["patient_id"]
        created_p = db.query(Patient).filter(Patient.id == created_id).first()
        assert created_p is not None, "No se guardó el nuevo paciente"
        assert created_p.first_name == "Marcos" and created_p.last_name == "Peña"
        assert created_p.document_id == "402-7776665-0"
        assert created_p.allergies == "Mariscos"
        print("[OK] Cita con nuevo paciente creó correctamente el registro en la base de datos central.")

        # 8. Si se intenta crear otra vez con el mismo teléfono o cédula, no crea duplicado sino que reutiliza
        count_p_before = db.query(Patient).count()
        res_dup_create = client.post("/api/mobile/appointments/quick-create", headers=headers, json={
            "patient_name": "Marcos",
            "patient_last_name": "Peña",
            "patient_document_id": "402-7776665-0",
            "patient_phone": new_phone,
            "date": "2026-09-27",
            "start_time": "10:00",
            "reason": "Seguimiento"
        })
        assert res_dup_create.status_code == 200
        count_p_after = db.query(Patient).count()
        assert count_p_after == count_p_before, "Creó duplicado en vez de vincular al paciente existente"
        assert res_dup_create.json()["patient_id"] == created_id, "No reutilizó el ID existente"
        print("[OK] Protección anti-duplicados impidió duplicar al paciente existente y reutilizó su ID.")

        print("\n>>> TODOS LOS TESTS PASARON EXITOSAMENTE (100% VERIFICADO) <<<")
    finally:
        db.close()

if __name__ == "__main__":
    test_mobile_patients_and_quick_appt()
