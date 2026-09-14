import sys
import uuid
import requests
from datetime import date, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8080"
session = requests.Session()

def test_login():
    print("[TEST 1] Iniciar sesion...")
    login_data = {
        "username": "admin@sscp.com",
        "password": "password123"
    }
    r = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    assert r.status_code == 200, f"Error en login: {r.status_code}"
    assert "Panel Principal" in r.text or "Dashboard" in r.text
    print("  -> Login exitoso.")

def test_create_patient():
    print("[TEST 2] Crear paciente dinamico para pruebas clinicas...")
    unique_doc = f"402-{uuid.uuid4().hex[:7]}-1"
    patient_data = {
        "first_name": "Laura",
        "last_name": "Gomez",
        "document_id": unique_doc,
        "phone": "829-555-4321",
        "email": f"laura.{uuid.uuid4().hex[:5]}@clinica.local",
        "blood_type": "A+",
        "allergies": "Penicilina, Sulfas"
    }
    r = session.post(f"{BASE_URL}/patients/create", data=patient_data, allow_redirects=True)
    assert r.status_code == 200, f"Error al crear paciente: {r.status_code}"
    # Obtener el ID del paciente recién creado buscando en la lista
    r_list = session.get(f"{BASE_URL}/patients/?q={unique_doc}")
    assert unique_doc in r_list.text
    
    # Extraer patient_id
    import re
    m = re.search(r'/patients/(\d+)', r_list.text)
    assert m, "No se encontro el ID del paciente en la lista"
    patient_id = int(m.group(1))
    print(f"  -> Paciente creado con ID {patient_id} (DNI: {unique_doc}).")
    return patient_id

def test_vital_signs(patient_id):
    print("[TEST 3] Signos vitales & F11 Curvas de evolucion...")
    # Registro de signo vital 1
    vitals_data_1 = {
        "weight_kg": 72.5,
        "height_cm": 168.0,
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "heart_rate": 75,
        "respiratory_rate": 18,
        "temperature_c": 36.8,
        "oxygen_saturation": 98.0,
        "glucose_mg_dl": 95.0,
        "notes": "Signos dentro de rangos normales"
    }
    r = session.post(f"{BASE_URL}/vitals/patient/{patient_id}/create", data=vitals_data_1, allow_redirects=True)
    assert r.status_code == 200, f"Error al registrar signo vital: {r.status_code}"
    assert "72.5" in r.text
    assert "120/80" in r.text
    # Verificar cálculo automático de IMC: 72.5 / (1.68^2) = ~25.7
    assert "25.7" in r.text

    # Registro de signo vital 2 para curva
    vitals_data_2 = {
        "weight_kg": 71.8,
        "height_cm": 168.0,
        "systolic_bp": 118,
        "diastolic_bp": 78,
        "heart_rate": 72,
        "respiratory_rate": 16,
        "temperature_c": 36.6,
        "oxygen_saturation": 99.0,
        "glucose_mg_dl": 92.0,
        "notes": "Evolución favorable en control"
    }
    r2 = session.post(f"{BASE_URL}/vitals/patient/{patient_id}/create", data=vitals_data_2, allow_redirects=True)
    assert r2.status_code == 200

    # Test F11 API de datos para Chart.js
    r_api = session.get(f"{BASE_URL}/vitals/patient/{patient_id}/api/evolution")
    assert r_api.status_code == 200
    data = r_api.json()
    assert len(data["weight"]) >= 2
    assert 72.5 in data["weight"] and 71.8 in data["weight"]
    assert 120 in data["systolic"] and 118 in data["systolic"]
    print("  -> Signos vitales registrados, IMC calculado y API F11 verificada con exito.")

def test_lab_results(patient_id):
    print("[TEST 4] Modulo de Laboratorio con alerta de anormalidad...")
    today_str = date.today().strftime("%Y-%m-%d")
    lab_data = {
        "patient_id": patient_id,
        "test_name": "Hemograma Completo",
        "test_category": "Hematología",
        "result_date": today_str,
        "summary_findings": "Plaquetopenia severa: 48,000 /uL. Leucocitos normales.",
        "is_abnormal": True
    }
    r = session.post(f"{BASE_URL}/lab-results/create", data=lab_data, allow_redirects=True)
    assert r.status_code == 200, f"Error al crear resultado de laboratorio: {r.status_code}"
    assert "Plaquetopenia severa" in r.text
    assert "Anormal" in r.text or "ANORMAL" in r.text or "Valor Alterado" in r.text
    print("  -> Resultado de laboratorio con alerta de valor anormal verificado.")

