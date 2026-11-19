import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.styles import getSampleStyleSheet

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.appointment import Appointment  # noqa: E402
from app.models.audit_log import ClinicalAuditLog  # noqa: E402
from app.models.consultation import Consultation  # noqa: E402
from app.models.lab_result import LabResult  # noqa: E402
from app.models.medical_license import MedicalLicense  # noqa: E402
from app.models.patient import Patient  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vaccine import VaccineRecord  # noqa: E402
from app.routers.payments import is_paid_payment, normalize_payment_method  # noqa: E402
from app.services.pdf_service import Paragraph  # noqa: E402


def _auth_cookies_for(role: str) -> dict:
    with SessionLocal() as db:
        user = db.query(User).filter(User.role == role, User.is_active == True).first()
        assert user is not None, f"Missing active seeded user for role={role}"
        token = create_access_token(data={"email": user.email, "role": user.role})
        return {"access_token": f"Bearer {token}"}


def _bearer_headers_for(role: str) -> dict:
    with SessionLocal() as db:
        user = db.query(User).filter(User.role == role, User.is_active == True).first()
        assert user is not None, f"Missing active seeded user for role={role}"
        token = create_access_token(data={"email": user.email, "role": user.role})
        return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_endpoints_blocked(monkeypatch):
    client = TestClient(app)

    assert client.get("/api/relay/status").status_code in (401, 403)
    assert client.get("/api/relay/qr-link").status_code in (401, 403)
    assert client.get("/sync/peer/delta").status_code in (401, 403)
    assert client.post("/sync/peer/import", json={}).status_code in (401, 403)
    assert client.get("/settings/print-config").status_code in (401, 403)

    monkeypatch.setenv("SSCP_IPC_SECRET", "unit-test-ipc-secret-value")
    resp = client.post("/api/internal/graceful-shutdown")
    assert resp.status_code == 403


def test_setup_locked_when_custom_user_exists():
    with SessionLocal() as db:
        custom = User(
            name="Dr. Personalizado",
            email=f"custom_{uuid.uuid4().hex[:8]}@clinica.do",
            hashed_password=get_password_hash("StrongPass123!"),
            role="doctor",
            is_active=True,
        )
        db.add(custom)
        db.commit()
        custom_id = custom.id

    try:
        anon = TestClient(app)
        login_page = anon.get("/login")
        assert login_page.status_code == 200
        assert 'href="/setup"' not in login_page.text

        setup_get = anon.get("/setup", follow_redirects=False)
        assert setup_get.status_code in (302, 303, 401, 403)

        setup_post = anon.post(
            "/setup",
            data={
                "name": "Attacker",
                "email": "attacker@evil.test",
                "password": "Password123!",
                "password_confirm": "Password123!",
            },
            follow_redirects=False,
        )
        assert setup_post.status_code in (302, 303, 401, 403)
        with SessionLocal() as db:
            assert db.query(User).filter(User.email == "attacker@evil.test").first() is None
    finally:
        with SessionLocal() as db:
            u = db.query(User).filter(User.id == custom_id).first()
            if u:
                db.delete(u)
                db.commit()


def test_inactive_user_rejected_across_web_and_api():
    email = f"inactive_{uuid.uuid4().hex[:8]}@sscp.com"
    with SessionLocal() as db:
        u = User(
            name="Usuario Inactivo",
            email=email,
            hashed_password=get_password_hash("Secret1234!"),
            role="secretaria",
            is_active=False,
        )
        db.add(u)
        db.commit()
        uid = u.id

    try:
        client = TestClient(app)
        web_login = client.post(
            "/login",
            data={"email": email, "password": "Secret1234!"},
            follow_redirects=False,
        )
        assert web_login.status_code in (200, 401, 403)
        assert "access_token" not in web_login.cookies

        token_resp = client.post("/auth/token", data={"username": email, "password": "Secret1234!"})
        assert token_resp.status_code in (401, 403)

        mob_resp = client.post("/api/mobile/login", json={"email": email, "password": "Secret1234!"})
        assert mob_resp.status_code in (401, 403)

        forged_token = create_access_token(data={"email": email, "role": "secretaria"})
        dash = client.get(
            "/dashboard",
            cookies={"access_token": f"Bearer {forged_token}"},
            follow_redirects=False,
        )
        assert dash.status_code in (302, 303, 307, 401, 403)
    finally:
        with SessionLocal() as db:
            u = db.query(User).filter(User.id == uid).first()
            if u:
                db.delete(u)
                db.commit()


def test_doctor_cannot_escalate_to_admin():
    doc_client = TestClient(app, cookies=_auth_cookies_for("doctor"))
    evil_email = f"fake_admin_{uuid.uuid4().hex[:8]}@sscp.com"
    create_resp = doc_client.post(
        "/users/create",
        data={
            "name": "Fake Admin",
            "email": evil_email,
            "password": "Password123!",
            "role": "admin",
        },
        follow_redirects=False,
    )
    assert create_resp.status_code in (302, 303, 403)
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == evil_email).first() is None
        admin = db.query(User).filter(User.role == "admin").first()
        assert admin is not None
        admin_id = admin.id

    edit_resp = doc_client.post(
        f"/users/{admin_id}/edit",
        data={
            "name": "Hacked Admin",
            "email": "admin@sscp.com",
            "role": "admin",
            "is_active": "1",
        },
        follow_redirects=False,
    )
    assert edit_resp.status_code == 403


