import requests
import json
import time
import sys

# Ensure UTF-8 output even on Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8080"
session = requests.Session()

def run_tests():
    print("Iniciando pruebas de integración SSCP Desktop...")
    
    # 1. Test Login
    print("1. Probando Login...")
    response = session.post(f"{BASE_URL}/login", data={
        "username": "admin@sscp.com",
        "password": "password123"
    }, allow_redirects=False)
    
    if response.status_code == 302 and "access_token" in response.cookies:
        print("[OK] Login exitoso. Cookie recibida.")
    else:
        print(f"[FAIL] Fallo en Login. Status: {response.status_code}")
        return False
        
    # 2. Test Acceso a Dashboard
    print("2. Probando acceso a Dashboard...")
    response = session.get(f"{BASE_URL}/dashboard")
    if response.status_code == 200 and "Bienvenido, Administrador" in response.text:
        print("[OK] Acceso a Dashboard exitoso.")
    else:
        print(f"[FAIL] Fallo en acceso a Dashboard. Status: {response.status_code}")
        return False
        
    # 3. Test Acceso a Pacientes (GET)
    print("3. Probando listado de pacientes...")
    response = session.get(f"{BASE_URL}/patients")
    if response.status_code == 200 and "Nuevo Paciente" in response.text:
        print("[OK] Acceso a Pacientes exitoso.")
    else:
        print(f"[FAIL] Fallo en listado de pacientes. Status: {response.status_code}")
        return False
        
    # 4. Test Crear Paciente (POST)
    print("4. Probando crear paciente...")
    response = session.post(f"{BASE_URL}/patients/create", data={
        "first_name": "Juan",
        "last_name": "Perez",
        "document_id": "V-12345678",
        "phone": "0414-1234567",
        "email": "juan@example.com"
    }, allow_redirects=False)
    if response.status_code == 303:
        print("[OK] Paciente creado exitosamente.")
    else:
        print(f"[FAIL] Fallo al crear paciente. Status: {response.status_code}")
        return False
        
    # 5. Test Obtener ID del Paciente y Citas (GET)
    print("5. Probando agendar cita...")
    response = session.get(f"{BASE_URL}/appointments/create")
    if response.status_code == 200 and "Juan Perez" in response.text:
        # Extraer el ID del paciente creado del HTML
        # Buscamos value="(\d+)">Juan Perez
        import re
        m = re.search(r'value="(\d+)"[^>]*>Juan Perez', response.text)
        patient_id = m.group(1) if m else "1"
        
        response = session.post(f"{BASE_URL}/appointments/create", data={
            "patient_id": patient_id,
            "date": "2026-09-15",
            "start_time": "10:00",
            "end_time": "11:00",
            "reason": "Chequeo de rutina"
        }, allow_redirects=False)
        
        if response.status_code == 303:
            print("[OK] Cita agendada exitosamente.")
            
            # Verificar en lista de citas
            response = session.get(f"{BASE_URL}/appointments")
            if response.status_code == 200 and "Chequeo de rutina" in response.text:
                print("[OK] Cita verificada en el listado.")
                return True
            else:
                print("[FAIL] Fallo verificando la cita en la lista.")
                return False
        else:
            print(f"[FAIL] Fallo al crear cita. Status: {response.status_code}")
            return False
    else:
        print("[FAIL] No se encontró al paciente en el select de citas.")
        return False

if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
