import io
import json
import sys
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.appointment import Appointment  # noqa: E402
from app.models.consultation import Consultation  # noqa: E402
from app.models.insurance_preauthorization import InsurancePreauthorization  # noqa: E402
from app.models.inventory import InventoryItem, InventoryMovement  # noqa: E402
from app.models.lab_order import LabOrder  # noqa: E402
from app.models.medical_license import MedicalLicense  # noqa: E402
from app.models.patient import Patient  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.service import Service  # noqa: E402
from app.models.setting import Setting  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vital_sign import VitalSign  # noqa: E402
from app.services.patient_service import PatientService  # noqa: E402
from app.services.pdf_service import (  # noqa: E402
    generate_insurance_preauthorization_pdf,
    generate_lab_order_pdf,
    generate_medical_license_pdf,
)
from app.services.relay_service import RelayService  # noqa: E402


def _auth_cookies_for(role: str) -> dict:
    with SessionLocal() as db:
        user = db.query(User).filter(User.role == role, User.is_active == True).first()
        token = create_access_token(data={"email": user.email, "role": user.role})
        return {"access_token": f"Bearer {token}"}


def _bearer_headers_for(role: str) -> dict:
    with SessionLocal() as db:
        user = db.query(User).filter(User.role == role, User.is_active == True).first()
        token = create_access_token(data={"email": user.email, "role": user.role})
        return {"Authorization": f"Bearer {token}"}


def test_upcoming_appointments_filters_today_tomorrow_week_15days_all():
    today = date.today()
    created_ids = []
    with SessionLocal() as db:
        doc = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        patient = db.query(Patient).first()
        spec = [
            (today, "Hoy Activa", "Pendiente"),
            (today + timedelta(days=1), "Manana Confirmada", "Confirmada"),
            (today + timedelta(days=1), "Manana Cancelada", "Cancelada"),
            (today + timedelta(days=5), "Semana Cita", "Pendiente"),
            (today + timedelta(days=12), "Quince Dias Cita", "Confirmada"),
            (today + timedelta(days=25), "Veinticinco Dias Cita", "Pendiente"),
        ]
        for dt, rsn, st in spec:
            a = Appointment(
                patient_id=patient.id,
                doctor_id=doc.id,
                date=dt,
                start_time=time(10, 0),
                end_time=time(10, 30),
                reason=rsn,
                status=st,
            )
            db.add(a)
            db.flush()
            created_ids.append(a.id)
        db.commit()

    try:
        client = TestClient(app, headers=_bearer_headers_for("doctor"))

        r_today = client.get("/api/mobile/appointments/upcoming?range=today").json()
        today_reasons = {x["reason"] for x in r_today["appointments"]}
        assert "Hoy Activa" in today_reasons
        assert "Manana Confirmada" not in today_reasons
        assert "Semana Cita" not in today_reasons

        r_tmr = client.get("/api/mobile/appointments/upcoming?range=tomorrow").json()
        tmr_reasons = {x["reason"] for x in r_tmr["appointments"]}
        assert "Manana Confirmada" in tmr_reasons
        assert "Manana Cancelada" not in tmr_reasons
        assert "Hoy Activa" not in tmr_reasons
        assert "Semana Cita" not in tmr_reasons

        r_week = client.get("/api/mobile/appointments/upcoming?range=this_week").json()
        week_reasons = {x["reason"] for x in r_week["appointments"]}
        assert {"Manana Confirmada", "Semana Cita"}.issubset(week_reasons)
        assert "Hoy Activa" not in week_reasons
        assert "Quince Dias Cita" not in week_reasons
        assert "Veinticinco Dias Cita" not in week_reasons

        r_15 = client.get("/api/mobile/appointments/upcoming?range=next_15_days").json()
        d15_reasons = {x["reason"] for x in r_15["appointments"]}
        assert {"Manana Confirmada", "Semana Cita", "Quince Dias Cita"}.issubset(d15_reasons)
        assert "Hoy Activa" not in d15_reasons
        assert "Veinticinco Dias Cita" not in d15_reasons

        r_all = client.get("/api/mobile/appointments/upcoming?range=all").json()
        all_reasons = {x["reason"] for x in r_all["appointments"]}
        assert {"Manana Confirmada", "Semana Cita", "Quince Dias Cita", "Veinticinco Dias Cita"}.issubset(all_reasons)
        assert "Hoy Activa" not in all_reasons
        assert all("reminder_text" in x and "wa_link" in x for x in r_all["appointments"])
        assert "all_appointments" in r_all

        r_conf = client.get("/api/mobile/appointments/upcoming?range=all&status=confirmed").json()
        conf_reasons = {x["reason"] for x in r_conf["appointments"]}
        assert "Manana Confirmada" in conf_reasons
        assert "Semana Cita" not in conf_reasons
        assert "Hoy Activa" not in conf_reasons
    finally:
        with SessionLocal() as db:
            db.query(Appointment).filter(Appointment.id.in_(created_ids)).delete(synchronize_session=False)
            db.commit()


