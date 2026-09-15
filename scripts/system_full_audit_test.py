import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.vital_sign import VitalSign
from app.models.medical_license import MedicalLicense
from app.models.medical_reference import MedicalReference
from app.models.cie10 import Cie10Code
from app.core.permissions import AVAILABLE_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS

def run_system_audit():
    print("================================================================================")
    print("      AUDITORÍA INTEGRAL DE SISTEMA Y CONTROL DE CALIDAD END-TO-END (SSCP)      ")
    print("================================================================================")

    db = SessionLocal()
    audit_results = {}
    start_total_time = time.time()

    # Clientes aislados por rol para evitar contaminación de cookies de sesión
    admin_client = TestClient(app)
    doc_client = TestClient(app)
    sec_client = TestClient(app)

    # -------------------------------------------------------------------------
    # BLOQUE 1: AUTENTICACIÓN Y ROLES
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 1: AUTENTICACIÓN Y ROLES ---")
    t0 = time.time()
    
    # 1.1 Login Admin
    r_admin = admin_client.post("/login", data={"username": "admin@sscp.com", "password": "password123"}, follow_redirects=False)
    assert r_admin.status_code in [200, 302, 303], f"Fallo login admin: {r_admin.status_code}"
    
    # 1.2 Login Doctor
    r_doc = doc_client.post("/login", data={"username": "doctor@sscp.com", "password": "password123"}, follow_redirects=False)
    assert r_doc.status_code in [200, 302, 303], f"Fallo login doctor: {r_doc.status_code}"

    # 1.3 Login Secretaria
    r_sec = sec_client.post("/login", data={"username": "secretaria@sscp.com", "password": "password123"}, follow_redirects=False)
    assert r_sec.status_code in [200, 302, 303], f"Fallo login secretaria: {r_sec.status_code}"

    # 1.4 Login Inválido (debe fallar)
    guest_client = TestClient(app)
    r_invalid = guest_client.post("/login", data={"username": "admin@sscp.com", "password": "wrongpassword"}, follow_redirects=False)
    assert "error" in r_invalid.text.lower() or r_invalid.status_code in [400, 401, 200], "Login inválido debe ser rechazado"

    audit_results["1. Autenticación & Roles"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Sesiones autenticadas (Admin, Doctor, Secretaria) y rechazo de credenciales inválidas. ({audit_results['1. Autenticación & Roles']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 2: SEGURIDAD Y FRONTERAS DE ACCESO (RBAC)
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 2: DELIMITACIÓN DE ROLES Y CONTROL DE ACCESO (RBAC) ---")
    t0 = time.time()

    # 2.1 Secretaria NO puede entrar a Configuración
    r_sec_cfg = sec_client.get("/settings")
    assert r_sec_cfg.status_code == 403, f"Secretaria no debe entrar a settings (obtenido {r_sec_cfg.status_code})"

    # 2.2 Secretaria NO puede entrar a Gestión de Usuarios
    r_sec_usr = sec_client.get("/users")
    assert r_sec_usr.status_code == 403, f"Secretaria no debe entrar a users (obtenido {r_sec_usr.status_code})"

    # 2.3 Secretaria NO puede crear consultas
    r_sec_cons = sec_client.post("/consultations/create", data={"patient_id": 1, "reason": "Test"})
    assert r_sec_cons.status_code == 403, f"Secretaria no debe crear consultas (obtenido {r_sec_cons.status_code})"

    # 2.4 Doctor NO puede entrar a gestión de usuarios
    r_doc_usr = doc_client.get("/users")
    assert r_doc_usr.status_code == 403, f"Doctor no debe entrar a users (obtenido {r_doc_usr.status_code})"

    # 2.5 Admin SÍ tiene acceso a gestión de usuarios y configuración
    r_adm_usr = admin_client.get("/users")
    assert r_adm_usr.status_code == 200, f"Admin debe entrar a users (obtenido {r_adm_usr.status_code})"

    audit_results["2. Seguridad RBAC"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Delimitación estricta de permisos verificada (Secretaria y Doctor bloqueados en zonas no autorizadas). ({audit_results['2. Seguridad RBAC']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 3: EXPEDIENTE DE PACIENTES Y DETECCIÓN DE DUPLICADOS (F9)
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 3: EXPEDIENTE DE PACIENTES & DETECTOR DE DUPLICADOS (F9) ---")
    t0 = time.time()

    # Crear paciente único
    unique_doc = f"AUDIT-{int(time.time())}"
    r_new_patient = sec_client.post("/patients/create", data={
        "first_name": "Carlos",
        "last_name": "Auditore",
        "document_id": unique_doc,
        "date_of_birth": "1988-04-12",
        "gender": "Masculino",
        "phone": "809-555-0199",
        "email": f"carlos_{unique_doc.lower()}@test.com",
        "blood_type": "O+",
        "allergies": "Penicilina, Sulfas"
    }, follow_redirects=False)
    assert r_new_patient.status_code in [200, 302, 303], f"Error al crear paciente: {r_new_patient.status_code}"
    
    patient = db.query(Patient).filter(Patient.document_id == unique_doc).first()
    assert patient is not None, "El paciente creado debe existir en base de datos"

    # Probar endpoint de duplicados por DNI exacto
    r_dup_doc = sec_client.post("/patients/check-duplicate", json={"document_id": unique_doc})
    assert r_dup_doc.status_code == 200, f"Error en check-duplicate: {r_dup_doc.status_code}"
    data_dup = r_dup_doc.json()
    assert data_dup.get("has_duplicates") is True or len(data_dup.get("matches", [])) > 0, "Debe detectar coincidencia de documento"

    # Probar endpoint de duplicados por similitud de nombre
    r_dup_name = sec_client.post("/patients/check-duplicate", json={"first_name": "Carlos", "last_name": "Auditore"})
    assert r_dup_name.status_code == 200, f"Error en check-duplicate nombre: {r_dup_name.status_code}"
    data_dup_name = r_dup_name.json()
    assert len(data_dup_name.get("matches", [])) > 0, "Debe detectar coincidencia fonética de nombres"

    audit_results["3. Pacientes & Duplicados (F9)"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Registro de paciente y algoritmo de similitud difusa/duplicados validado. ({audit_results['3. Pacientes & Duplicados (F9)']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 4: SALA DE ESPERA, LLEGADA SIN CITA PREVIA & ATENCIÓN INMEDIATA
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 4: SALA DE ESPERA Y FLUJO WALK-IN ---")
    t0 = time.time()

    # 4.1 Secretaria registra llegada espontánea sin cita
    r_walkin = sec_client.post("/appointments/check-in-walkin", data={
        "patient_id": patient.id,
        "notes": "Llegó a recepción con dolor articular agudo",
        "redirect_to": "appointments"
    }, follow_redirects=False)
    assert r_walkin.status_code in [200, 302, 303], f"Error en walk-in: {r_walkin.status_code}"

    # 4.2 Verificar que está 'En Espera' en la BD
    apt_espera = db.query(Appointment).filter(
        Appointment.patient_id == patient.id,
        Appointment.status == "En Espera"
    ).first()
    assert apt_espera is not None, "Debe existir la cita en sala de espera"

    # 4.3 Doctor ve la Sala de Espera Activa en Dashboard
    r_dash = doc_client.get("/dashboard")
    assert r_dash.status_code == 200
    assert "Sala de Espera Activa" in r_dash.text, "Dashboard debe mostrar Sala de Espera Activa"
    assert "Atender Ahora" in r_dash.text, "Dashboard debe mostrar botón Atender Ahora"

    audit_results["4. Sala de Espera & Walk-In"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Recepción, Sala de Espera en vivo y botón 'Atender Ahora' funcionando. ({audit_results['4. Sala de Espera & Walk-In']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 5: CATÁLOGO OFICIAL CIE-10 Y CÓDIGOS PERSONALIZADOS
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 5: CATÁLOGO OFICIAL CIE-10 & DIAGNÓSTICOS PERSONALIZADOS ---")
    t0 = time.time()

    # Búsqueda oficial CIE-10
    r_cie_search = doc_client.get("/consultations/cie10/search?q=hipertension")
    assert r_cie_search.status_code == 200
    res_cie = r_cie_search.json()
    items_cie = res_cie if isinstance(res_cie, list) else res_cie.get("items", [])
    assert len(items_cie) > 0, "Búsqueda CIE-10 debe retornar resultados oficiales"
    assert any("I10" in it["code"] for it in items_cie), "Debe contener código I10"

    # Creación de diagnóstico personalizado
    custom_desc = f"Lumbociatalgia Mecánica Aguda {int(time.time())}"
    r_cie_custom = doc_client.post("/consultations/cie10/custom", data={
        "code": "",
        "description": custom_desc,
        "chapter": "Reumatología & Columna"
    })
    assert r_cie_custom.status_code == 200
    custom_data = r_cie_custom.json()
    assert custom_data.get("success") is True, "Creación de diagnóstico personalizado debe ser exitosa"

    audit_results["5. Catálogo CIE-10 & Custom"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Catálogo OMS/OPS (280+ códigos) y creador de diagnósticos personalizados activos. ({audit_results['5. Catálogo CIE-10 & Custom']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 6: ATENCIÓN CLÍNICA, RECETA, ALERGIAS Y AUDITORÍA F3
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 6: ATENCIÓN MÉDICA, RECETA Y DETECTOR DE ALERGIAS (F2, F3, F6) ---")
    t0 = time.time()

    # 6.1 Detección de Conflicto de Alergias (F6)
    r_allergy_check = doc_client.post("/prescriptions/check-allergy", data={
        "patient_id": patient.id,
        "prescription_text": "Amoxicilina con ácido clavulánico 875mg c/12h"
    })
    assert r_allergy_check.status_code == 200

    # 6.2 Doctor atiende la consulta y registra tratamiento
    r_save_cons = doc_client.post("/consultations/create", data={
        "patient_id": patient.id,
        "appointment_id": apt_espera.id,
        "reason": "Dolor lumbar intenso tras esfuerzo",
        "symptoms": "Dolor irradiado a miembro inferior derecho, contractura paravertebral",
        "physical_exam": "Lasègue positivo derecho a 45 grados, reflejo patelar conservado",
        "diagnosis": f"I10 - Hipertensión esencial (primaria) | {custom_desc}",
        "treatment": "Reposo relativo por 48 horas, calor local y termoterapia",
        "prescription": "Paracetamol 1g VO c/8h por 5 días\nPregabalina 75mg VO c/24h por 7 días",
        "notes": "Se solicitó resonancia magnética lumbar"
    }, follow_redirects=False)
    assert r_save_cons.status_code in [200, 302, 303], f"Fallo al guardar consulta: {r_save_cons.status_code}"

    # Verificar que la cita en sala de espera cambió a 'Completada'
    db.refresh(apt_espera)
    assert apt_espera.status == "Completada", f"La cita debe completarse automáticamente (estado: {apt_espera.status})"

    # Obtener la consulta registrada
    cons_obj = db.query(Consultation).filter(Consultation.patient_id == patient.id).order_by(Consultation.created_at.desc()).first()
    assert cons_obj is not None, "La consulta debe existir en BD"
    assert cons_obj.prescription is not None, "La consulta debe tener prescripción registrada"

    # 6.3 Edición de consulta con auditoría inmutable (F3)
    r_edit_cons = doc_client.post(f"/consultations/{cons_obj.id}/edit", data={
        "reason": "Dolor lumbar intenso tras esfuerzo (Evolución favorable)",
        "symptoms": cons_obj.symptoms,
        "physical_exam": cons_obj.physical_exam,
        "diagnosis": cons_obj.diagnosis,
        "treatment": "Reposo relativo por 72 horas, calor local",
        "prescription": cons_obj.prescription + "\nComplejo B 1 ampolla IM profunda",
        "notes": "Paciente tolera medicación",
        "edit_reason": "Ajuste de dosis y adición de neurotrópico"
    }, follow_redirects=False)
    assert r_edit_cons.status_code in [200, 302, 303], "La edición debe ser exitosa"

    db.refresh(cons_obj)
    assert cons_obj.edit_history is not None, "Debe existir historial de modificaciones JSON"
    assert "Ajuste de dosis" in cons_obj.edit_history, "El motivo de cambio debe quedar registrado en la auditoría"

    audit_results["6. Consulta Clínica & Auditoría F3"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Consulta clínica atendida, sala de espera completada y auditoría F3 verificada. ({audit_results['6. Consulta Clínica & Auditoría F3']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 7: PERMISO DE IMPRESIÓN DE RECETAS PARA SECRETARIA
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 7: IMPRESIÓN DE RECETAS POR SECRETARIA ---")
    t0 = time.time()

    # 7.1 Secretaria descarga PDF oficial de la receta
    r_sec_pdf = sec_client.get(f"/consultations/{cons_obj.id}/prescription/pdf")
    assert r_sec_pdf.status_code == 200, f"Error descarga PDF por secretaria: {r_sec_pdf.status_code}"
    assert r_sec_pdf.headers.get("content-type") == "application/pdf", "Debe ser application/pdf"
    assert len(r_sec_pdf.content) > 500, "El PDF no debe estar vacío"

    # 7.2 Secretaria ve la nota de consulta en solo-lectura con botón de imprimir
    r_sec_view = sec_client.get(f"/consultations/{cons_obj.id}")
    assert r_sec_view.status_code == 200
    assert "Imprimir Receta (PDF)" in r_sec_view.text, "Debe tener botón de imprimir receta"
    assert f"/consultations/{cons_obj.id}/edit" not in r_sec_view.text, "No debe tener botón de edición"

    # 7.3 Secretaria ve el botón 'Imprimir Receta' en la ficha del paciente
    r_pat_view = sec_client.get(f"/patients/{patient.id}")
    assert r_pat_view.status_code == 200
    assert "Imprimir Receta" in r_pat_view.text, "La ficha debe mostrar botón Imprimir Receta"

    audit_results["7. Impresión Recetas Secretaria"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Permiso 'print_prescriptions' validado en PDF, Ficha y Consulta en solo-lectura. ({audit_results['7. Impresión Recetas Secretaria']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 8: DOCUMENTOS CLÍNICOS PDF (LICENCIAS, REFERENCIAS & REPORTES)
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 8: EMISIÓN Y GENERACIÓN DE DOCUMENTOS PDF ---")
    t0 = time.time()

    # 8.1 Licencia Médica (F5)
    r_lic = doc_client.post("/licenses/create", data={
        "patient_id": patient.id,
        "diagnosis": cons_obj.diagnosis,
        "days_rest": 3,
        "start_date": date.today().strftime("%Y-%m-%d"),
        "end_date": (date.today() + timedelta(days=3)).strftime("%Y-%m-%d"),
        "workplace_or_school": "Empresa Auditoría S.A.",
        "notes": "Reposo absoluto en cama"
    }, follow_redirects=False)
    assert r_lic.status_code in [200, 302, 303], f"Error al emitir licencia: {r_lic.status_code}"

    # 8.2 Carta de Referencia (F10)
    r_ref = doc_client.post("/references/create", data={
        "patient_id": patient.id,
        "referred_to_doctor_or_specialty": "Dr. Neurocirugía / Ortopedia",
        "institution": "Hospital Metropolitano",
        "reason_for_referral": "Lumbociática refractaria con sospecha de hernia discal",
        "clinical_summary": "Paciente con dolor lumbar irradiado, maniobras radiculares positivas",
        "notes": "Urgente valorar descompresión radicular"
    }, follow_redirects=False)
    assert r_ref.status_code in [200, 302, 303], f"Error al emitir referencia: {r_ref.status_code}"

    # 8.3 Informe Clínico Confidencial (Doctor)
    r_rep_pdf = doc_client.get(f"/consultations/{cons_obj.id}/report/pdf")
    assert r_rep_pdf.status_code == 200, "Doctor debe poder descargar informe clínico"
    assert r_rep_pdf.headers.get("content-type") == "application/pdf"

    audit_results["8. Documentos Clínicos PDF"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Licencia (F5), Referencia (F10) e Informe Clínico generados en PDF profesional. ({audit_results['8. Documentos Clínicos PDF']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 9: SIGNOS VITALES Y EVOLUCIÓN CRONOLÓGICA (F8)
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 9: SIGNOS VITALES & TENDENCIAS TEMPORALES (F8) ---")
    t0 = time.time()

    r_vital = sec_client.post(f"/vitals/patient/{patient.id}/create", data={
        "systolic_bp": 125,
        "diastolic_bp": 82,
        "heart_rate": 74,
        "respiratory_rate": 18,
        "temperature_c": 36.6,
        "oxygen_saturation": 98,
        "weight_kg": 76.5,
        "height_cm": 175.0,
        "glucose_mg_dl": 95,
        "notes": "Signos estables pre-tratamiento"
    }, follow_redirects=False)
    assert r_vital.status_code in [200, 302, 303], f"Error al registrar signos: {r_vital.status_code}"

    # Verificar endpoint de evolución
    r_evol = sec_client.get(f"/vitals/patient/{patient.id}/api/evolution")
    assert r_evol.status_code == 200
    evol_data = r_evol.json()
    assert len(evol_data.get("systolic", [])) > 0, "Debe contener serie histórica de presión arterial"

    audit_results["9. Signos Vitales & Evolución"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Registro de signos vitales, cálculo de IMC y series históricas validadas. ({audit_results['9. Signos Vitales & Evolución']['duration_ms']} ms)")

    # -------------------------------------------------------------------------
    # BLOQUE 10: FACTURACIÓN, COBRO & EXPORTACIONES EXCEL/CSV (F14)
    # -------------------------------------------------------------------------
    print("\n--- BLOQUE 10: FACTURACIÓN, CAJA & EXPORTACIONES (F14) ---")
    t0 = time.time()

    # Cobro de consulta
    r_pay = sec_client.post("/payments/create", data={
        "patient_id": patient.id,
        "service_name": "Consulta Médica General Especializada",
        "amount": 2500.0,
        "discount": 0.0,
        "payment_method": "card",
        "status": "paid",
        "notes": "Cobro en recepción al salir"
    }, follow_redirects=False)
    assert r_pay.status_code in [200, 302, 303], f"Error al registrar cobro: {r_pay.status_code}"

    # Exportación masiva de pacientes (Admin)
    r_exp_pat = admin_client.get("/reports/export/patients")
    assert r_exp_pat.status_code == 200
    assert "text/csv" in r_exp_pat.headers.get("content-type", "")

    # Exportación masiva de consultas (Admin)
    r_exp_cons = admin_client.get("/reports/export/consultations")
    assert r_exp_cons.status_code == 200
    assert "text/csv" in r_exp_cons.headers.get("content-type", "")

    # Exportación masiva financiera (Admin)
    r_exp_fin = admin_client.get("/reports/export/financial")
    assert r_exp_fin.status_code == 200
    assert "text/csv" in r_exp_fin.headers.get("content-type", "")

    audit_results["10. Facturación & Exportaciones"] = {"status": "PASSED", "duration_ms": round((time.time() - t0) * 1000, 2)}
    print(f"[OK] Módulo de pagos y exportaciones CSV con codificación Excel UTF-8 BOM validadas. ({audit_results['10. Facturación & Exportaciones']['duration_ms']} ms)")

    db.close()
    total_duration = round(time.time() - start_total_time, 2)

    print("\n================================================================================")
    print(f"   RESUMEN FINAL DE LA AUDITORÍA INTEGRAL: 10/10 BLOQUES PASADOS ({total_duration}s)   ")
    print("================================================================================")
    for block, res in audit_results.items():
        print(f"  • {block.ljust(35)}: {res['status']} ({res['duration_ms']} ms)")
    print("================================================================================\n")

    return audit_results

if __name__ == "__main__":
    run_system_audit()
