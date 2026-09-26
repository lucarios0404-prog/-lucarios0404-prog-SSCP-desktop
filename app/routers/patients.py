from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pathlib import Path
from datetime import datetime, date, timedelta, time
from typing import Optional

from app.database import get_db
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.vital_sign import VitalSign
from app.models.service import Service
from app.models.user import User
from app.core.deps import require_current_user
from app.services.patient_service import PatientService
from app.services.audit_service import AuditService

from app.core.templates import templates
from app.services.ars_service import get_all_ars, ARS_LIST
from app.routers.appointments import assign_next_queue_number
from app.routers.payments import generate_receipt_number

router = APIRouter(prefix="/patients", tags=["patients"])

@router.post("/check-duplicate")
async def check_duplicate_patient(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Detector Inteligente de Pacientes Duplicados (F9).
    """
    try:
        data = await request.json()
    except Exception:
        data = {}

    matches = PatientService.find_potential_duplicates(
        db=db,
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        document_id=data.get("document_id"),
        phone=data.get("phone"),
        exclude_id=data.get("exclude_id")
    )
    return {"has_duplicates": len(matches) > 0, "matches": matches}

@router.get("/")
def list_patients(
    request: Request,
    q: str = Query(None),
    status: str = Query("active"),
    page: int = Query(1, ge=1),
    per_page: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    is_admin = getattr(current_user, "role", "") == "admin"
    view_archived = (status == "archived") and is_admin
    
    # Contadores para las pestañas de navegación
    active_count = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).count()
    archived_count = db.query(Patient).filter(Patient.is_active == False).count() if is_admin else 0

    query = db.query(Patient)
    if view_archived:
        query = query.filter(Patient.is_active == False)
    else:
        query = query.filter(or_(Patient.is_active == True, Patient.is_active == None))

    clean_q = q.strip() if q else ""
    if clean_q:
        search = f"%{clean_q}%"
        query = query.filter(
            or_(
                Patient.first_name.ilike(search),
                Patient.last_name.ilike(search),
                func.concat(Patient.first_name, " ", Patient.last_name).ilike(search),
                Patient.document_id.ilike(search),
                Patient.phone.ilike(search),
                Patient.email.ilike(search)
            )
        )
    
    total_count = query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        
    offset = (page - 1) * per_page
    patients = query.order_by(
        Patient.archived_at.desc() if view_archived else Patient.last_name.asc(),
        Patient.first_name.asc()
    ).offset(offset).limit(per_page).all()
    
    # Calcular saldos pendientes solo para los pacientes visibles en esta página
    patient_cards = []
    for p in patients:
        pending_sum = sum(pay.total for pay in p.payments if pay.status == "pending") if hasattr(p, "payments") and p.payments else 0
        patient_cards.append({
            "patient": p,
            "balance_due": pending_sum,
            "has_debt": pending_sum > 0
        })

    return templates.TemplateResponse(
        request=request,
        name="patients/index.html",
        context={
            "user": current_user,
            "patient_cards": patient_cards,
            "search_query": clean_q,
            "status_filter": "archived" if view_archived else "active",
            "active_count": active_count,
            "archived_count": archived_count,
            "is_admin": is_admin,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "start_item": offset + 1 if total_count > 0 else 0,
            "end_item": min(offset + per_page, total_count),
        }
    )

@router.get("/create")
def create_patient_form(
    request: Request,
    current_user = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category.asc(), Service.name.asc()).all()
    today_str = date.today().strftime("%Y-%m-%d")
    now_time_str = datetime.now().strftime("%H:%M")
    return templates.TemplateResponse(
        request=request,
        name="patients/create.html",
        context={
            "user": current_user,
            "ARS_LIST": get_all_ars(),
            "services": services,
            "today_str": today_str,
            "now_time_str": now_time_str,
        }
    )

@router.post("/create")
def create_patient(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    document_id: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    blood_type: Optional[str] = Form(None),
    allergies: Optional[str] = Form(None),
    emergency_contact_name: Optional[str] = Form(None),
    emergency_contact_phone: Optional[str] = Form(None),
    insurance_name: Optional[str] = Form("Privado / Particular"),
    insurance_number: Optional[str] = Form(None),
    # Nuevos parámetros del flujo continuo de recepción: Cita y Cobro
    schedule_action: Optional[str] = Form("none"), # 'none', 'today', 'scheduled'
    appt_date: Optional[str] = Form(None),
    appt_time: Optional[str] = Form(None),
    service_id: Optional[int] = Form(None),
    appt_reason: Optional[str] = Form(None),
    payment_action: Optional[str] = Form("none"), # 'none', 'charge_now', 'pay_later'
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    dob = None
    if date_of_birth:
        try:
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        except ValueError:
            dob = None

    new_patient = Patient(
        first_name=first_name,
        last_name=last_name,
        document_id=document_id,
        date_of_birth=dob,
        gender=gender,
        phone=phone,
        email=email,
        address=address,
        blood_type=blood_type,
        allergies=allergies,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_phone=emergency_contact_phone,
        insurance_name=insurance_name or "Privado / Particular",
        insurance_number=insurance_number
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)

    # Registrar en bitácora de auditoría médica (F13)
    AuditService.log_change(
        db=db,
        entity_type="patient",
        entity_id=new_patient.id,
        action="create",
        summary=f"Expediente clínico creado para {new_patient.first_name} {new_patient.last_name}",
        patient_id=new_patient.id,
        user_id=current_user.id if current_user else 1,
        new_data={"document_id": document_id, "phone": phone, "allergies": allergies}
    )

    # ── Flujo Continuo de Recepción: Planificación de Cita & Cobro ──────────
    if schedule_action == "today":
        today = date.today()
        now_time = datetime.now().time()
        end_time_val = (datetime.now() + timedelta(minutes=30)).time()
        next_q = assign_next_queue_number(db, today)

        doctor = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        doc_id = current_user.id if current_user.role == "doctor" else (doctor.id if doctor else 1)

        price = 0.0
        svc = None
        if service_id and service_id > 0:
            svc = db.query(Service).filter(Service.id == service_id).first()
            if svc:
                price = float(svc.price or 0.0)

        reason_val = appt_reason or (svc.name if svc else "Consulta Médica General - Llegada presencial")

        new_appt = Appointment(
            patient_id=new_patient.id,
            doctor_id=doc_id,
            date=today,
            start_time=now_time,
            end_time=end_time_val,
            reason=reason_val,
            notes=f"Llegada presencial registrada en recepción por {current_user.name}",
            service_id=service_id if service_id and service_id > 0 else None,
            price=price,
            status="En Espera",
            queue_number=next_q
        )
        db.add(new_appt)
        db.commit()
        db.refresh(new_appt)

        if payment_action == "charge_now":
            return RedirectResponse(
                url=f"/payments/create?patient_id={new_patient.id}&appointment_id={new_appt.id}{('&service_id=' + str(service_id)) if service_id else ''}",
                status_code=303
            )
        elif payment_action == "pay_later":
            pay_amt = price if price and price > 0 else 1500.0
            rec_no = generate_receipt_number()
            new_pay = Payment(
                patient_id=new_patient.id,
                appointment_id=new_appt.id,
                service_id=service_id if service_id and service_id > 0 else None,
                service_name=svc.name if svc else "Consulta Médica General",
                insurance_name=new_patient.insurance_name or "Privado / Particular",
                amount=pay_amt,
                discount=0.0,
                total=pay_amt,
                status="pending",
                payment_method="cash",
                receipt_number=rec_no,
                notes=f"Saldo por cobrar en recepción (Pagar después) por {current_user.name}",
                created_by_id=current_user.id
            )
            db.add(new_pay)
            db.commit()
            return RedirectResponse(url="/appointments?status=En+Espera&waiting_success=1", status_code=303)
        else:
            return RedirectResponse(url="/appointments?status=En+Espera&waiting_success=1", status_code=303)

    elif schedule_action == "scheduled":
        target_date = date.today() + timedelta(days=1)
        if appt_date:
            try:
                target_date = datetime.strptime(appt_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        start_time_val = time(9, 0)
        if appt_time:
            try:
                start_time_val = datetime.strptime(appt_time, "%H:%M").time()
            except ValueError:
                pass

        end_time_val = (datetime.combine(target_date, start_time_val) + timedelta(minutes=30)).time()

        doctor = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        doc_id = current_user.id if current_user.role == "doctor" else (doctor.id if doctor else 1)

        price = 0.0
        svc = None
        if service_id and service_id > 0:
            svc = db.query(Service).filter(Service.id == service_id).first()
            if svc:
                price = float(svc.price or 0.0)

        reason_val = appt_reason or (svc.name if svc else "Consulta Médica Programada")

        new_appt = Appointment(
            patient_id=new_patient.id,
            doctor_id=doc_id,
            date=target_date,
            start_time=start_time_val,
            end_time=end_time_val,
            reason=reason_val,
            notes=f"Cita programada registrada por {current_user.name}",
            service_id=service_id if service_id and service_id > 0 else None,
            price=price,
            status="Pendiente"
        )
        db.add(new_appt)
        db.commit()
        db.refresh(new_appt)

        if payment_action == "charge_now":
            return RedirectResponse(
                url=f"/payments/create?patient_id={new_patient.id}&appointment_id={new_appt.id}{('&service_id=' + str(service_id)) if service_id else ''}",
                status_code=303
            )
        elif payment_action == "pay_later":
            pay_amt = price if price and price > 0 else 1500.0
            rec_no = generate_receipt_number()
            new_pay = Payment(
                patient_id=new_patient.id,
                appointment_id=new_appt.id,
                service_id=service_id if service_id and service_id > 0 else None,
                service_name=svc.name if svc else "Consulta Médica General",
                insurance_name=new_patient.insurance_name or "Privado / Particular",
                amount=pay_amt,
                discount=0.0,
                total=pay_amt,
                status="pending",
                payment_method="cash",
                receipt_number=rec_no,
                notes=f"Saldo por cobrar de cita programada (Pagar después) por {current_user.name}",
                created_by_id=current_user.id
            )
            db.add(new_pay)
            db.commit()
            return RedirectResponse(url=f"/appointments?date={target_date.strftime('%Y-%m-%d')}&scheduled=1", status_code=303)
        else:
            return RedirectResponse(url=f"/appointments?date={target_date.strftime('%Y-%m-%d')}&scheduled=1", status_code=303)

    return RedirectResponse(url=f"/patients/{new_patient.id}?new_patient=1", status_code=303)

@router.get("/{patient_id}")
def view_patient(
    request: Request,
    patient_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    appointments = db.query(Appointment).filter(Appointment.patient_id == patient_id).order_by(Appointment.date.desc()).all()
    consultations = db.query(Consultation).filter(Consultation.patient_id == patient_id).order_by(Consultation.created_at.desc()).all()
    payments = db.query(Payment).filter(Payment.patient_id == patient_id).order_by(Payment.created_at.desc()).all()
    vitals = db.query(VitalSign).filter(VitalSign.patient_id == patient_id).order_by(VitalSign.recorded_at.asc()).all()
    audit_logs = AuditService.get_logs_for_patient(db, patient_id, limit=25)

    # F8: Series de evolución de signos vitales para gráficas
    vitals_evolution = {
        "dates": [v.recorded_at.strftime("%d/%m") for v in vitals],
        "systolic": [v.systolic_bp for v in vitals if v.systolic_bp is not None],
        "diastolic": [v.diastolic_bp for v in vitals if v.diastolic_bp is not None],
        "glucose": [v.glucose_mg_dl for v in vitals if v.glucose_mg_dl is not None],
        "weight": [v.weight_kg for v in vitals if v.weight_kg is not None],
        "bmi": [v.bmi for v in vitals if v.bmi is not None],
        "heart_rate": [v.heart_rate for v in vitals if v.heart_rate is not None],
    }

    # F8: Cálculo de deuda pendiente
    pending_payments = [p for p in payments if p.status == "pending"]
    balance_due = sum(p.total for p in pending_payments)

    # Paciente en sala de espera hoy
    today = date.today()
    active_waiting_appointment = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.date == today,
        Appointment.status == "En Espera"
    ).first()

    # Buscar la última consulta que tenga receta médica emitida
    latest_prescription = next((c for c in consultations if c.prescription and c.prescription.strip()), None)

    return templates.TemplateResponse(
        request=request,
        name="patients/view.html",
        context={
            "user": current_user,
            "patient": patient,
            "appointments": appointments,
            "consultations": consultations,
            "latest_prescription": latest_prescription,
            "payments": payments,
            "vitals": list(reversed(vitals)),
            "vitals_evolution": vitals_evolution,
            "audit_logs": audit_logs,
            "balance_due": balance_due,
            "active_waiting_appointment": active_waiting_appointment,
            "waiting_success": request.query_params.get("waiting_success"),
        }
    )

@router.get("/{patient_id}/edit")
def edit_patient_form(
    request: Request,
    patient_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    return templates.TemplateResponse(
        request=request,
        name="patients/edit.html",
        context={
            "user": current_user,
            "patient": patient,
        }
    )

@router.post("/{patient_id}/edit")
def edit_patient(
    request: Request,
    patient_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    document_id: str = Form(None),
    date_of_birth: str = Form(None),
    gender: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    blood_type: str = Form(None),
    allergies: str = Form(None),
    emergency_contact_name: str = Form(None),
    emergency_contact_phone: str = Form(None),
    insurance_name: str = Form("Privado / Particular"),
    insurance_number: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    dob = None
    if date_of_birth:
        try:
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        except ValueError:
            dob = None

    old_data = {
        "name": f"{patient.first_name} {patient.last_name}",
        "phone": patient.phone,
        "allergies": patient.allergies,
        "address": patient.address,
        "insurance_name": patient.insurance_name,
        "insurance_number": patient.insurance_number
    }

    patient.first_name = first_name
    patient.last_name = last_name
    patient.document_id = document_id
    patient.date_of_birth = dob
    patient.gender = gender
    patient.phone = phone
    patient.email = email
    patient.address = address
    patient.blood_type = blood_type
    patient.allergies = allergies
    patient.emergency_contact_name = emergency_contact_name
    patient.emergency_contact_phone = emergency_contact_phone
    patient.insurance_name = insurance_name or "Privado / Particular"
    patient.insurance_number = insurance_number
    patient.updated_at = datetime.utcnow()

    db.commit()

    # Registrar en bitácora de auditoría médica (F13)
    AuditService.log_change(
        db=db,
        entity_type="patient",
        entity_id=patient.id,
        action="update",
        summary=f"Actualización de datos demográficos y de contacto de {patient.first_name} {patient.last_name}",
        patient_id=patient.id,
        user_id=current_user.id if current_user else 1,
        old_data=old_data,
        new_data={"name": f"{first_name} {last_name}", "phone": phone, "allergies": allergies, "address": address}
    )

    return RedirectResponse(url=f"/patients/{patient_id}", status_code=303)


@router.post("/{patient_id}/archive")
def archive_patient(
    request: Request,
    patient_id: int,
    reason: str = Form("Archivado por usuario"),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Oculta / Archiva un paciente (Soft Delete).
    Disponible para personal autorizado (Médico, Secretaria, Admin).
    """
    if not (current_user.has_permission('patients') or getattr(current_user, 'role', '') == 'admin'):
        raise HTTPException(status_code=403, detail="No tiene permisos para archivar pacientes.")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    clean_reason = reason.strip() if reason and reason.strip() else "Archivado sin motivo especificado"
    patient.is_active = False
    patient.archived_at = datetime.utcnow()
    patient.archived_reason = clean_reason
    patient.archived_by_id = current_user.id
    db.commit()

    AuditService.log_change(
        db=db,
        entity_type="patient",
        entity_id=patient.id,
        action="archive",
        summary=f"Expediente de {patient.first_name} {patient.last_name} archivado/ocultado. Motivo: {clean_reason}",
        patient_id=patient.id,
        user_id=current_user.id,
        new_data={"reason": clean_reason}
    )

    return RedirectResponse(url=f"/patients/{patient.id}?archived=1", status_code=303)


@router.post("/{patient_id}/restore")
def restore_patient(
    request: Request,
    patient_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Restaura un paciente archivado al estado activo.
    Exclusivo para el Administrador.
    """
    if getattr(current_user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido: Solo un Administrador puede restaurar expedientes archivados.")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    prev_reason = patient.archived_reason
    patient.is_active = True
    patient.archived_at = None
    patient.archived_reason = None
    patient.archived_by_id = None
    db.commit()

    AuditService.log_change(
        db=db,
        entity_type="patient",
        entity_id=patient.id,
        action="restore",
        summary=f"Expediente de {patient.first_name} {patient.last_name} restaurado al estado activo por el Administrador",
        patient_id=patient.id,
        user_id=current_user.id,
        old_data={"archived_reason": prev_reason}
    )

    return RedirectResponse(url=f"/patients/{patient.id}?restored=1", status_code=303)


@router.post("/{patient_id}/permanent-delete")
def permanent_delete_patient(
    request: Request,
    patient_id: int,
    confirm_text: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Elimina físicamente un paciente y sus registros dependientes en cascada.
    Exclusivo para el Administrador con confirmación explícita.
    """
    if getattr(current_user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido: Solo un Administrador puede eliminar permanentemente expedientes.")

    if confirm_text.strip().upper() != "ELIMINAR":
        raise HTTPException(status_code=400, detail="Debe escribir exactamente 'ELIMINAR' para confirmar la eliminación permanente.")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    from app.models.medical_license import MedicalLicense
    from app.models.medical_reference import MedicalReference
    from app.models.audit_log import ClinicalAuditLog

    # Eliminación en cascada segura de tablas dependientes
    db.query(Appointment).filter(Appointment.patient_id == patient_id).delete(synchronize_session=False)
    db.query(Consultation).filter(Consultation.patient_id == patient_id).delete(synchronize_session=False)
    db.query(Payment).filter(Payment.patient_id == patient_id).delete(synchronize_session=False)
    db.query(VitalSign).filter(VitalSign.patient_id == patient_id).delete(synchronize_session=False)
    db.query(MedicalLicense).filter(MedicalLicense.patient_id == patient_id).delete(synchronize_session=False)
    db.query(MedicalReference).filter(MedicalReference.patient_id == patient_id).delete(synchronize_session=False)
    db.query(ClinicalAuditLog).filter(ClinicalAuditLog.patient_id == patient_id).delete(synchronize_session=False)

    db.delete(patient)
    db.commit()

    return RedirectResponse(url="/patients?status=archived&deleted=1", status_code=303)
