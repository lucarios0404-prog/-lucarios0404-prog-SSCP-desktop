import os
import sys
import json
from datetime import datetime, date

# Asegurar path al subproyecto
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, PROJECT_DIR)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.lab_order import LabOrder
from app.models.appointment import Appointment
from app.models.payment import Payment
from app.models.setting import Setting
from app.models.user import User
from app.models.audit_log import ClinicalAuditLog
from app.services.sync_service import SyncService
from app.services.audit_service import AuditService

def run_full_master_suite():
    print("=" * 80)
    print("🚀 INICIANDO BATERÍA INTEGRAL DE PRUEBAS — SSCP v1.2.0 & AUDITORÍA")
    print("=" * 80)

    client = TestClient(app)
    db = SessionLocal()

    # 0. Autenticación de prueba
    from app.core.security import get_password_hash
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

    login_resp = client.post(
        "/login",
        data={"username": "admin@sscp.com", "password": "password123"},
        follow_redirects=False
    )
    assert login_resp.status_code == 302, f"Fallo al autenticar: {login_resp.status_code}"

    # ==========================================
    # TEST 1: FASE 1 — HISTORIA CLÍNICA UNIFICADA
    # ==========================================
    print("\n[TEST 1] Verificando Fase 1: Historia Clínica Unificada...")
    test_patient = db.query(Patient).filter(Patient.document_id == "402-9988776-1").first()
    if not test_patient:
        test_patient = Patient(
            first_name="Carmen",
            last_name="Valdez",
            document_id="402-9988776-1",
            phone="809-555-4321",
            gender="F",
            date_of_birth=date(1990, 5, 12),
            blood_type="O+"
        )
        db.add(test_patient)
        db.commit()
        db.refresh(test_patient)

    # Crear consulta con historia unificada
    unified_text = "MOTIVO: Cefalea intensa de 3 días de evolución.\nEXAMEN: PA 120/80 mmHg, fondo de ojo normal.\nDIAGNÓSTICO: Cefalea tensional."
    resp_create = client.post("/consultations/create", data={
        "patient_id": test_patient.id,
        "reason": "Cefalea recurrente",
        "clinical_history": unified_text,
        "is_first_visit": "true",
        "diagnosis": "Cefalea tensional (G44.2)",
        "treatment": "Paracetamol 500mg c/8h",
        "prescription": "Paracetamol 500mg tab VO c/8h x 3d",
        "notes": "Control si no cede el dolor"
    }, follow_redirects=False)

    assert resp_create.status_code == 303, f"Fallo al crear consulta: {resp_create.status_code}"
    loc = resp_create.headers.get("location")
    c_id = int(loc.split("/")[-1])
    consultation = db.query(Consultation).filter(Consultation.id == c_id).first()
    assert consultation is not None
    assert consultation.clinical_history == unified_text
    assert consultation.is_first_visit == True
    assert consultation.edit_version == 1
    print(f"  ✓ Consulta #{c_id} creada con historia unificada (v1, Primera Visita: Sí)")

    # Editar consulta incrementando versión y registrando auditoría
    edit_text = unified_text + "\nACTUALIZACIÓN: Paciente refiere mejoría parcial con analgésicos."
    resp_edit = client.post(f"/consultations/{c_id}/edit", data={
        "reason": "Cefalea en evolución",
        "clinical_history": edit_text,
        "is_first_visit": "true",
        "diagnosis": "Cefalea tensional (G44.2)",
        "treatment": "Paracetamol 500mg c/8h + Hidratación abundante",
        "prescription": "Paracetamol 500mg tab VO c/8h",
        "notes": "Paciente hidratándose adecuadamente",
        "edit_reason": "Ajuste de hidratación y seguimiento clínico"
    }, follow_redirects=False)

    assert resp_edit.status_code == 303
    db.refresh(consultation)
    assert consultation.edit_version == 2
    assert "Ajuste" in (consultation.edit_history or "")
    print(f"  ✓ Consulta #{c_id} editada correctamente a v{consultation.edit_version} con motivo auditado")

    # ==========================================
    # TEST 2: FASE 2 — BÚSQUEDA EN VIVO (LIVE AUTOCOMPLETE)
    # ==========================================
    print("\n[TEST 2] Verificando Fase 2: Autocomplete en Vivo de Pacientes...")
    resp_auto = client.get("/patients/autocomplete?q=Carmen")
    assert resp_auto.status_code == 200
    auto_data = resp_auto.json()
    assert len(auto_data) > 0
    found_carmen = any(p["document_id"] == "402-9988776-1" for p in auto_data)
    assert found_carmen, "No se encontró a Carmen en autocomplete por nombre"
    print(f"  ✓ Búsqueda en vivo por nombre exitosa: {len(auto_data)} coincidencia(s)")

    resp_auto_dni = client.get("/patients/autocomplete?q=9988776")
    assert resp_auto_dni.status_code == 200
    assert any(p["id"] == test_patient.id for p in resp_auto_dni.json())
    print("  ✓ Búsqueda en vivo por Cédula exitosa")

    # ==========================================
    # TEST 3: FASE 3 — SOLICITUD DE LABORATORIOS DIGITAL EN PDF
    # ==========================================
    print("\n[TEST 3] Verificando Fase 3: Solicitud de Laboratorios Digital...")
    tests_selected = ["Hemograma Completo", "Glucemia en Ayunas", "Perfil Lipídico Completo"]
    resp_lab = client.post("/lab-results/orders/new", data={
        "patient_id": test_patient.id,
        "consultation_id": c_id,
        "clinical_indication": "Control metabólico y cefalea",
        "tests": tests_selected,
        "other_tests": "Vitamina D (25-OH)",
        "notes": "Ayuno estricto de 10 a 12 horas previas a la toma de muestra"
    }, follow_redirects=False)

    loc_path = resp_lab.headers.get("location", "").split("?")[0]
    lab_id = int(loc_path.rstrip("/").split("/")[-1])
    lab_order = db.query(LabOrder).filter(LabOrder.id == lab_id).first()
    assert lab_order is not None
    assert "Hemograma Completo" in lab_order.tests_requested
    assert "Vitamina D" in lab_order.tests_requested
    print(f"  ✓ Orden de laboratorio #{lab_id} creada con 4 análisis seleccionados")

    # Descargar PDF de la orden de laboratorio
    resp_pdf = client.get(f"/lab-results/orders/{lab_id}/pdf")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers.get("content-type") == "application/pdf"
    assert len(resp_pdf.content) > 1000
    print(f"  ✓ PDF de orden de laboratorio generado ({len(resp_pdf.content)} bytes)")

    # ==========================================
    # TEST 4: FASE 4 — ROL DE ESTACIÓN & CONFIGURACIÓN DE RED
    # ==========================================
    print("\n[TEST 4] Verificando Fase 4: Rol de Estación y Configuración...")
    resp_set = client.post("/settings/", data={
        "clinic_name": "Centro Médico Especializado SSCP",
        "doctor_name": "Dra. Especialista v1.2",
        "specialty": "Medicina Interna",
        "phone": "809-555-0100",
        "email": "consultorio@sscp.local",
        "address": "Calle Médica #12",
        "currency": "RD$",
        "sede_name": "Consultorio Central",
        "tailscale_ip": "100.90.80.70",
        "station_role": "doctor_principal",
        "central_station_url": "http://192.168.1.100:8080"
    }, follow_redirects=False)

    assert resp_set.status_code in [200, 303]
    setting = db.query(Setting).first()
    assert setting.station_role == "doctor_principal"
    assert setting.central_station_url == "http://192.168.1.100:8080"
    print(f"  ✓ Estación configurada como: {setting.station_role}, URL Par: {setting.central_station_url}")

    # ==========================================
    # TEST 5: FASE 5 — MOTOR DE SINCRONIZACIÓN P2P (Tailscale / LAN)
    # ==========================================
    print("\n[TEST 5] Verificando Fase 5: Motor de Sincronización P2P...")
    
    # 5.1 Estado de estación
    resp_status = client.get("/sync/peer/status")
    assert resp_status.status_code == 200
    st_data = resp_status.json()
    assert st_data["status"] == "online"
    assert st_data["version"] == "1.2.0"
    assert st_data["station_role"] == "doctor_principal"
    print("  ✓ Endpoint GET /sync/peer/status responde en línea con metadatos de estación")

    # 5.2 Exportación de delta
    resp_delta = client.get("/sync/peer/delta")
    assert resp_delta.status_code == 200
    delta_pkg = resp_delta.json()
    assert "data" in delta_pkg
    assert len(delta_pkg["data"]["patients"]) > 0
    assert len(delta_pkg["data"]["consultations"]) > 0
    assert len(delta_pkg["data"]["lab_orders"]) > 0
    print(f"  ✓ Endpoint GET /sync/peer/delta exporta {delta_pkg['counts']['patients']} pacientes, {delta_pkg['counts']['consultations']} consultas y {delta_pkg['counts']['lab_orders']} órdenes")

    # 5.3 Importación de delta simulando envío desde estación de secretaría
    existing_mp = db.query(Patient).filter(Patient.document_id == "402-1122334-9").first()
    if existing_mp:
        db.query(Payment).filter(Payment.patient_id == existing_mp.id).delete()
        db.query(Appointment).filter(Appointment.patient_id == existing_mp.id).delete()
        db.delete(existing_mp)
        db.commit()

    simulated_secretaria_payload = {
        "version": "1.2.0",
        "station_role": "secretaria",
        "clinic_name": "Recepción Externa",
        "exported_at": datetime.utcnow().isoformat(),
        "data": {
            "patients": [
                {
                    "first_name": "Marcos",
                    "last_name": "Paredes",
                    "document_id": "402-1122334-9",
                    "phone": "809-555-7788",
                    "date_of_birth": "1985-04-20",
                    "gender": "M",
                    "blood_type": "A+"
                }
            ],
            "appointments": [
                {
                    "patient_document_id": "402-1122334-9",
                    "date": date.today().isoformat(),
                    "start_time": "10:30:00",
                    "reason": "Chequeo preventivo registrado por secretaría",
                    "status": "Pendiente",
                    "queue_number": 4,
                    "price": 1500.0,
                    "sede_origen": "secretaria"
                }
            ],
            "payments": [
                {
                    "patient_document_id": "402-1122334-9",
                    "service_name": "Consulta Preventiva",
                    "amount": 1500.0,
                    "discount": 0.0,
                    "total": 1500.0,
                    "payment_method": "Tarjeta",
                    "receipt_number": "REC-SEC-0042",
                    "status": "Completado"
                }
            ]
        }
    }

    resp_import = client.post("/sync/peer/import", json=simulated_secretaria_payload)
    assert resp_import.status_code == 200
    imp_data = resp_import.json()
    assert imp_data["success"] == True
    assert imp_data["counts"]["patients"] >= 1
    assert imp_data["counts"]["appointments"] >= 1
    assert imp_data["counts"]["payments"] >= 1
    print(f"  ✓ Endpoint POST /sync/peer/import procesó delta P2P con éxito: {imp_data['message']}")

    # ==========================================
    # TEST 6: FASE 6 — INDICADORES VISUALES EN PLANTILLAS
    # ==========================================
    print("\n[TEST 6] Verificando Fase 6: Renderizado de Indicadores Visuales UI...")
    resp_dash = client.get("/dashboard")
    assert resp_dash.status_code == 200
    html_dash = resp_dash.text
    assert "Estación Doctor" in html_dash or "Estación Consultorio" in html_dash or "Estación:" in html_dash
    assert "P2P" in html_dash or "Sync" in html_dash
    print("  ✓ Sidebar y Header renderizan el badge de estación e indicador P2P")

    resp_sync_view = client.get("/sync")
    assert resp_sync_view.status_code == 200
    html_sync = resp_sync_view.text
    assert "Sincronización Directa de Estaciones" in html_sync or "Sincronización Directa" in html_sync
    assert "testPeerConnection" in html_sync
    print("  ✓ Centro de Sincronización renderiza tarjeta dedicada de estación par P2P")

    # ==========================================
    # TEST 7: AUDITORÍA DEL SISTEMA (CLINICAL AUDIT & INTEGRITY)
    # ==========================================
    print("\n[TEST 7] Verificando Sistema de Auditoría Médica e Integridad...")
    audit_logs = AuditService.get_logs_for_patient(db, test_patient.id)
    assert len(audit_logs) >= 2, f"Se esperaban al menos 2 registros de auditoría para el paciente, se encontraron {len(audit_logs)}"
    print(f"  ✓ {len(audit_logs)} registros inmutables de auditoría encontrados para el paciente {test_patient.first_name}:")
    for log in audit_logs[:3]:
        print(f"     - [{log.created_at.strftime('%H:%M:%S')}] {log.action.upper()}: {log.summary}")

    # Renderizar vista de paciente para verificar tab de auditoría
    resp_pat_view = client.get(f"/patients/{test_patient.id}")
    assert resp_pat_view.status_code == 200
    assert "Bitácora de Auditoría" in resp_pat_view.text
    print("  ✓ Vista de paciente muestra la bitácora de auditoría legal con diffs")

    print("\n" + "=" * 80)
    print("🎉 TODAS LAS PRUEBAS DE LA SUITE MAESTRA v1.2.0 PASARON SATISFACTORIAMENTE (100%)")
    print("=" * 80)

if __name__ == "__main__":
    run_full_master_suite()
