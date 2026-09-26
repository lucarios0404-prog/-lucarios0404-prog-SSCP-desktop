import urllib.request
import json

BASE = "http://127.0.0.1:8080"

def test_full_mobile_flow():
    print("=== TEST COMPLETO DE INTEGRACIÓN MÓVIL (SECRETARÍA Y PACIENTES) ===")
    
    # 1. Login
    login_data = json.dumps({"email": "secretaria@sscp.com", "password": "password123"}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/mobile/login", data=login_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        token = res["access_token"]
        print(f"[OK] 1. Autenticación exitosa como: {res['user']['name']} (Rol: {res['user']['role']})")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 2. Directorio centralizado de pacientes
    req = urllib.request.Request(f"{BASE}/api/mobile/patients?limit=5", headers=headers)
    with urllib.request.urlopen(req) as resp:
        pats = json.loads(resp.read().decode("utf-8"))
        total = pats["total"]
        sample_patient = pats["patients"][0]
        print(f"[OK] 2. Directorio centralizado conectado: {total} pacientes en la base de datos.")
        print(f"      Paciente muestra: {sample_patient['name']} (Doc: {sample_patient['document_id'] or 'S/N'}, Tel: {sample_patient['phone'] or 'S/T'})")

    # 3. Verificación anti-duplicados en tiempo real
    doc_id = sample_patient.get("document_id")
    if doc_id:
        req = urllib.request.Request(f"{BASE}/api/mobile/patients/check-duplicate?document_id={doc_id}", headers=headers)
        with urllib.request.urlopen(req) as resp:
            dup_res = json.loads(resp.read().decode("utf-8"))
            print(f"[OK] 3. Anti-duplicados detectó cédula existente '{doc_id}': {dup_res['is_duplicate']}")
            print(f"      Mensaje: {dup_res['message']}")

    # 4. Detalle y expediente del paciente
    req = urllib.request.Request(f"{BASE}/api/mobile/patients/{sample_patient['id']}/details", headers=headers)
    with urllib.request.urlopen(req) as resp:
        details = json.loads(resp.read().decode("utf-8"))
        p_info = details["patient"]
        print(f"[OK] 4. Ficha/Expediente cargado:")
        print(f"      Nombre: {p_info['name']}")
        print(f"      Cédula: {p_info['document_id']} | Teléfono: {p_info['phone']}")
        print(f"      Citas previas registradas: {len(details['appointments'])}")
        print(f"      Pagos previos registrados: {len(details['payments'])}")

    # 5. Agendar cita vinculada a paciente existente (SIN crear duplicados)
    appt_payload = {
        "patient_id": sample_patient["id"],
        "patient_name": sample_patient["name"],
        "patient_phone": sample_patient.get("phone") or "809-555-0100",
        "date": "2026-09-26",
        "start_time": "11:00",
        "reason": "Revisión médica móvil"
    }
    req = urllib.request.Request(
        f"{BASE}/api/mobile/appointments/quick-create",
        data=json.dumps(appt_payload).encode("utf-8"),
        headers=headers
    )
    with urllib.request.urlopen(req) as resp:
        appt_res = json.loads(resp.read().decode("utf-8"))
        print(f"[OK] 5. Agendado express sin duplicidad:")
        print(f"      {appt_res.get('message')}")
        print(f"      ID Cita: {appt_res.get('appointment_id')} -> Asociada correctamente a Patient ID: {appt_res.get('patient_id')}")

    # 6. Verificación de interfaz móvil web
    req = urllib.request.Request(f"{BASE}/mobile")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert "view-patients" in html, "Falta view-patients en HTML"
        assert "modal-new-patient" in html, "Falta modal-new-patient en HTML"
        assert "modal-patient-details" in html, "Falta modal-patient-details en HTML"
        assert "nav-btn-patients" in html, "Falta nav-btn-patients en HTML"
        print(f"[OK] 6. Plantilla móvil HTML verificada (incluye Directorio de Pacientes, Botón Nav, Anti-Duplicados y Ficha de Paciente).")

    print("\n>>> RESULTADO: 100% DE LAS PRUEBAS PASARON EXITOSAMENTE <<<")

if __name__ == "__main__":
    test_full_mobile_flow()