def test_secretaria_clinical_confidentiality_and_rbac():
    with SessionLocal() as db:
        cons = db.query(Consultation).first()
        assert cons is not None
        patient_id = cons.patient_id
        cons_id = cons.id

    sec_web = TestClient(app, cookies=_auth_cookies_for("secretaria"))
    assert sec_web.get(f"/consultations/{cons_id}", follow_redirects=False).status_code in (302, 303, 403)
    assert sec_web.get(f"/appointments/patient-consultations/{patient_id}", follow_redirects=False).status_code == 403
    assert sec_web.get("/lab-results/", follow_redirects=False).status_code in (302, 303, 403)
    assert sec_web.get("/templates/", follow_redirects=False).status_code in (302, 303, 403)
    assert sec_web.get("/reports/", follow_redirects=False).status_code in (302, 303, 403)

    # Secretary can view patient administrative ficha + print prescriptions, NOT clinical evolution notes
    patient_view = sec_web.get(f"/patients/{patient_id}", follow_redirects=False)
    assert patient_view.status_code == 200
    assert "Paciente estable para pruebas de reporte mensual" not in patient_view.text

    sec_headers = _bearer_headers_for("secretaria")
    sec_mob = TestClient(app, headers=sec_headers)
    details = sec_mob.get(f"/api/mobile/patients/{patient_id}/details")
    assert details.status_code == 200
    assert details.json()["consultations"] == []

    mob_summary = sec_mob.get("/api/mobile/reports/summary")
    assert mob_summary.status_code in (200, 403)
    if mob_summary.status_code == 200:
        assert mob_summary.json()["attended"]["items"] == []


