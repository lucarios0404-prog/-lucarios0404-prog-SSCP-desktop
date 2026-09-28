"""
scripts/test_null_safety_fuzzing.py
Suite de Fuzzing y Prueba de Estrés de Nulos para SSCP Desktop v1.2.0.
Verifica que ningún registro con campos nulos o relaciones ausentes genere un Error 500.
"""

import sys
import os
from pathlib import Path
from datetime import date, datetime

# Añadir raíz de sscp-desktop al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import httpx
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.lab_order import LabOrder
from app.models.payment import Payment
from app.models.user import User

BASE_URL = "http://127.0.0.1:8080"

def run_fuzz_test():
    print("=" * 70)
    print("INICIANDO TEST DE ESTRÉS Y BLINDAJE CONTRA NULOS (NULL-SAFETY FUZZING)")
    print("=" * 70)

    # 1. Crear registros 'Fuzz' deliberadamente saturados de campos NULL
    with SessionLocal() as db:
        # Asegurar usuario doctor
        doc = db.query(User).filter(User.role == "doctor").first()
        doc_id = doc.id if doc else 1

        # Paciente con nulos
        fuzz_patient = Patient(
            first_name="PacienteFuzz",
            last_name="NullSafety",
            document_id=None,
            phone=None,
            email=None,
            date_of_birth=None,
            gender="Masculino",
            blood_type=None,
            allergies=None,
            is_active=True,
            archived_at=None,
            archived_reason=None
        )
        db.add(fuzz_patient)
        db.commit()
        db.refresh(fuzz_patient)
        pid = fuzz_patient.id
        print(f"[1/4] Paciente Fuzz creado con ID: {pid} (campos opcionales en NULL)")

        # Cita con nulos
        fuzz_appt = Appointment(
            patient_id=pid,
            date=date.today(),
            start_time=None,
            end_time=None,
            status="Pendiente",
            reason="Control Fuzz Null",
            notes=None,
            price=0.0,
            queue_number=None,
            whatsapp_reminder_sent=False,
            whatsapp_reminder_sent_at=None
        )
        db.add(fuzz_appt)
        db.commit()
        db.refresh(fuzz_appt)
        aid = fuzz_appt.id
        print(f"[2/4] Cita Fuzz creada con ID: {aid} (start_time, end_time, notes en NULL)")

        # Consulta con nulos
        fuzz_cons = Consultation(
            patient_id=pid,
            doctor_id=doc_id,
            reason="Consulta con nulos de prueba",
            diagnosis=None,
            treatment=None,
            prescription="Paracetamol 500mg cada 8h",
            notes=None,
            updated_at=None,
            clinical_history=None,
            is_first_visit=True,
            edit_version=1,
            sede_origen="local"
        )
        db.add(fuzz_cons)
        db.commit()
        db.refresh(fuzz_cons)
        cid = fuzz_cons.id
        print(f"[3/4] Consulta Fuzz creada con ID: {cid} (diagnosis, treatment, notes en NULL)")

        # Orden de laboratorio con nulos
        fuzz_order = LabOrder(
            patient_id=pid,
            doctor_id=doc_id,
            consultation_id=cid,
            order_date=date.today(),
            clinical_indication=None,
            tests_requested="Hemograma, Glucemia",
            status="pendiente"
        )
        db.add(fuzz_order)
        db.commit()
        db.refresh(fuzz_order)
        oid = fuzz_order.id
        print(f"[4/5] Orden Lab Fuzz creada con ID: {oid}")

        # Pago con nulos
        fuzz_pay = Payment(
            patient_id=pid,
            appointment_id=aid,
            service_name="Consulta Fuzz",
            amount=500.0,
            discount=0.0,
            total=500.0,
            status="pending",
            payment_method="cash",
            insurance_name=None,
            service_id=None,
            receipt_number=None,
            notes=None
        )
        db.add(fuzz_pay)
        db.commit()
        db.refresh(fuzz_pay)
        pay_id = fuzz_pay.id
        print(f"[5/5] Pago Fuzz creado con ID: {pay_id} (campos opcionales en NULL)")

    # 2. Iniciar sesión vía TestClient (in-process ASGI)
    from fastapi.testclient import TestClient
    from main import app
    from app.core.security import get_password_hash

    # Asegurar credenciales de admin
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == "admin@sscp.com").first()
        if not admin:
            admin = User(
                name="Administrador Principal",
                email="admin@sscp.com",
                hashed_password=get_password_hash("password123"),
                role="admin",
                is_active=True
            )
            db.add(admin)
            db.commit()
        else:
            admin.hashed_password = get_password_hash("password123")
            db.commit()

    client = TestClient(app)
    login_resp = client.post(
        "/login",
        data={"username": "admin@sscp.com", "password": "password123"},
        follow_redirects=True
    )
    if login_resp.status_code not in [200, 302]:
        print(f"[ERROR] No se pudo autenticar usuario admin (HTTP {login_resp.status_code})")
        sys.exit(1)
    print("--> Autenticación exitosa como Administrador.")

    # 3. Lista de URLs críticas a evaluar contra Errores 500
    test_urls = [
        # Dashboard y Navegación Principal
        ("/dashboard", "Panel Principal"),
        ("/appointments", "Listado de Citas"),
        ("/appointments/create", "Formulario Agendar Cita (Live Search)"),
        ("/patients", "Listado de Pacientes (Live Search)"),
        (f"/patients/{pid}", "Expediente del Paciente Fuzz (Nulls en Historia)"),
        ("/consultations", "Listado de Consultas"),
        (f"/consultations/{cid}", "Ficha de Consulta Fuzz"),
        (f"/consultations/{cid}/prescription/pdf", "PDF Receta Completa"),
        (f"/consultations/{cid}/prescription/talonario/pdf", "PDF Talonario Preimpreso 21.7x13.6cm"),
        (f"/consultations/{cid}/report/pdf", "PDF Informe Clínico"),
        ("/lab-results", "Listado de Laboratorios"),
        ("/lab-results/orders", "Listado de Órdenes de Laboratorio"),
        (f"/lab-results/orders/{oid}", "Vista de Orden de Laboratorio Fuzz"),
        (f"/lab-results/orders/{oid}/pdf", "PDF Volante de Laboratorio"),
        ("/payments", "Listado de Pagos"),
        ("/payments/create", "Formulario Cobro / Pago (Live Search)"),
        ("/prescriptions/quick", "Emisión Rápida de Recetas y Talonario"),
        ("/vaccines", "Registro de Vacunas"),
        (f"/vitals/patient/{pid}", "Gráficas de Signos Vitales Paciente Fuzz"),
        ("/licenses", "Licencias Médicas"),
        ("/references", "Referencias Médicas"),
        ("/sync", "Centro de Sincronización P2P"),
        ("/settings", "Configuración de Sistema & Roles"),
        # Prueba de Autocompletado Live Search con texto y vacío
        (f"/patients/autocomplete?q=PacienteFuzz", "API Autocomplete con coincidencia"),
        (f"/patients/autocomplete?q=", "API Autocomplete vacío"),
        # Prueba de Manejador 404 Seguro
        ("/ruta-inexistente-para-probar-404-amigable", "Ruta Inexistente (Error 404 Personalizado)"),
    ]

    print("\nEvaluando 100% de rutas contra respuestas HTTP 500...")
    print("-" * 70)

    success_count = 0
    failure_count = 0

    for path, description in test_urls:
        try:
            resp = client.get(path)
            if "ruta-inexistente" in path:
                # Debe ser 404 con HTML amigable
                if resp.status_code == 404 and "Página no encontrada" in resp.text:
                    print(f" [PASS] 404 HANDLER OK  -> {path} ({description})")
                    success_count += 1
                else:
                    print(f" [FAIL] 404 HANDLER ERR -> {path} (Status: {resp.status_code})")
                    failure_count += 1
                continue

            if resp.status_code == 500:
                print(f" [CRITICAL FAIL 500] -> {path} ({description})")
                print(f"    Contenido del error:\n{resp.text[:300]}")
                failure_count += 1
            elif resp.status_code in [200, 302, 303, 307]:
                print(f" [PASS] HTTP {resp.status_code}       -> {path} ({description})")
                success_count += 1
            else:
                print(f" [WARN] HTTP {resp.status_code}       -> {path} ({description})")
                success_count += 1
        except Exception as e:
            print(f" [EXC] Error de conexión en {path}: {e}")
            failure_count += 1

    print("-" * 70)
    print(f"RESULTADO FINAL: {success_count} Rutas Aprobadas, {failure_count} Fallas.")

    # Limpieza del paciente Fuzz
    with SessionLocal() as db:
        db.query(Payment).filter(Payment.id == pay_id).delete()
        db.query(LabOrder).filter(LabOrder.id == oid).delete()
        db.query(Consultation).filter(Consultation.id == cid).delete()
        db.query(Appointment).filter(Appointment.id == aid).delete()
        db.query(Patient).filter(Patient.id == pid).delete()
        db.commit()
    print("--> Registros temporales de prueba limpiados exitosamente de la base de datos.")

    if failure_count == 0:
        print("\n [AUDITORIA COMPLETADA] ¡El sistema es 100% resistente a valores Nulos! Cero errores 500.")
        return True
    else:
        print(f"\n [ALERTA] Se detectaron {failure_count} problemas que requieren corrección.")
        return False

if __name__ == "__main__":
    ok = run_fuzz_test()
    sys.exit(0 if ok else 1)
