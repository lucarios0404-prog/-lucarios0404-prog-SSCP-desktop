import atexit
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

_CREATED_TEMP_DIR = None
if not os.environ.get("SSCP_DATA_DIR"):
    _CREATED_TEMP_DIR = tempfile.mkdtemp(prefix="sscp_pytest_")
    os.environ["SSCP_DATA_DIR"] = _CREATED_TEMP_DIR

from app.database import Base, engine, SessionLocal  # noqa: E402
import app.models  # noqa: F401, E402
from main import ensure_schema_migrations  # noqa: E402
from app.core.permissions import seed_permissions_if_empty  # noqa: E402
from app.core.initial_data import seed_initial_data_if_empty  # noqa: E402
from app.data.cie10_catalog import seed_cie10_catalog  # noqa: E402
from app.data.services_catalog import seed_services_if_empty  # noqa: E402
from app.models.consultation import Consultation  # noqa: E402
from app.models.license_config import LicenseConfig  # noqa: E402
from app.models.patient import Patient  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.license_service import (  # noqa: E402
    DATA_DIR,
    LICENSE_CACHE_FILE,
    _compute_cache_signature,
    get_machine_id,
)


def _provision_test_license(db) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    test_key = "SSCPL-PYTEST-ONLINE-KEY"
    machine_id = get_machine_id()
    now = datetime.now(timezone.utc)
    cache = {
        "valid": True,
        "machine_id": machine_id,
        "license_token": test_key,
        "doctor_name": "Dr. Carlos Mendoza",
        "plan": "Pro",
        "expires_at": (now + timedelta(days=365)).isoformat(),
        "cached_at": now.isoformat(),
    }
    cache["signature"] = _compute_cache_signature(cache, machine_id)
    LICENSE_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    cfg = db.query(LicenseConfig).first()
    if not cfg:
        cfg = LicenseConfig(
            license_key=test_key,
            mode="online",
            machine_id=machine_id,
            doctor_name="Dr. Carlos Mendoza",
            plan="Pro",
        )
        db.add(cfg)
        db.commit()


def _bootstrap_test_database() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_migrations(engine)

    with SessionLocal() as db:
        seed_cie10_catalog(db)
        seed_permissions_if_empty(db)
        seed_initial_data_if_empty(db)
        seed_services_if_empty(db)
        _provision_test_license(db)

        if db.query(Consultation).count() == 0:
            doc = db.query(User).filter(User.role == "doctor").first()
            patient = db.query(Patient).first()
            if not patient:
                patient = Patient(
                    first_name="Paciente",
                    last_name="Prueba",
                    document_id="001-0000001-1",
                    phone="8095550101",
                    doctor_id=doc.id if doc else None,
                )
                db.add(patient)
                db.commit()
                db.refresh(patient)

            consultation = Consultation(
                patient_id=patient.id,
                doctor_id=doc.id if doc else None,
                reason="Control general",
                diagnosis="Z00.0 - Examen médico general",
                clinical_history="Paciente estable para pruebas de reporte mensual.",
                treatment="Seguimiento ambulatorio",
                prescription="Hidratación adecuada",
                is_first_visit=True,
                created_at=datetime(2026, 10, 15, 10, 0),
            )
            db.add(consultation)
            db.commit()


_bootstrap_test_database()


def _cleanup_temp_dir() -> None:
    if _CREATED_TEMP_DIR and os.path.exists(_CREATED_TEMP_DIR):
        try:
            engine.dispose()
        except Exception:
            pass
        shutil.rmtree(_CREATED_TEMP_DIR, ignore_errors=True)


atexit.register(_cleanup_temp_dir)