def test_vaccines(patient_id):
    print("[TEST 5] Modulo de Vacunas (F12) e inmunizacion...")
    today = date.today()
    next_due = today + timedelta(days=60)
    vaccine_data = {
        "patient_id": patient_id,
        "vaccine_name": "Hepatitis B Recombinante",
        "dose": "1ra Dosis",
        "application_date": today.strftime("%Y-%m-%d"),
        "next_due_date": next_due.strftime("%Y-%m-%d"),
        "lot_number": "LOT-HEP-2026-X",
        "administered_by": "Lic. Maria enfermera",
        "notes": "Toleró sin reacciones adversas inmediatas"
    }
    r = session.post(f"{BASE_URL}/vaccines/create", data=vaccine_data, allow_redirects=True)
    assert r.status_code == 200, f"Error al registrar vacuna: {r.status_code}"
    assert "Hepatitis B Recombinante" in r.text
    assert "LOT-HEP-2026-X" in r.text
    assert next_due.strftime("%d/%m/%Y") in r.text
    print("  -> Registro de vacuna y proxima dosis (F12) verificado con exito.")

def test_messages(patient_id):
    print("[TEST 6] Mensajeria interna entre personal...")
    # Listar bandeja
    r = session.get(f"{BASE_URL}/messages")
    assert r.status_code == 200 or r.status_code == 307
    
    # Enviar mensaje interno
    msg_data = {
        "recipient_id": "", # Todos
        "patient_id": patient_id,
        "subject": "Interconsulta urgente",
        "content": "Favor preparar expediente para interconsulta con cardiologia.",
        "priority": "urgent"
    }
    r_send = session.post(f"{BASE_URL}/messages/send", data=msg_data, allow_redirects=True)
    assert r_send.status_code == 200
    assert "Interconsulta urgente" in r_send.text
    assert "preparar expediente" in r_send.text
    print("  -> Mensajeria interna verificada con exito.")

def test_inventory():
    print("[TEST 7] Control de Inventario, alertas de stock bajo y movimientos...")
    item_name = f"Amoxicilina 500mg - Test {uuid.uuid4().hex[:5]}"
    item_data = {
        "name": item_name,
        "category": "Medicamento",
        "description": "Cápsulas antibióticas para tratamiento oral",
        "stock": 3,
        "min_stock": 10,
        "unit": "Caja",
        "price": 280.0
    }
    # 1. Crear producto con stock menor al mínimo para validar alerta de Stock Bajo
    r = session.post(f"{BASE_URL}/inventory/create", data=item_data, allow_redirects=True)
    assert r.status_code == 200, f"Error al crear producto en inventario: {r.status_code}"
    assert item_name in r.text
    assert "Stock Bajo" in r.text
    
    # 2. Extraer ID del artículo
    import re
    m = re.search(r'/inventory/(\d+)', r.text)
    assert m, "No se encontró enlace al artículo creado en el inventario"
    item_id = int(m.group(1))
    
    # 3. Registrar movimiento de Entrada (+20)
    mov_in = {
        "type": "in",
        "quantity": 20,
        "notes": "Recepción de pedido farmacéutico mayorista"
    }
    r_in = session.post(f"{BASE_URL}/inventory/{item_id}/movement", data=mov_in, allow_redirects=True)
    assert r_in.status_code == 200
    # Existencia debe ser 3 + 20 = 23 -> Stock Óptimo
    assert "23" in r_in.text
    assert "Stock Óptimo" in r_in.text
    assert "Recepción de pedido farmacéutico" in r_in.text
    
    # 4. Registrar movimiento de Salida (-5)
    mov_out = {
        "type": "out",
        "quantity": 5,
        "notes": "Suministro aplicado a paciente en sala"
    }
    r_out = session.post(f"{BASE_URL}/inventory/{item_id}/movement", data=mov_out, allow_redirects=True)
    assert r_out.status_code == 200
    # Existencia debe ser 23 - 5 = 18
    assert "18" in r_out.text
    assert "Suministro aplicado a paciente" in r_out.text
    print("  -> Inventario, alerta de stock mínimo y registro Kardex verificados con exito.")

if __name__ == "__main__":
    print("==================================================")
    print("INICIANDO SUITE DE PRUEBAS AUTOMATIZADAS - FASE 3")
    print("==================================================")
    test_login()
    pid = test_create_patient()
    test_vital_signs(pid)
    test_lab_results(pid)
    test_vaccines(pid)
    test_messages(pid)
    test_inventory()
    print("==================================================")
    print("[RESULTADO] 7/7 PRUEBAS DE FASE 3 COMPLETADAS Y VERIFICADAS")
    print("==================================================")