def test_patient_model_properties_and_duplicate_service_isolation():
    with SessionLocal() as db:
        doc1 = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        other_doc = User(
            name="Dr. Otro",
            email=f"otro_{uuid.uuid4().hex[:8]}@clinica.do",
            hashed_password=get_password_hash("Pass1234!"),
            role="doctor",
            is_active=True,
        )
        db.add(other_doc)
        db.commit()
        db.refresh(other_doc)

        dob = date(date.today().year - 30, 1, 1)
        p = Patient(
            first_name="Maria",
            last_name="IsoTest",
            document_id="402-9998881-1",
            phone="8095559988",
            date_of_birth=dob,
            doctor_id=other_doc.id,
        )
        db.add(p)
        db.commit()
        db.refresh(p)

        assert p.birth_date == dob
        assert p.mobile == "8095559988"
        assert p.age in (29, 30)
        assert p.chronic_conditions == "Ninguna"

        matches_doc1 = PatientService.find_potential_duplicates(
            db, "Maria", "IsoTest", document_id="402-9998881-1", doctor_id=doc1.id
        )
        assert all(m["id"] != p.id for m in matches_doc1)

        matches_other = PatientService.find_potential_duplicates(
            db, "Maria", "IsoTest", document_id="402-9998881-1", doctor_id=other_doc.id
        )
        assert any(m["id"] == p.id for m in matches_other)

        db.delete(p)
        db.delete(other_doc)
        db.commit()


def test_secretaria_cannot_complete_appointment_and_walkin_service():
    with SessionLocal() as db:
        doc = db.query(User).filter(User.role == "doctor").first()
        patient = db.query(Patient).first()
        svc = Service(name=f"Servicio Walkin {uuid.uuid4().hex[:6]}", price=2200.0, category="Consulta")
        db.add(svc)
        db.flush()
        appt = Appointment(
            patient_id=patient.id,
            doctor_id=doc.id,
            date=date.today(),
            start_time=time(14, 0),
            reason="Control Walkin",
            status="En Consulta",
        )
        db.add(appt)
        db.commit()
        appt_id = appt.id
        svc_id = svc.id
        pat_id = patient.id

    try:
        sec_web = TestClient(app, cookies=_auth_cookies_for("secretaria"))
        r_web = sec_web.post(f"/appointments/{appt_id}/status", data={"new_status": "Completada"})
        assert r_web.status_code == 403

        sec_mob = TestClient(app, headers=_bearer_headers_for("secretaria"))
        r_mob = sec_mob.post(f"/api/mobile/appointments/{appt_id}/status", json={"status": "Completada"})
        assert r_mob.status_code == 403

        # Walk-in check-in reuses today's Pendiente appointment cleanly
        with SessionLocal() as db:
            db.query(Appointment).filter(Appointment.id == appt_id).update({"status": "Pendiente"})
            db.commit()

        r_walkin = sec_web.post(
            "/appointments/check-in-walkin",
            data={"patient_id": str(pat_id), "service_id": str(svc_id)},
            follow_redirects=False,
        )
        assert r_walkin.status_code == 303
        with SessionLocal() as db:
            a_ref = db.query(Appointment).filter(Appointment.id == appt_id).first()
            assert a_ref.status == "En Espera"
            assert a_ref.service_id == svc_id
            assert a_ref.price == 2200.0
    finally:
        with SessionLocal() as db:
            db.query(Appointment).filter(
                (Appointment.id == appt_id) | (Appointment.service_id == svc_id)
            ).delete(synchronize_session=False)
            db.query(Service).filter(Service.id == svc_id).delete()
            db.commit()


