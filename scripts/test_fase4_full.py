import sys
import os
from pathlib import Path
import uuid

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
from app.models.template import ClinicalTemplate
from app.models.medical_license import MedicalLicense
from app.models.medical_reference import MedicalReference
from app.routers.quick_prescriptions import check_allergy_conflict
from app.services.qr_service import generate_patient_qr_base64
from app.services.pdf_service import (
    generate_quick_prescription_pdf,
    generate_medical_license_pdf,
    generate_medical_reference_pdf
)

def run_fase4_tests():
    print("=" * 60)
    print("INICIANDO VERIFICACIÓN COMPLETA - FASE 4: PRODUCTIVIDAD DEL DOCTOR")
    print("=" * 60)

    db = SessionLocal()
    client = TestClient(app)

    try:
        # 1. Test Detección de Conflicto de Alergias (F6)
        print("\n[1/6] Probando algoritmo de detección de alergias (F6)...")
        allergies = "Penicilina, Ibuprofeno, Sulfa"
        presc_conflict = "Administrar Amoxicilina 500mg cada 8 horas por 7 días y tomar Ibuprofeno si hay dolor."
        presc_safe = "Administrar Paracetamol 500mg y Azitromicina 500mg."

        conflicts = check_allergy_conflict(allergies, presc_conflict)
        assert len(conflicts) > 0, f"Debe detectar conflicto, detectado: {conflicts}"
        print(f"  OK: Conflictos detectados correctamente: {conflicts}")

        no_conflicts = check_allergy_conflict(allergies, presc_safe)
        assert len(no_conflicts) == 0, f"No debe haber conflictos, detectado: {no_conflicts}"
        print("  OK: Sin falsos positivos para fármacos seguros.")

        # 2. Test Paciente con Alergias y Código QR (F17)
        print("\n[2/6] Probando creación de paciente con alergias y código QR (F17)...")
        uid = uuid.uuid4().hex[:6]
        test_patient = Patient(
            first_name="Carmen",
            last_name=f"González {uid}",
            document_id=f"402-{uid}-1",
            phone="809-555-1234",
            email=f"carmen_{uid}@test.com",
            allergies="Penicilina, Ácido Acetilsalicílico",
            blood_type="O+"
        )
        db.add(test_patient)
        db.commit()
        db.refresh(test_patient)

        qr_base64 = generate_patient_qr_base64(test_patient)
        assert qr_base64.startswith("data:image/png;base64,"), "El QR debe ser un Data URI Base64 válido"
        print(f"  OK: Paciente #{test_patient.id} creado con alergias: '{test_patient.allergies}'")
        print(f"  OK: Código QR generado exitosamente (longitud base64: {len(qr_base64)} caracteres)")

        # 3. Test Receta Rápida (F2) & PDF
        print("\n[3/6] Probando generación de Receta Rápida en PDF (F2)...")
        rx_buffer = generate_quick_prescription_pdf(
            patient=test_patient,
            prescription_text="1. Claritromicina 500mg - 1 tab cada 12 hrs por 7 días.\n2. Paracetamol 500mg si hay fiebre.",
            diagnosis="Faringoamigdalitis aguda",
            doctor_name="Dr. Fernando Ruiz"
        )
        rx_bytes = rx_buffer.getvalue()
        assert len(rx_bytes) > 500, "El PDF de receta rápida debe tener contenido válido"
        print(f"  OK: PDF de Receta Rápida generado correctamente ({len(rx_bytes)} bytes)")

        # 4. Test Sistema de Plantillas Clínicas (F4)
        print("\n[4/6] Probando Sistema de Plantillas Clínicas (F4)...")
        tpl = ClinicalTemplate(
            title=f"Faringitis Aguda Estándar {uid}",
            category="prescription",
            content="1. Amoxicilina 500mg c/8h x 7d\n2. Ibuprofeno 400mg c/8h",
            is_global=True
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        fetched_tpl = db.query(ClinicalTemplate).filter(ClinicalTemplate.id == tpl.id).first()
        assert fetched_tpl is not None, "La plantilla debe persistir en base de datos"
        assert fetched_tpl.category == "prescription"
        print(f"  OK: Plantilla clínica persistida #{fetched_tpl.id} ('{fetched_tpl.title}')")

        # 5. Test Licencia Médica / Certificado de Reposo (F5) & PDF
        print("\n[5/6] Probando Licencia Médica (F5) & PDF...")
        from datetime import date, timedelta
        today = date.today()
        med_license = MedicalLicense(
            patient_id=test_patient.id,
            doctor_id=1,
            diagnosis="Gastroenteritis aguda con deshidratación leve",
            days_rest=3,
            start_date=today,
            end_date=today + timedelta(days=3),
            workplace_or_school="Empresas Asociadas S.A.",
            notes="Reposo absoluto en domicilio e hidratación oral."
        )
        db.add(med_license)
        db.commit()
        db.refresh(med_license)

        lic_buffer = generate_medical_license_pdf(
            license=med_license
        )
        lic_bytes = lic_buffer.getvalue()
        assert len(lic_bytes) > 500, "El PDF de licencia médica debe ser válido"
        print(f"  OK: Licencia médica #{med_license.id} creada con 3 días de reposo")
        print(f"  OK: PDF de Licencia Médica generado correctamente ({len(lic_bytes)} bytes)")

        # 6. Test Carta de Referencia Interconsulta (F10) & PDF
        print("\n[6/6] Probando Carta de Referencia Interconsulta (F10) & PDF...")
        med_ref = MedicalReference(
            patient_id=test_patient.id,
            doctor_id=1,
            referred_to_doctor_or_specialty="Dra. Patricia Méndez / Cardiología",
            institution="Instituto Dominicano de Cardiología",
            clinical_summary="Paciente refiere episodios de palpitaciones y disnea de medianos esfuerzos.",
            reason_for_referral="Evaluación por especialista, ecocardiograma y Holter 24h.",
            notes="Favor remitir contrarreferencia."
        )
        db.add(med_ref)
        db.commit()
        db.refresh(med_ref)

        ref_buffer = generate_medical_reference_pdf(
            reference=med_ref
        )
        ref_bytes = ref_buffer.getvalue()
        assert len(ref_bytes) > 500, "El PDF de carta de referencia debe ser válido"
        print(f"  OK: Carta de Referencia #{med_ref.id} a Cardiología creada")
        print(f"  OK: PDF de Carta de Referencia generado correctamente ({len(ref_bytes)} bytes)")

        print("\n" + "=" * 60)
        print("RESULTADO FASE 4: TODOS LOS TESTS PASARON EXITOSAMENTE (100% OK)")
        print("=" * 60)

    finally:
        db.close()

if __name__ == "__main__":
    run_fase4_tests()