def test_patient_allergies_empty_document_and_cascade_delete():
    doc_client = TestClient(app, cookies=_auth_cookies_for("doctor"))

    # Create two patients without cédula (empty string -> NULL, no UNIQUE conflict)
    for idx in (1, 2):
        resp = doc_client.post(
            "/patients/create",
            data={
                "first_name": f"SinCedula{idx}",
                "last_name": "Prueba",
                "document_id": "",
                "phone": f"809000100{idx}",
                "allergies": "Penicilina",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

    with SessionLocal() as db:
        p1 = db.query(Patient).filter(Patient.first_name == "SinCedula1").first()
        p2 = db.query(Patient).filter(Patient.first_name == "SinCedula2").first()
        assert p1 is not None and p2 is not None
        assert p1.document_id is None and p2.document_id is None
        p1_id = p1.id
        p2_id = p2.id

        # Attach child records + audit log for cascade delete test on p1
        db.add(LabResult(patient_id=p1_id, test_name="Hemograma", result_date=date.today(), summary_findings="Normal"))
        db.add(VaccineRecord(patient_id=p1_id, vaccine_name="Influenza", application_date=date.today()))
        db.add(ClinicalAuditLog(patient_id=p1_id, action="TEST_AUDIT", entity_type="Patient", entity_id=p1_id, summary="Prueba cascada"))
        db.commit()

    # Edit p2 WITHOUT sending allergies field or WITH allergies preserved
    edit_resp = doc_client.post(
        f"/patients/{p2_id}/edit",
        data={
            "first_name": "SinCedula2",
            "last_name": "Actualizado",
            "document_id": "",
            "phone": "8090001002",
            "allergies": "Penicilina",
        },
        follow_redirects=False,
    )
    assert edit_resp.status_code == 303

    with SessionLocal() as db:
        p2_refreshed = db.query(Patient).filter(Patient.id == p2_id).first()
        assert p2_refreshed.allergies == "Penicilina"

    del_resp = doc_client.post(f"/patients/{p1_id}/permanent-delete", follow_redirects=False)
    assert del_resp.status_code == 303

    with SessionLocal() as db:
        assert db.query(Patient).filter(Patient.id == p1_id).first() is None
        assert db.query(LabResult).filter(LabResult.patient_id == p1_id).count() == 0
        assert db.query(VaccineRecord).filter(VaccineRecord.patient_id == p1_id).count() == 0
        # Audit log preserved with detached patient_id
        log = db.query(ClinicalAuditLog).filter(ClinicalAuditLog.action == "TEST_AUDIT", ClinicalAuditLog.entity_id == p1_id).first()
        assert log is not None and log.patient_id is None

        # Cleanup p2
        p2_del = db.query(Patient).filter(Patient.id == p2_id).first()
        if p2_del:
            db.delete(p2_del)
            db.commit()


def test_pay_later_and_payment_method_normalization():
    assert normalize_payment_method("cash") == "cash"
    assert normalize_payment_method("Efectivo") == "cash"
    assert normalize_payment_method("Seguro Médico") == "insurance"
    assert normalize_payment_method("Copago ARS") == "copay"
    assert is_paid_payment("paid") is True
    assert is_paid_payment("Pagado") is True
    assert is_paid_payment("pending") is False

    with SessionLocal() as db:
        patient = db.query(Patient).first()
        doc = db.query(User).filter(User.role == "doctor").first()
        assert patient is not None and doc is not None
        patient_id = patient.id
        doc_id = doc.id

    doc_client = TestClient(app, cookies=_auth_cookies_for("doctor"))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = doc_client.post(
        "/appointments/create",
        data={
            "patient_id": str(patient_id),
            "date": tomorrow,
            "start_time": "09:30",
            "end_time": "10:00",
            "reason": "Consulta Test PayLater",
            "price": "2500",
            "payment_action": "pay_later",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    with SessionLocal() as db:
        pay = (
            db.query(Payment)
            .filter(Payment.patient_id == patient_id, Payment.status == "pending")
            .order_by(Payment.id.desc())
            .first()
        )
        assert pay is not None
        assert pay.total == 2500.0
        pay_id = pay.id
        appt_id = pay.appointment_id

    try:
        pay_resp = doc_client.post(
            f"/payments/{pay_id}/pay",
            data={"payment_method": "Copago ARS"},
            follow_redirects=False,
        )
        assert pay_resp.status_code == 303
        with SessionLocal() as db:
            paid = db.query(Payment).filter(Payment.id == pay_id).first()
            assert is_paid_payment(paid.status) is True
            assert normalize_payment_method(paid.payment_method) == "copay"
    finally:
        with SessionLocal() as db:
            p = db.query(Payment).filter(Payment.id == pay_id).first()
            if p:
                db.delete(p)
            if appt_id:
                a = db.query(Appointment).filter(Appointment.id == appt_id).first()
                if a:
                    db.delete(a)
            db.commit()


def test_license_print_and_pdf_xml_safety():
    styles = getSampleStyleSheet()
    p = Paragraph("Paciente <malo> & glucosa < 90 mg/dL & > 50 <b>estable</b>", styles["Normal"])
    assert p is not None

    with SessionLocal() as db:
        patient = db.query(Patient).first()
        doc = db.query(User).filter(User.role == "doctor").first()
        lic = MedicalLicense(
            patient_id=patient.id,
            doctor_id=doc.id,
            days_rest=3,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            diagnosis="J00 - Rinofaringitis aguda",
            workplace_or_school="Empresa Test",
            notes="Reposo domiciliario < 72h & hidratación",
        )
        db.add(lic)
        db.commit()
        lic_id = lic.id

    try:
        doc_client = TestClient(app, cookies=_auth_cookies_for("doctor"))
        resp = doc_client.get(f"/licenses/{lic_id}/print")
        assert resp.status_code == 200
        assert "Licencia" in resp.text or "Reposo" in resp.text
    finally:
        with SessionLocal() as db:
            obj = db.query(MedicalLicense).filter(MedicalLicense.id == lic_id).first()
            if obj:
                db.delete(obj)
                db.commit()


def test_mobile_chart_js_and_mobile_api_p0_contracts():
    anon = TestClient(app)
    chart_js = anon.get("/mobile/chart.min.js")
    assert chart_js.status_code == 200
    assert len(chart_js.content) > 1000

    doc_mob = TestClient(app, headers=_bearer_headers_for("doctor"))
    opts = doc_mob.get("/api/mobile/patients/options")
    assert opts.status_code == 200
    items = opts.json().get("patients", [])
    assert len(items) >= 1
    assert {"date_of_birth", "gender", "address"}.issubset(items[0].keys())

    with SessionLocal() as db:
        patient = db.query(Patient).first()
        patient_id = patient.id

    # Future quick appointment must start as Pendiente without queue number
    future_date = (date.today() + timedelta(days=5)).isoformat()
    appt_resp = doc_mob.post(
        "/api/mobile/appointments/quick-create",
        json={
            "patient_id": patient_id,
            "date": future_date,
            "start_time": "11:00",
            "reason": "Seguimiento Futuro",
        },
    )
    assert appt_resp.status_code == 200
    appt_id = appt_resp.json()["appointment_id"]

    # Idempotent quick consultation via client_uuid
    c_uuid = f"test-cons-{uuid.uuid4().hex}"
    payload = {
        "patient_id": patient_id,
        "reason": "Control hipertensión",
        "diagnosis": "I10 - Hipertensión esencial",
        "treatment": "Continuar esquema",
        "client_uuid": c_uuid,
    }
    r1 = doc_mob.post("/api/mobile/consultations/quick", json=payload)
    r2 = doc_mob.post("/api/mobile/consultations/quick", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    c_id_1 = r1.json()["consultation_id"]
    c_id_2 = r2.json()["consultation_id"]
    assert c_id_1 == c_id_2

    try:
        with SessionLocal() as db:
            a = db.query(Appointment).filter(Appointment.id == appt_id).first()
            assert a.status == "Pendiente"
            assert a.queue_number is None
    finally:
        with SessionLocal() as db:
            a = db.query(Appointment).filter(Appointment.id == appt_id).first()
            if a:
                db.delete(a)
            c = db.query(Consultation).filter(Consultation.id == c_id_1).first()
            if c:
                db.delete(c)
            db.commit()