def test_inventory_negative_stock_blocked_and_backup_export():
    with SessionLocal() as db:
        item = InventoryItem(name=f"Insumo_{uuid.uuid4().hex[:6]}", stock=2, min_stock=1, price=350.0)
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id

    try:
        doc_client = TestClient(app, cookies=_auth_cookies_for("doctor"))
        bad_out = doc_client.post(
            f"/inventory/{item_id}/movement",
            data={"type": "out", "quantity": "5", "notes": "Exceso"},
        )
        assert bad_out.status_code == 400

        with SessionLocal() as db:
            refreshed = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
            assert refreshed.stock == 2

        backup_resp = doc_client.get("/settings/backup/export")
        assert backup_resp.status_code == 200
        assert backup_resp.content.startswith(b"SQLite format 3\x00")
    finally:
        with SessionLocal() as db:
            db.query(InventoryMovement).filter(InventoryMovement.inventory_item_id == item_id).delete()
            db.query(InventoryItem).filter(InventoryItem.id == item_id).delete()
            db.commit()


def test_mobile_p2_parity_cie10_allergy_vitals_inventory_preauth():
    with SessionLocal() as db:
        patient = Patient(
            first_name="Alergia",
            last_name="TestP2",
            allergies="Penicilina",
            is_active=True,
        )
        item = InventoryItem(name=f"KitSutura_{uuid.uuid4().hex[:5]}", stock=3, min_stock=1, price=850.0)
        db.add(patient)
        db.add(item)
        db.commit()
        db.refresh(patient)
        db.refresh(item)
        pat_id = patient.id
        item_id = item.id

    created_cons_id = None
    created_preauth_id = None
    created_pay_id = None
    try:
        doc_mob = TestClient(app, headers=_bearer_headers_for("doctor"))
        cie = doc_mob.get("/api/mobile/cie10/search?q=I10")
        assert cie.status_code == 200
        assert any("I10" in x["code"] for x in cie.json()["items"])

        # Allergy block -> 409 without override
        conflict = doc_mob.post(
            "/api/mobile/consultations/quick",
            json={
                "patient_id": pat_id,
                "diagnosis": "J02.9 - Faringitis aguda",
                "prescription": "Amoxicilina / Penicilina 500mg cada 8h",
                "weight_kg": 72.5,
                "systolic_bp": 120,
                "diastolic_bp": 80,
            },
        )
        assert conflict.status_code == 409

        # Override=True succeeds and creates Consultation + linked VitalSign
        ok = doc_mob.post(
            "/api/mobile/consultations/quick",
            json={
                "patient_id": pat_id,
                "diagnosis": "J02.9 - Faringitis aguda",
                "clinical_history": "Odinofagia 48h",
                "prescription": "Penicilina V bajo supervisión",
                "weight_kg": 72.5,
                "systolic_bp": 120,
                "diastolic_bp": 80,
                "force_allergy_override": True,
            },
        )
        assert ok.status_code == 200
        created_cons_id = ok.json()["consultation_id"]

        with SessionLocal() as db:
            v = db.query(VitalSign).filter(VitalSign.consultation_id == created_cons_id).first()
            assert v is not None and v.weight_kg == 72.5

        pre = doc_mob.post(
            "/api/mobile/preauthorizations",
            json={
                "patient_id": pat_id,
                "ars_name": "ARS Humano",
                "service_type": "Sonografía Pélvica",
                "cie10_code": "Z00.0",
                "clinical_indication": "Estudio control",
            },
        )
        assert pre.status_code == 200
        created_preauth_id = pre.json()["preauthorization_id"]

        pay = doc_mob.post(
            "/api/mobile/payments/quick",
            json={
                "patient_id": pat_id,
                "amount": 850.0,
                "payment_method": "Efectivo",
                "item_type": "articulo",
                "service_id": item_id,
                "service_name": "KitSutura",
            },
        )
        assert pay.status_code == 200
        created_pay_id = pay.json()["payment_id"]

        with SessionLocal() as db:
            inv = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
            assert inv.stock == 2
    finally:
        with SessionLocal() as db:
            if created_pay_id:
                db.query(Payment).filter(Payment.id == created_pay_id).delete()
            db.query(InventoryMovement).filter(InventoryMovement.inventory_item_id == item_id).delete()
            db.query(InventoryItem).filter(InventoryItem.id == item_id).delete()
            if created_preauth_id:
                db.query(InsurancePreauthorization).filter(InsurancePreauthorization.id == created_preauth_id).delete()
            if created_cons_id:
                db.query(VitalSign).filter(VitalSign.consultation_id == created_cons_id).delete()
                db.query(Consultation).filter(Consultation.id == created_cons_id).delete()
            from app.models.audit_log import ClinicalAuditLog
            db.query(ClinicalAuditLog).filter(ClinicalAuditLog.patient_id == pat_id).delete()
            db.query(Patient).filter(Patient.id == pat_id).delete()
            db.commit()


