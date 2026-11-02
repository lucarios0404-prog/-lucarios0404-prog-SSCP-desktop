import pytest
from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.appointment import Appointment
from app.models.user import User

client = TestClient(app)

def test_api_patient_last_consultation_structure():
    db = SessionLocal()
    # Find patient with at least 1 consultation
    c = db.query(Consultation).first()
    assert c is not None, "Debe haber al menos 1 consulta en la base de datos de prueba"
    patient_id = c.patient_id

    # Simulate doctor user login / cookie
    user = db.query(User).first()
    assert user is not None

    # Call endpoint directly with TestClient
    # Note: depends(require_permission('consultations')) checks session cookie
    from app.routers.consultations import api_patient_last_consultation
    res = api_patient_last_consultation(patient_id, db, user)
    
    # Get latest consultation for that patient
    latest_c = db.query(Consultation).filter(
        Consultation.patient_id == patient_id
    ).order_by(Consultation.created_at.desc(), Consultation.id.desc()).first()

    assert res["found"] is True
    assert res["has_history"] is True
    assert "consultation" in res
    assert res["consultation"]["id"] == latest_c.id
    assert "reason" in res["consultation"]
    assert "diagnosis" in res["consultation"]
    assert "clinical_history" in res["consultation"]

def test_reports_monthly_logic():
    db = SessionLocal()
    user = db.query(User).first()

    from app.routers.reports import reports_monthly
    from starlette.requests import Request
    
    # Simular Request
    scope = {"type": "http", "method": "GET", "path": "/reports/monthly", "headers": []}
    req = Request(scope)

    # Probar para mes de Octubre 2026 (mes con datos)
    resp = reports_monthly(req, month="2026-10", db=db, current_user=user)
    assert resp.status_code == 200
    
    # Verificar que el template se renderice con los datos
    assert b"Informe Mensual de Actividad" in resp.body
    assert b"Tipos de Citas y Consultas del Mes" in resp.body
    assert b"D\xc3\xada M\xc3\xa1s Fuerte" in resp.body or b"Dia Mas Fuerte" in resp.body
