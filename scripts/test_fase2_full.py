import requests
import re
import sys

# Ensure UTF-8 output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8080"
session = requests.Session()

def run_fase2_tests():
    print("=== INICIANDO PRUEBAS COMPLETAS DE FASE 2: SSCP DESKTOP ===")
    
    # 1. Login
    print("\n[1/7] Probando Login de Administrador...")
    res = session.post(f"{BASE_URL}/login", data={
        "username": "admin@sscp.com",
        "password": "password123"
    }, allow_redirects=False)
    assert res.status_code == 302 and "access_token" in res.cookies, f"Fallo login: {res.status_code}"
    print("[OK] Sesion iniciada correctamente.")

    # 2. Dashboard con Métricas
    print("\n[2/7] Probando Dashboard con Métricas en Vivo...")
    res = session.get(f"{BASE_URL}/dashboard")
    assert res.status_code == 200, f"Fallo dashboard: {res.status_code}"
    assert "Panel de Control" in res.text, "Texto del dashboard ausente"
    assert "Total Pacientes" in res.text, "KPI total pacientes ausente"
    assert "Saldo por Cobrar (F13)" in res.text, "KPI saldo por cobrar ausente"
    print("[OK] Dashboard renderizado con KPIs en vivo.")

    # 3. Pacientes: Creación, Búsqueda y Ficha
    print("\n[3/7] Probando Módulo de Pacientes...")
    import random
    rand_doc = f"402-{random.randint(1000000, 9999999)}-0"
    res = session.post(f"{BASE_URL}/patients/create", data={
        "first_name": "Carlos",
        "last_name": "Mendoza",
        "document_id": rand_doc,
        "phone": "809-555-8888",
        "email": f"carlos.{random.randint(100,999)}@correo.local",
        "blood_type": "O+"
    }, allow_redirects=True)
    assert res.status_code == 200, f"Fallo crear paciente: {res.status_code}"
    assert "Carlos Mendoza" in res.text, "Nombre del paciente no encontrado en la ficha"
    print("[OK] Paciente Carlos Mendoza creado y ficha visualizada.")

    # Extraer ID del paciente de la URL
    patient_id_match = re.search(r'/patients/(\d+)', res.url)
    assert patient_id_match, f"No se pudo extraer patient_id de {res.url}"
    patient_id = patient_id_match.group(1)

    # Probar búsqueda de paciente
    res = session.get(f"{BASE_URL}/patients?q=Mendoza")
    assert res.status_code == 200 and "Carlos Mendoza" in res.text, "Fallo búsqueda de paciente"
    print("[OK] Búsqueda de paciente por apellido 'Mendoza' funciona correctamente.")

    # 4. Citas: Atajos F1 y Citas Recurrentes F14
    print("\n[4/7] Probando Módulo de Citas (F1 Atajos y F14 Recurrencia)...")
    res = session.get(f"{BASE_URL}/appointments/create?patient_id={patient_id}")
    assert res.status_code == 200 and "+7 Días" in res.text, "Fallo renderizado de atajos F1"
    print("[OK] Formulario de agendamiento con atajos de fecha F1 verificado.")

    # Agendar 3 citas recurrentes mensuales (F14)
    res = session.post(f"{BASE_URL}/appointments/create", data={
        "patient_id": patient_id,
        "date": "2026-09-20",
        "start_time": "10:00",
        "end_time": "10:30",
        "reason": "Control Hipertensión",
        "is_recurring": "true",
        "recurrence_count": "3",
        "recurrence_interval_days": "30"
    }, allow_redirects=False)
    assert res.status_code == 303, f"Fallo agendar cita recurrente: {res.status_code}"

    # Verificar citas creadas en listado
    res = session.get(f"{BASE_URL}/appointments")
    assert res.status_code == 200, "Fallo listado de citas"
    assert "Control Hipertensión" in res.text, "Cita base no aparece en el listado"
    assert "Recurrente (F14)" in res.text, "Badge de cita recurrente F14 no aparece"
    print("[OK] Citas recurrentes F14 creadas y visibles en la agenda.")

    # 5. Pagos: Registro de cobro pendiente y verificación de F8 (Saldo) y F13 (Cuentas por cobrar)
    print("\n[5/7] Probando Módulo de Pagos, Saldo Pendiente (F8) y Cuentas por Cobrar (F13)...")
    res = session.post(f"{BASE_URL}/payments/create", data={
        "patient_id": patient_id,
        "service_name": "Consulta de Especialidad",
        "amount": "2500.00",
        "discount": "500.00",
        "status": "pending",
        "payment_method": "card",
        "receipt_number": "REC-TEST-PENDING",
        "notes": "Deuda pendiente acordada a fin de mes"
    }, allow_redirects=False)
    assert res.status_code == 303, f"Fallo crear pago: {res.status_code}"
    print("[OK] Cobro pendiente por RD$ 2000.00 registrado.")

    # Verificar F8: Badge de Saldo Pendiente en ficha del paciente
    res = session.get(f"{BASE_URL}/patients/{patient_id}")
    assert res.status_code == 200
    assert "Saldo Pendiente: RD$ 2000.00" in res.text, "F8 Badge de saldo pendiente no encontrado en ficha"
    print("[OK] F8: Badge de saldo pendiente visible en la ficha del paciente (RD$ 2000.00).")

    # Verificar F8: Badge en la tabla de pacientes
    res = session.get(f"{BASE_URL}/patients")
    assert "RD$ 2000.00" in res.text, "F8 Saldo no encontrado en tabla de pacientes"
    print("[OK] F8: Saldo pendiente visible en la lista general de pacientes.")

    # Verificar F13: Pestaña Cuentas por Cobrar
    res = session.get(f"{BASE_URL}/payments?status=receivables")
    assert res.status_code == 200
    assert "Carlos Mendoza" in res.text, "Paciente deudor no encontrado en Cuentas por Cobrar F13"
    assert "2000.00" in res.text, "Monto de deuda no encontrado en Cuentas por Cobrar F13"
    print("[OK] F13: Módulo Cuentas por Cobrar muestra correctamente al paciente con su deuda.")

    # Cobrar el pago pendiente
    m_payment_id = re.search(r'action="/payments/(\d+)/pay"', res.text)
    if m_payment_id:
        pay_id = m_payment_id.group(1)
        res = session.post(f"{BASE_URL}/payments/{pay_id}/pay", allow_redirects=False)
        assert res.status_code == 303
        print(f"[OK] Pago #{pay_id} marcado como cobrado exitosamente.")

        # Verificar que saldo volvió a 0 / al día
        res = session.get(f"{BASE_URL}/patients/{patient_id}")
        assert "Al día (Sin deuda)" in res.text, "Paciente no figura al día tras el cobro"
        print("[OK] Saldo del paciente actualizado a 'Al día (Sin deuda)'.")

    # 6. Historias Clínicas: Creación con CIE-10 y Edición con Auditoría F3
    print("\n[6/7] Probando Consultas Médicas y Edición de Historia Médica (F3)...")
    res = session.post(f"{BASE_URL}/consultations/create", data={
        "patient_id": patient_id,
        "reason": "Chequeo por cefalea y fatiga",
        "symptoms": "Dolor de cabeza pulsátil holocraneal de 3 días",
        "physical_exam": "PA: 140/90 mmHg, FC: 80 lpm",
        "diagnosis": "I10 - Hipertensión esencial (primaria); R51 - Cefalea",
        "treatment": "Modificación dietética baja en sodio y control tensional",
        "prescription": "Enalapril 10mg VO cada 12h",
        "notes": "Paciente colaborador"
    }, allow_redirects=True)
    assert res.status_code == 200, f"Fallo crear consulta: {res.status_code}"
    assert "I10 - Hipertensión esencial" in res.text, "Diagnóstico CIE-10 no encontrado"
    print("[OK] Consulta médica registrada con códigos CIE-10 y prescripción.")

    # Extraer ID de la consulta creada
    consult_id_match = re.search(r'/consultations/(\d+)', res.url)
    assert consult_id_match, f"No se pudo extraer consultation_id de {res.url}"
    consultation_id = consult_id_match.group(1)

    # Probar F3: Edición post-guardado con justificación
    print("Probando F3: Edición de nota clínica con motivo de auditoría...")
    res = session.post(f"{BASE_URL}/consultations/{consultation_id}/edit", data={
        "reason": "Chequeo por cefalea y fatiga - REVALUADO",
        "symptoms": "Dolor de cabeza pulsátil, mejoría con reposo",
        "physical_exam": "PA: 135/85 mmHg tras reposo",
        "diagnosis": "I10 - Hipertensión esencial; R51 - Cefalea tensional",
        "treatment": "Se ajusta pauta de enalapril y se indica mapa de presión",
        "prescription": "Enalapril 10mg VO en las mañanas",
        "notes": "Revaluado tras 30 min de reposo",
        "edit_reason": "Ajuste de dosis tras reevaluación de presión en reposo"
    }, allow_redirects=True)
    assert res.status_code == 200, f"Fallo editar consulta: {res.status_code}"
    assert "Ajuste de dosis tras reevaluación" in res.text, "Motivo de cambio F3 no aparece en el historial"
    assert "Modificada" in res.text, "Evento de auditoría F3 no reflejado en la vista"
    print("[OK] F3: Historia médica editada y registrada con auditoría médica de autor, fecha y motivo.")

    # 7. Configuración (M10)
    print("\n[7/7] Probando Configuración del Consultorio (M10)...")
    res = session.post(f"{BASE_URL}/settings/", data={
        "clinic_name": "Consultorio Especializado Dr. Antigravity",
        "doctor_name": "Dr. Antigravity Specialist",
        "specialty": "Medicina Interna y Cardiología",
        "phone": "809-555-9000",
        "email": "dr.antigravity@sscp.local",
        "address": "Av. Winston Churchill #50, Torre Médica Piso 4",
        "currency": "RD$",
        "sede_name": "Sede Santo Domingo",
        "tailscale_ip": "100.115.92.10",
        "sync_interval_minutes": "5"
    }, allow_redirects=True)
    assert res.status_code == 200, f"Fallo configuración: {res.status_code}"
    assert "Consultorio Especializado Dr. Antigravity" in res.text, "Nombre de clínica no actualizado"
    assert "100.115.92.10" in res.text, "IP Tailscale no guardada"
    print("[OK] Configuración del consultorio y parámetros multi-sede actualizados y persistidos.")

    print("\n=======================================================")
    print("TODAS LAS PRUEBAS DE LA FASE 2 PASARON SATISFACTORIAMENTE (7/7)")
    print("=======================================================")
    return True

if __name__ == "__main__":
    success = run_fase2_tests()
    if not success:
        sys.exit(1)