def test_pdf_service_non_obstetric_license_and_lab_colwidths():
    custom_doc = User(name="Dra. Elena Ruiz", email="elena@sscp.test", role="doctor")
    pat = Patient(first_name="Pedro", last_name="Pérez", document_id="001-1111111-1", gender="Masculino")
    custom_setting = Setting(
        clinic_name="Clínica Pediátrica Central",
        doctor_name="Dra. Elena Ruiz",
        specialty="Pediatría",
        doctor_exequatur="9988-22",
        doctor_cedula="001-9999999-9",
    )
    lic = MedicalLicense(
        patient=pat,
        doctor=custom_doc,
        diagnosis="J00 - Resfriado común",
        days_rest=3,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=2),
        workplace_or_school="Colegio Norte",
        notes="",
    )
    buf_lic = generate_medical_license_pdf(lic, setting=custom_setting)
    raw_lic = buf_lic.getvalue()
    assert raw_lic.startswith(b"%PDF-")

    order = LabOrder(
        patient=pat,
        doctor_id=1,
        order_date=date.today(),
        clinical_indication="Chequeo <anual> & control",
        tests_requested=json.dumps(["Hemograma Completo", "Glicemia en Ayunas", "Perfil Lipídico"]),
    )
    buf_lab = generate_lab_order_pdf(order, setting=custom_setting)
    assert buf_lab.getvalue().startswith(b"%PDF-")

    preauth = InsurancePreauthorization(
        patient=pat,
        doctor=custom_doc,
        ars_name="SeNaSa",
        request_type="Procedimiento Ambulatorio",
        request_date=date.today(),
        presumptive_diagnosis="J00",
        procedures_json=json.dumps([{"code": "99", "procedure": "Consulta"}]),
    )
    buf_pre = generate_insurance_preauthorization_pdf(preauth, setting=custom_setting)
    assert buf_pre.getvalue().startswith(b"%PDF-")


def test_relay_service_skips_orphan_payments():
    with SessionLocal() as db:
        before_count = db.query(Payment).count()
        stats = RelayService.reconcile_incoming_delta(
            db,
            {
                "patients": [],
                "appointments": [],
                "payments": [
                    {
                        "patient_id": 99999999,
                        "amount": 1500.0,
                        "receipt_number": f"ORPHAN-{uuid.uuid4().hex[:6]}",
                        "status": "paid",
                    }
                ],
            },
        )
        assert stats["processed_payments"] == 0
        assert db.query(Payment).count() == before_count


