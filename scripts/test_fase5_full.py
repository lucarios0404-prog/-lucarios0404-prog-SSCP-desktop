import sys
import os
from pathlib import Path
import uuid
from datetime import datetime, date, timedelta

# Asegurar UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Añadir raíz de sscp-desktop al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.vital_sign import VitalSign
from app.models.audit_log import ClinicalAuditLog
from app.services.patient_service import PatientService
from app.services.audit_service import AuditService
from app.core.deps import require_current_user
from app.models.user import User

def run_fase5_tests():
    print("=" * 60)
    print("INICIANDO VERIFICACIÓN COMPLETA - FASE 5: INTELIGENCIA CLÍNICA & REPORTES")
    print("=" * 60)

    db = SessionLocal()
    mock_user = User(id=1, email="admin@sscp.local", name="Dr. Administrador", role="admin", is_active=True)
    app.dependency_overrides[require_current_user] = lambda: mock_user
    client = TestClient(app)

    try:
        # 1. Test F9: Detector Inteligente de Pacientes Duplicados
        print("\n[1/4] Probando Detector Inteligente de Pacientes Duplicados (F9)...")
        uid = uuid.uuid4().hex[:6]
        orig_doc = f"402-DUP{uid}-1"
        orig_patient = Patient(
            first_name="Alejandro",
            last_name=f"Martínez {uid}",
            document_id=orig_doc,
            phone="809-555-8888",
            email=f"ale_{uid}@test.com"
        )
        db.add(orig_patient)
        db.commit()
        db.refresh(orig_patient)

        # Caso A: Mismo documento
        dup_by_doc = PatientService.find_potential_duplicates(
            db=db,
            first_name="Alex",
            last_name="M",
            document_id=orig_doc.replace("-", "") # Cédula sin guiones
        )
        assert len(dup_by_doc) > 0, "Debe detectar duplicado por cédula idéntica"
        assert dup_by_doc[0]["score"] == 100
        print(f"  OK: Duplicado por Cédula detectado (Score: {dup_by_doc[0]['score']}%)")

        # Caso B: Nombre con ligera variación tipográfica ("Alejandro Martinez" vs "Alejandro Martines")
        dup_by_name = PatientService.find_potential_duplicates(
            db=db,
            first_name="Alejandro",
            last_name=f"Martines {uid}",
            threshold=0.75
        )
        assert len(dup_by_name) > 0, "Debe detectar duplicado por similitud fonética/textual"
        assert dup_by_name[0]["score"] >= 80
        print(f"  OK: Duplicado por Similitud de Nombre detectado (Score: {dup_by_name[0]['score']}%)")

        # Caso C: Persona completamente distinta
        no_dup = PatientService.find_potential_duplicates(
            db=db,
            first_name="Verónica",
            last_name="Valdez Zorrilla",
            document_id="001-9999999-9"
        )
        # No debe coincidir con Alejandro
        matched_ids = [m["id"] for m in no_dup]
        assert orig_patient.id not in matched_ids, "No debe marcar falsos positivos para nombres distintos"
        print("  OK: Sin falsos positivos para pacientes distintos.")

        # 2. Test F8: Gráficos y Series de Evolución de Signos Vitales
        print("\n[2/4] Probando Gráficos y Evolución de Signos Vitales (F8)...")
        # Crear 3 mediciones sucesivas de signos vitales para evaluar tendencias
        now = datetime.now()
        v1 = VitalSign(
            patient_id=orig_patient.id,
            systolic_bp=140,
            diastolic_bp=90,
            glucose_mg_dl=135.0,
            weight_kg=85.0,
            bmi=28.5,
            heart_rate=88,
            oxygen_saturation=98.0,
            recorded_at=now - timedelta(days=30)
        )
        v2 = VitalSign(
            patient_id=orig_patient.id,
            systolic_bp=130,
            diastolic_bp=85,
            glucose_mg_dl=115.0,
            weight_kg=83.0,
            bmi=27.8,
            heart_rate=80,
            oxygen_saturation=99.0,
            recorded_at=now - timedelta(days=15)
        )
        v3 = VitalSign(
            patient_id=orig_patient.id,
            systolic_bp=120,
            diastolic_bp=80,
            glucose_mg_dl=98.0,
            weight_kg=80.5,
            bmi=27.0,
            heart_rate=72,
            oxygen_saturation=99.0,
            recorded_at=now
        )
        db.add_all([v1, v2, v3])
        db.commit()

        # Consultar API de evolución
        evo_resp = client.get(f"/vitals/patient/{orig_patient.id}/api/evolution")
        assert evo_resp.status_code == 200, f"Fallo endpoint evolución: {evo_resp.status_code}"
        evo_data = evo_resp.json()
        assert len(evo_data["systolic"]) >= 3, "Debe contener al menos 3 mediciones de tensión sistólica"
        assert len(evo_data["glucose"]) >= 3, "Debe contener al menos 3 mediciones de glucemia"
        print(f"  OK: Series cronológicas generadas: {len(evo_data['dates'])} puntos de control")
        print(f"      - Sistólica: {evo_data['systolic']}")
        print(f"      - Diastólica: {evo_data['diastolic']}")
        print(f"      - Glucosa: {evo_data['glucose']}")

        # 3. Test F13: Bitácora de Auditoría y Trazabilidad Médica
        print("\n[3/4] Probando Trazabilidad y Auditoría Médica (F13)...")
        # Crear consulta médica
        c_test = Consultation(
            patient_id=orig_patient.id,
            doctor_id=1,
            reason=f"Evaluación de Hipertensión {uid}",
            diagnosis="I10 Hipertensión arterial primaria",
            treatment="Enalapril 10mg diario",
            sede_origen="local"
        )
        db.add(c_test)
        db.commit()
        db.refresh(c_test)

        # Registrar auditoría de creación
        audit_create = AuditService.log_change(
            db=db,
            entity_type="consultation",
            entity_id=c_test.id,
            action="create",
            summary=f"Consulta #{c_test.id} creada por evaluación",
            patient_id=orig_patient.id,
            user_id=1,
            new_data={"reason": c_test.reason, "diagnosis": c_test.diagnosis}
        )
        assert audit_create.id is not None
        print(f"  OK: Registro de auditoría por creación # {audit_create.id} generado")

        # Simular edición y registrar auditoría de modificación
        audit_update = AuditService.log_change(
            db=db,
            entity_type="consultation",
            entity_id=c_test.id,
            action="update",
            summary="Ajuste de dosis antihipertensiva",
            patient_id=orig_patient.id,
            user_id=1,
            old_data={"treatment": "Enalapril 10mg diario"},
            new_data={"treatment": "Enalapril 20mg diario + Amlodipina 5mg"}
        )
        assert audit_update.id is not None
        assert "Amlodipina" in audit_update.changes_json
        print(f"  OK: Registro de auditoría por edición #{audit_update.id} con diferencias JSON guardado")

        logs = AuditService.get_logs_for_patient(db, orig_patient.id)
        assert len(logs) >= 2, "Deben existir al menos 2 registros de auditoría para el paciente"
        print(f"  OK: Historial de auditoría recuperado con {len(logs)} eventos inmutables.")

        # 4. Test F14: Reportes Estadísticos y Exportación Excel / CSV
        print("\n[4/4] Probando Reportes Estadísticos y Exportación Excel / CSV (F14)...")
        # Dashboard de reportes
        r_dash = client.get("/reports")
        assert r_dash.status_code == 200, f"Error en /reports: {r_dash.status_code}"
        assert "Inteligencia Clínica" in r_dash.text or "Estadísticas" in r_dash.text
        print("  OK: Dashboard de Inteligencia Clínica renderizado (HTTP 200)")

        # Exportación de Pacientes CSV
        r_exp_p = client.get("/reports/export/patients")
        assert r_exp_p.status_code == 200
        assert "text/csv" in r_exp_p.headers.get("content-type", "")
        csv_text_p = r_exp_p.content.decode("utf-8-sig")
        assert "Cédula / Documento" in csv_text_p
        assert orig_patient.first_name in csv_text_p
        print("  OK: Exportación de Pacientes a CSV generada con BOM UTF-8 para Excel.")

        # Exportación de Consultas CSV
        r_exp_c = client.get("/reports/export/consultations")
        assert r_exp_c.status_code == 200
        assert "text/csv" in r_exp_c.headers.get("content-type", "")
        csv_text_c = r_exp_c.content.decode("utf-8-sig")
        assert "Motivo de Consulta" in csv_text_c
        print("  OK: Exportación de Consultas e Historias a CSV generada con éxito.")

        # Exportación Financiera CSV
        r_exp_f = client.get("/reports/export/financial")
        assert r_exp_f.status_code == 200
        assert "text/csv" in r_exp_f.headers.get("content-type", "")
        print("  OK: Exportación de Facturación a CSV generada con éxito.")

        print("\n" + "=" * 60)
        print("RESULTADO FASE 5: TODOS LOS TESTS PASARON EXITOSAMENTE (100% OK)")
        print("=" * 60)

    finally:
        app.dependency_overrides.clear()
        db.close()

if __name__ == "__main__":
    run_fase5_tests()
