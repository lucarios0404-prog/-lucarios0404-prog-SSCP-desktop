import sys
from pathlib import Path

# Add root directory to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from main import ensure_schema_migrations
from app.database import SessionLocal, engine
from app.models.consultation import Consultation
from app.models.patient import Patient
from app.models.user import User
from app.models.setting import Setting
from app.services.pdf_service import generate_consultation_report_pdf

def test_unified_clinical_history():
    print(">>> 1. Probando ensure_schema_migrations()...")
    ensure_schema_migrations(engine)
    print("Migration OK.")

    db = SessionLocal()
    try:
        # Get or create test patient
        patient = db.query(Patient).first()
        if not patient:
            patient = Patient(first_name="Paciente", last_name="Prueba", document_id="001-0000000-1")
            db.add(patient)
            db.commit()
            db.refresh(patient)
        print(f"Paciente de prueba: #{patient.id} {patient.first_name} {patient.last_name}")

        # Get or create doctor
        doctor = db.query(User).first()
        doctor_id = doctor.id if doctor else 1

        print(">>> 2. Creando consulta con historia clínica unificada...")
        test_history_text = (
            "Paciente acude por cuadro de 3 días de evolución caracterizado por dolor abdominal tipo cólico en epigastrio.\n"
            "--- EXAMEN FÍSICO ---\n"
            "Abdomen blando, doloroso a la palpación profunda en epigastrio, sin signos de irritación peritoneal.\n"
            "--- DIAGNÓSTICO ---\n"
            "K29.7 - Gastritis aguda no especificada."
        )

        new_consult = Consultation(
            patient_id=patient.id,
            doctor_id=doctor_id,
            reason="Dolor abdominal persistente y epigastralgia",
            clinical_history=test_history_text,
            is_first_visit=True,
            edit_version=1,
            symptoms=test_history_text,
            diagnosis="K29.7 - Gastritis aguda no especificada",
            treatment="Dieta blanda, evitar irritantes y grasas por 14 días.",
            prescription="Omeprazol 20mg: 1 cápsula vía oral cada 24 horas en ayunas por 14 días."
        )
        db.add(new_consult)
        db.commit()
        db.refresh(new_consult)

        print(f"Consulta creada con ID #{new_consult.id}")
        assert new_consult.clinical_history == test_history_text
        assert new_consult.is_first_visit == True
        assert new_consult.edit_version == 1
        assert new_consult.display_clinical_history == test_history_text
        print("Verificación de creación y display_clinical_history: EXITOSA")

        print(">>> 3. Probando retrocompatibilidad con consulta legacy (sin clinical_history)...")
        legacy_consult = Consultation(
            patient_id=patient.id,
            doctor_id=doctor_id,
            reason="Chequeo rutinario",
            clinical_history=None,
            symptoms="Cefalea tensional ocasional",
            physical_exam="Presión arterial 120/80 mmHg, FC 72 lpm",
            diagnosis="G44.2 - Cefalea tensional",
            treatment="Manejo del estrés",
            is_first_visit=False,
            edit_version=1
        )
        db.add(legacy_consult)
        db.commit()
        db.refresh(legacy_consult)

        legacy_display = legacy_consult.display_clinical_history
        print("Display sintetizado de consulta legacy:\n", legacy_display)
        assert "Cefalea tensional ocasional" in legacy_display
        assert "Presión arterial 120/80 mmHg" in legacy_display
        assert "G44.2 - Cefalea tensional" in legacy_display
        print("Verificación de retrocompatibilidad legacy: EXITOSA")

        print(">>> 4. Probando edición y versionado...")
        new_consult.clinical_history += "\n\n--- EVOLUCIÓN ---\nPaciente tolera medicación adecuadamente."
        new_consult.edit_version = (new_consult.edit_version or 1) + 1
        db.commit()
        db.refresh(new_consult)
        assert new_consult.edit_version == 2
        assert "Paciente tolera medicación" in new_consult.display_clinical_history
        print(f"Consulta #{new_consult.id} versionada a v{new_consult.edit_version}: EXITOSA")

        print(">>> 5. Probando generación de PDF con la nueva consulta...")
        setting = db.query(Setting).first()
        pdf_buffer = generate_consultation_report_pdf(new_consult, setting)
        pdf_bytes = pdf_buffer.getvalue()
        assert len(pdf_bytes) > 1000
        print(f"PDF generado correctamente ({len(pdf_bytes)} bytes) con la Historia Clínica Unificada!")

        print("\n================ TODAS LAS PRUEBAS PASARON EXITOSAMENTE ================")

    finally:
        db.close()

if __name__ == "__main__":
    test_unified_clinical_history()