def test_waiting_room_protected_against_confirm_and_due_reminders_exposed():
    today = date.today()
    tomorrow = today + timedelta(days=1)
    created_ids = []
    with SessionLocal() as db:
        doc = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        patient = db.query(Patient).first()
        waiting_appt = Appointment(
            patient_id=patient.id,
            doctor_id=doc.id,
            date=today,
            start_time=time(9, 0),
            end_time=time(9, 30),
            reason="Turno Sala Hoy",
            status="En Espera",
            queue_number=4,
            whatsapp_reminder_sent=False,
        )
        tmr_appt = Appointment(
            patient_id=patient.id,
            doctor_id=doc.id,
            date=tomorrow,
            start_time=time(11, 0),
            end_time=time(11, 30),
            reason="Recordatorio Manana WS",
            status="Pendiente",
            whatsapp_reminder_sent=False,
        )
        db.add_all([waiting_appt, tmr_appt])
        db.flush()
        created_ids.extend([waiting_appt.id, tmr_appt.id])
        db.commit()
        w_id, t_id = waiting_appt.id, tmr_appt.id

    try:
        sec_mobile = TestClient(app, headers=_bearer_headers_for("secretaria"))
        # 1) Confirmar una cita ya En Espera debe devolver 409 y preservar turno #4
        res_409 = sec_mobile.post(f"/api/mobile/appointments/{w_id}/status", json={"status": "Confirmada"})
        assert res_409.status_code == 409
        with SessionLocal() as db:
            refreshed_w = db.query(Appointment).filter(Appointment.id == w_id).first()
            assert refreshed_w.status == "En Espera"
            assert refreshed_w.queue_number == 4

        # 2) Recepción /reception/appointments/{id}/status tampoco puede degradar En Espera
        sec_web = TestClient(app, cookies=_auth_cookies_for("secretaria"))
        res_web_409 = sec_web.post(f"/reception/appointments/{w_id}/status", data={"status": "Confirmada"})
        assert res_web_409.status_code == 409

        # 3) Dashboard móvil expone due_reminders con recordatorio listo para copiar/WS (excluyendo En Espera)
        dash = sec_mobile.get("/api/mobile/dashboard").json()
        due = dash["due_reminders"]
        assert due["tomorrow_unsent"] >= 1
        due_ids = {item["id"] for item in due["items"]}
        assert t_id in due_ids
        assert w_id not in due_ids
        tmr_item = next(item for item in due["items"] if item["id"] == t_id)
        assert tmr_item["reminder_text"]

        # 4) Filtro unsent_wa + confirmar cita futura sin afectar Sala de Espera
        unsent = sec_mobile.get("/api/mobile/appointments/upcoming?range=tomorrow&status=unsent_wa").json()
        assert any(a["id"] == t_id for a in unsent["appointments"])
        ok_conf = sec_mobile.post(f"/api/mobile/appointments/{t_id}/status", json={"status": "Confirmada"})
        assert ok_conf.status_code == 200
        assert ok_conf.json()["new_status"] == "Confirmada"

        # 5) Marcar whatsapp-sent deja intacto el status Confirmada
        ok_wa = sec_mobile.post(f"/api/mobile/appointments/{t_id}/whatsapp-sent")
        assert ok_wa.status_code == 200
        with SessionLocal() as db:
            refreshed_t = db.query(Appointment).filter(Appointment.id == t_id).first()
            assert refreshed_t.status == "Confirmada"
            assert refreshed_t.whatsapp_reminder_sent is True
    finally:
        with SessionLocal() as db:
            db.query(Appointment).filter(Appointment.id.in_(created_ids)).delete(synchronize_session=False)
            db.commit()
