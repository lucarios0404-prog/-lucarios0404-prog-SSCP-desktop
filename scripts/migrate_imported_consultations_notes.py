"""
Migration script to improve already imported consultations from Consulta Práctica:
- Copies clinical notes (HistoriaT) into symptoms (Anamnesis / Evolución Clínica)
- Refines generic reason with diagnosis or clinical follow-up
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import SessionLocal
from app.models.consultation import Consultation

def migrate():
    db = SessionLocal()
    try:
        imported = db.query(Consultation).filter(Consultation.sede_origen == "import_consulta_practica").all()
        print(f"Encontradas {len(imported)} consultas importadas.")
        
        updated_count = 0
        for c in imported:
            changed = False
            # 1. Update symptoms with real clinical note if present
            if c.notes and c.notes.strip().lower() not in ["no recabada", "none", ""]:
                if c.symptoms in ["Importado de historia clínica anterior", None, ""]:
                    c.symptoms = c.notes.strip()
                    changed = True
            elif c.symptoms in ["Importado de historia clínica anterior", None, ""]:
                c.symptoms = "Consulta histórica sin descripción de síntomas registrada en el sistema anterior."
                changed = True
                
            # 2. Improve generic reason
            if c.reason == "Consulta Histórica importada de Consulta Práctica":
                if c.diagnosis and c.diagnosis.strip().lower() not in ["sin diagnóstico especificado", "en estudio", ""]:
                    c.reason = f"Consulta: {c.diagnosis.strip()}"
                    changed = True
                else:
                    c.reason = "Consulta Médica / Chequeo Clínico"
                    changed = True

            if changed:
                updated_count += 1

        db.commit()
        print(f"[EXITO] {updated_count} consultas actualizadas con su información clínica completa.")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Error durante la migración: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
