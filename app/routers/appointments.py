from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, case
from pathlib import Path
from datetime import datetime, date, time, timedelta
from typing import Optional

from app.database import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.user import User
from app.models.service import Service
from app.models.payment import Payment
from app.core.deps import require_current_user, require_permission
from app.core.templates import templates
from app.services.whatsapp_service import WhatsAppService
from app.services.whatsapp_gateway import gateway_manager
from app.services.ars_service import get_all_ars
from app.routers.payments import generate_receipt_number

router = APIRouter(prefix="/appointments", tags=["appointments"])

INACTIVE_APPT_STATUSES = [
    "Cancelada", "cancelada", "Canceled", "canceled",
    "Cancelled", "cancelled", "No Asistió", "no_show"
]

def find_same_day_appointment(
    db: Session,
    patient_id: int,
    target_date: date,
    exclude_appt_id: Optional[int] = None
) -> Optional[Appointment]:
    """Devuelve una cita activa existente del paciente en target_date, ignorando citas canceladas."""
    q = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.date == target_date,
        or_(Appointment.status == None, Appointment.status.notin_(INACTIVE_APPT_STATUSES))
    )
    if exclude_appt_id is not None:
        q = q.filter(Appointment.id != exclude_appt_id)
    return q.first()

def remove_appointment_from_queue(db: Session, appt: Appointment, mode: str = "cancel") -> str:
    """
    Saca a un paciente de la sala de espera / fila.
    - mode='unqueue': regresa la cita a 'Pendiente' y limpia su queue_number.
    - mode='cancel': marca la cita como 'Cancelada', limpia queue_number y elimina cobros 'pending' sin pagar.
    """
    appt.queue_number = None
    appt.updated_at = datetime.utcnow()
    if mode == "unqueue":
        appt.status = "Pendiente"
        msg = "Paciente retirado de la sala de espera (cita conservada como Pendiente)."
    else:
        appt.status = "Cancelada"
        pending_pays = db.query(Payment).filter(
            Payment.appointment_id == appt.id,
            Payment.status == "pending"
        ).all()
        for py in pending_pays:
            db.delete(py)
        msg = "Cita anulada y paciente retirado de la sala de espera."
    db.commit()
    return msg

def assign_next_queue_number(db: Session, target_date: date) -> int:
    """Calcula y asigna el siguiente número correlativo de turno para la fecha dada."""
    max_q = db.query(func.max(Appointment.queue_number)).filter(Appointment.date == target_date).scalar() or 0
    return int(max_q) + 1

@router.get("/waiting-count")
def get_waiting_count(db: Session = Depends(get_db)):
    """Devuelve la cantidad de pacientes actualmente en sala de espera hoy."""
    today = date.today()
    count = db.query(Appointment).filter(
        Appointment.date == today,
        Appointment.status.in_(["En Espera", "En espera", "en espera"])
    ).count()
    return {"count": count, "date": today.isoformat()}

@router.get("/")
def list_appointments(
    request: Request,
    view: str = Query("list", pattern="^(list|calendar)$"),
    filter_date: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    from app.routers.patients import resolve_current_doctor_id
    from app.models.setting import Setting
    doc_id = resolve_current_doctor_id(db, current_user)

    # Auto-reconciliación: Si un paciente ya tuvo consulta médica asociada o del día, marcar la cita como Completada
    try:
        from app.services.appointment_reconciliation import reconcile_completed_appointments
        if reconcile_completed_appointments(db) > 0:
            db.commit()
            try:
                from app.services.supabase_sync_service import signal_supabase_sync
                signal_supabase_sync()
            except Exception:
                pass
    except Exception:
        pass

    if status in ["all", "Completada", "Cancelada"]:
        query = db.query(Appointment).order_by(Appointment.date.desc(), Appointment.start_time.desc(), Appointment.id.desc())
    else:
        query = db.query(Appointment).order_by(Appointment.date.asc(), Appointment.start_time.asc())
    if doc_id:
        query = query.filter(or_(Appointment.doctor_id == doc_id, Appointment.doctor_id == None))
    
    if filter_date:
        try:
            d = datetime.strptime(filter_date, "%Y-%m-%d").date()
            query = query.filter(Appointment.date == d)
        except ValueError:
            pass

    if status and status not in ["all", "pendientes"]:
        query = query.filter(Appointment.status == status)
    elif status == "all":
        pass  # Histórico completo solicitado explícitamente
    else:
        # Por defecto (Citas Pendientes): únicamente mostrar citas pendientes, confirmadas o en espera (NO completadas)
        query = query.filter(Appointment.status.in_(["Pendiente", "Confirmada", "En Espera"]))

    total_appointments = query.count()
    total_pages = max(1, (total_appointments + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    appointments = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Pre-organizar citas por fecha para el calendario y recopilar datos WhatsApp (sin N+1 sobre Setting)
    calendar_events = []
    whatsapp_info = {}
    unsent_reminders_count = 0
    cached_setting = db.query(Setting).first()
    gateway_status = gateway_manager.get_status()

    for a in appointments:
        p_name = f"{a.patient.first_name} {a.patient.last_name}" if a.patient else "Paciente no registrado"
        time_display = f"{a.start_time.strftime('%H:%M')} - " if a.start_time else ""
        calendar_events.append({
            "id": a.id,
            "title": f"{time_display}{p_name} ({a.reason or 'Sin motivo'})",
            "start": f"{a.date}T{a.start_time}" if a.start_time else f"{a.date}",
            "end": f"{a.date}T{a.end_time}" if a.end_time else None,
            "status": a.status,
            "patient_name": p_name,
        })
        
        # Información de WhatsApp para 1-clic
        w_data = WhatsAppService.get_appointment_reminder(
            db, a, setting=cached_setting, gateway_status=gateway_status
        )
        whatsapp_info[a.id] = w_data
        if not a.whatsapp_reminder_sent and a.status in ["Pendiente", "Confirmada"]:
            unsent_reminders_count += 1

    tomorrow_date = date.today() + timedelta(days=1)
    tomorrow_q = db.query(Appointment).filter(
        Appointment.date == tomorrow_date,
        Appointment.status.in_(["Pendiente", "Confirmada"]),
        or_(Appointment.whatsapp_reminder_sent == False, Appointment.whatsapp_reminder_sent == None),
    )
    if doc_id:
        tomorrow_q = tomorrow_q.filter(or_(Appointment.doctor_id == doc_id, Appointment.doctor_id == None))
    tomorrow_unsent_count = tomorrow_q.count()

    today_str = date.today().strftime("%Y-%m-%d")
    pat_q = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None))
    if doc_id:
        pat_q = pat_q.filter(Patient.doctor_id == doc_id)
    all_patients = pat_q.order_by(Patient.last_name).limit(300).all()

    wait_q = db.query(Appointment).filter(
        Appointment.date == date.today(),
        Appointment.status == "En Espera"
    )
    if doc_id:
        wait_q = wait_q.filter(Appointment.doctor_id == doc_id)
    waiting_count = wait_q.count()

    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category.asc(), Service.name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="appointments/index.html",
        context={
            "user": current_user,
            "appointments": appointments,
            "all_patients": all_patients,
            "services": services,
            "waiting_count": waiting_count,
            "waiting_success": request.query_params.get("waiting_success"),
            "view_mode": view,
            "calendar_events": calendar_events,
            "today_str": today_str,
            "tomorrow_str": tomorrow_date.strftime("%Y-%m-%d"),
            "filter_date": filter_date or "",
            "status_filter": status or "pendientes",
            "whatsapp_info": whatsapp_info,
            "unsent_reminders_count": unsent_reminders_count,
            "tomorrow_unsent_count": tomorrow_unsent_count,
            "gateway_status": gateway_status,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_appointments": total_appointments,
        }
    )

@router.get("/create")
def create_appointment_form(
    request: Request,
    patient_id: int = Query(None),
    suggested_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patients = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).order_by(Patient.last_name).all()
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category.asc(), Service.name.asc()).all()
    today = date.today()
    
    # Atajos de fecha para F1
    quick_dates = {
        "today": today.strftime("%Y-%m-%d"),
        "plus_7": (today + timedelta(days=7)).strftime("%Y-%m-%d"),
        "plus_15": (today + timedelta(days=15)).strftime("%Y-%m-%d"),
        "plus_30": (today + timedelta(days=30)).strftime("%Y-%m-%d"),
    }

    initial_date = suggested_date if suggested_date else quick_dates["today"]

    return templates.TemplateResponse(
        request=request,
        name="appointments/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "services": services,
            "selected_patient_id": patient_id,
            "quick_dates": quick_dates,
            "initial_date": initial_date,
        }
    )

@router.post("/create")
def create_appointment(
    request: Request,
    patient_id: int = Form(...),
    date_str: str = Form(..., alias="date"),
    start_time_str: str = Form(..., alias="start_time"),
    end_time_str: str = Form(..., alias="end_time"),
    reason: str = Form(...),
    notes: str = Form(None),
    service_id: int = Form(None),
    price: float = Form(None),
    is_recurring: bool = Form(False),
    recurrence_count: int = Form(1), # Número de ocurrencias para F14
    recurrence_interval_days: int = Form(30), # Intervalo en días (30 = mensual)
    payment_action: Optional[str] = Form("none"), # 'charge_now', 'pay_later', 'none'
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    start_time_obj = datetime.strptime(start_time_str, "%H:%M").time()
    end_time_obj = datetime.strptime(end_time_str, "%H:%M").time()

    # Si se seleccionó servicio y no se definió precio explícito, tomar el precio del servicio
    if service_id and (price is None or price <= 0):
        svc = db.query(Service).filter(Service.id == service_id).first()
        if svc:
            price = svc.price

    # Determinar médico responsable
    if current_user.role == "doctor":
        doc_id = current_user.id
    else:
        active_doc = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        doc_id = active_doc.id if active_doc else current_user.id
    
    # Determinar cuántas citas crear (F14: citas recurrentes)
    count = max(1, min(12, recurrence_count if is_recurring else 1))

    # Filtro anti-duplicidad: verificar antes de crear que ninguna de las fechas tenga ya una cita activa
    for i in range(count):
        check_date = base_date + timedelta(days=i * recurrence_interval_days)
        existing_same_day = find_same_day_appointment(db, patient_id, check_date)
        if existing_same_day:
            pat_obj = db.query(Patient).filter(Patient.id == patient_id).first()
            pat_name = f"{pat_obj.first_name} {pat_obj.last_name}" if pat_obj else "Este paciente"
            time_disp = existing_same_day.start_time.strftime("%I:%M %p") if existing_same_day.start_time else ""
            err_text = (
                f"⚠️ {pat_name} ya tiene una cita activa para el día {check_date.strftime('%d/%m/%Y')} "
                f"{('a las ' + time_disp + ' ') if time_disp else ''}(Estado: {existing_same_day.status}). "
                f"No se permite crear citas duplicadas el mismo día."
            )
            patients_list = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).order_by(Patient.last_name).all()
            services_list = db.query(Service).filter(Service.is_active == True).order_by(Service.name.asc()).all()
            today_d = date.today()
            quick_dates = {
                "today": today_d.strftime("%Y-%m-%d"),
                "plus_7": (today_d + timedelta(days=7)).strftime("%Y-%m-%d"),
                "plus_15": (today_d + timedelta(days=15)).strftime("%Y-%m-%d"),
                "plus_30": (today_d + timedelta(days=30)).strftime("%Y-%m-%d"),
            }
            return templates.TemplateResponse(
                request=request,
                name="appointments/create.html",
                context={
                    "user": current_user,
                    "patients": patients_list,
                    "services": services_list,
                    "selected_patient_id": patient_id,
                    "quick_dates": quick_dates,
                    "initial_date": date_str,
                    "error_msg": err_text,
                },
                status_code=400,
            )

    created_appts = []
    
    for i in range(count):
        current_appt_date = base_date + timedelta(days=i * recurrence_interval_days)
        reason_label = reason if i == 0 else f"{reason} (Control recurrente #{i+1})"
        
        # Si la primera cita es para hoy mismo, ponerla en espera y asignar turno correlativo
        if i == 0 and current_appt_date == date.today():
            appt_status = "En Espera"
            queue_num = assign_next_queue_number(db, current_appt_date)
        else:
            appt_status = "Pendiente"
            queue_num = None

        new_appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doc_id,
            date=current_appt_date,
            start_time=start_time_obj,
            end_time=end_time_obj,
            reason=reason_label,
            notes=notes,
            service_id=service_id if service_id and service_id > 0 else None,
            price=price,
            is_recurring=is_recurring,
            status=appt_status,
            queue_number=queue_num
        )
        db.add(new_appointment)
        created_appts.append(new_appointment)

    db.commit()

    first_appt = created_appts[0] if created_appts else None

    # Acciones de facturación integradas
    if payment_action == "charge_now" and first_appt:
        svc_param = f"&service_id={service_id}" if service_id and service_id > 0 else ""
        return RedirectResponse(
            url=f"/payments/create?patient_id={patient_id}&appointment_id={first_appt.id}{svc_param}",
            status_code=303
        )
    elif payment_action == "pay_later" and first_appt:
        final_price = float(price) if (price and price > 0) else 0.0
        pending_payment = Payment(
            receipt_number=generate_receipt_number(),
            patient_id=patient_id,
            appointment_id=first_appt.id,
            service_id=service_id if service_id and service_id > 0 else None,
            amount=final_price,
            total=final_price,
            payment_method="Pendiente",
            status="pending",
            notes=f"Cuenta por cobrar generada al agendar cita #{first_appt.id}",
            created_by_id=current_user.id
        )
        db.add(pending_payment)
        db.commit()
        return RedirectResponse(url=f"/appointments?msg=created_pay_later", status_code=303)

    return RedirectResponse(url="/appointments", status_code=303)

@router.get("/check-duplicate")
def check_duplicate_same_day(
    patient_id: int = Query(...),
    target_date: str = Query(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Comprueba en vivo si el paciente ya tiene una cita activa en la fecha solicitada."""
    try:
        d = datetime.strptime(target_date.strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return {"has_duplicate": False}

    existing = find_same_day_appointment(db, patient_id, d)
    if existing:
        time_disp = existing.start_time.strftime("%I:%M %p") if existing.start_time else ""
        return {
            "has_duplicate": True,
            "appointment_id": existing.id,
            "date": d.strftime("%d/%m/%Y"),
            "time": time_disp,
            "status": existing.status,
            "message": f"Este paciente ya tiene una cita activa el {d.strftime('%d/%m/%Y')}{' a las ' + time_disp if time_disp else ''} ({existing.status})."
        }
    return {"has_duplicate": False}

@router.post("/{appointment_id}/status")
def update_appointment_status(
    appointment_id: int,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appt:
        if new_status in ("Completada", "Atendida") and not current_user.has_permission("consultations"):
            raise HTTPException(
                status_code=403,
                detail="Solo el médico tratante puede completar o cerrar una consulta clínica."
            )
        if appt.status in ("En Espera", "En Consulta") and new_status in ("Confirmada", "Pendiente"):
            return RedirectResponse(url="/appointments?error=in_queue", status_code=303)
        # Al marcar como En Espera (llegada del paciente), asignar Turno correlativo diario si aún no tiene
        if new_status == "En Espera" and not appt.queue_number:
            appt.queue_number = assign_next_queue_number(db, appt.date)
        elif new_status in ["Pendiente", "Cancelada", "cancelled", "canceled"]:
            appt.queue_number = None
        appt.status = new_status
        appt.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/appointments", status_code=303)

@router.post("/{appointment_id}/remove-from-queue")
def desktop_remove_from_queue(
    appointment_id: int,
    request: Request,
    mode: str = Form("cancel"),
    redirect_to: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Permite sacar a un paciente de la fila/sala de espera (volver a Pendiente o anular cita por error)."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    msg = remove_appointment_from_queue(db, appt, mode=mode)

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return {"success": True, "appointment_id": appt.id, "status": appt.status, "message": msg}

    from urllib.parse import urlparse
    parsed = urlparse(redirect_to or "")
    dest = (
        redirect_to
        if (
            redirect_to
            and redirect_to.startswith("/")
            and not redirect_to.startswith("//")
            and not parsed.netloc
            and "\\" not in redirect_to
        )
        else "/appointments"
    )
    return RedirectResponse(url=dest, status_code=303)

@router.post("/{appointment_id}/check-in")
def check_in_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Marca la llegada del paciente a la sala de espera y le asigna su Turno del día."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    appt.status = "En Espera"
    if not appt.queue_number:
        appt.queue_number = assign_next_queue_number(db, appt.date)
    appt.updated_at = datetime.utcnow()
    db.commit()

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return {"success": True, "queue_number": appt.queue_number, "status": appt.status}

    return RedirectResponse(url="/appointments?status=En+Espera&waiting_success=1", status_code=303)

@router.post("/check-in-walkin")
def check_in_walkin(
    request: Request,
    patient_id: int = Form(...),
    service_id: Optional[int] = Form(None),
    notes: str = Form(None),
    redirect_to: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    today = date.today()
    now_time = datetime.now().time()
    resolved_price = 0.0
    resolved_reason = "Llegada espontánea (Sin cita previa) - En Espera"
    if service_id:
        svc = db.query(Service).filter(Service.id == service_id).first()
        if svc:
            resolved_price = float(svc.price or 0.0)
            resolved_reason = svc.name or resolved_reason

    # Verificar si el paciente ya tiene cita hoy en estado Pendiente, Confirmada o En Espera
    existing = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.date == today,
        Appointment.status.in_(["Pendiente", "Confirmada", "En Espera"])
    ).first()
    
    if existing:
        existing.status = "En Espera"
        if not existing.queue_number:
            existing.queue_number = assign_next_queue_number(db, today)
        if service_id and not existing.service_id:
            existing.service_id = service_id
            existing.price = resolved_price
        if notes:
            existing.notes = f"{existing.notes} | {notes}" if existing.notes else notes
        existing.updated_at = datetime.utcnow()
        db.commit()
        appt = existing
    else:
        # Crear cita espontánea / walk-in directa para hoy con su Turno correlativo
        end_time_val = (datetime.now() + timedelta(minutes=30)).time()
        next_q = assign_next_queue_number(db, today)
        from app.routers.patients import resolve_current_doctor_id
        doc_id = resolve_current_doctor_id(db, current_user) or 1
        appt = Appointment(
            patient_id=patient_id,
            doctor_id=doc_id,
            date=today,
            start_time=now_time,
            end_time=end_time_val,
            service_id=service_id,
            price=resolved_price,
            reason=resolved_reason,
            notes=notes or "Paciente en sala de espera indicado por recepción",
            status="En Espera",
            queue_number=next_q
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)

    if redirect_to == "patient":
        return RedirectResponse(url=f"/patients/{patient_id}?waiting_success=1", status_code=303)
    elif redirect_to == "dashboard":
        return RedirectResponse(url="/dashboard?waiting_success=1", status_code=303)
    return RedirectResponse(url="/appointments?status=En+Espera&waiting_success=1", status_code=303)

@router.post("/attend-now")
def attend_now(
    request: Request,
    patient_id: int = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('consultations'))
):
    # Solo médicos pueden ingresar directamente a consulta
    today = date.today()
    now_time = datetime.now().time()
    
    # Si ya existe una cita hoy, asociarla para completarla luego
    existing = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.date == today,
        Appointment.status.in_(["En Espera", "Pendiente", "Confirmada"])
    ).first()
    
    if existing:
        existing.status = "En Espera"
        if not existing.queue_number:
            existing.queue_number = assign_next_queue_number(db, today)
        existing.updated_at = datetime.utcnow()
        db.commit()
        appt_id = existing.id
    else:
        end_time_val = (datetime.now() + timedelta(minutes=30)).time()
        next_q = assign_next_queue_number(db, today)
        appt = Appointment(
            patient_id=patient_id,
            doctor_id=current_user.id,
            date=today,
            start_time=now_time,
            end_time=end_time_val,
            reason="Atención Inmediata (Sin cita previa)",
            notes=notes or "Paciente entra de inmediato a consulta médica",
            status="En Espera",
            queue_number=next_q
        )
        db.add(appt)
        db.commit()
        db.refresh(appt)
        appt_id = appt.id

    return RedirectResponse(url=f"/consultations/create?patient_id={patient_id}&appointment_id={appt_id}&walk_in=1", status_code=303)


@router.get("/patient-consultations/{patient_id}")
def get_patient_recent_consultations(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('consultations'))
):
    """Retorna las últimas 5 consultas de un paciente para vista previa rápida en citas."""
    from app.models.consultation import Consultation
    from app.models.patient import Patient
    from app.routers.patients import resolve_current_doctor_id
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    doc_id = resolve_current_doctor_id(db, current_user)
    q = db.query(Consultation).filter(Consultation.patient_id == patient_id)
    if doc_id:
        q = q.filter((Consultation.doctor_id == doc_id) | (Consultation.doctor_id.is_(None)))
    consultations = q.order_by(Consultation.created_at.desc(), Consultation.id.desc()).limit(5).all()

    items = []
    for c in consultations:
        doc_name = c.doctor.name if c.doctor else "Doctor"
        date_str = c.created_at.strftime("%d/%m/%Y %H:%M") if c.created_at else "—"
        items.append({
            "id": c.id,
            "date": date_str,
            "doctor": doc_name,
            "reason": c.reason or "Sin motivo especificado",
            "diagnosis": c.diagnosis or "Sin diagnóstico",
            "clinical_history": (c.display_clinical_history or "")[:280] + ("..." if len(c.display_clinical_history or "") > 280 else ""),
            "treatment": c.treatment or "",
            "prescription": c.prescription or ""
        })

    return {
        "patient": {
            "id": patient.id,
            "name": f"{patient.first_name} {patient.last_name}",
            "document_id": patient.document_id or "Sin documento",
            "phone": patient.phone or "Sin teléfono"
        },
        "consultations": items
    }


@router.get("/secretary-daily-pdf")
def redirect_secretary_daily_pdf(report_date: str = Query(None)):
    """Acceso directo para secretaría al reporte diario en PDF."""
    url = "/reports/export/secretary-daily-pdf"
    if report_date:
        url += f"?report_date={report_date}"
    return RedirectResponse(url=url, status_code=303)


# ---------------------------------------------------------
# ENDPOINTS DE INTEGRACIÓN DE WHATSAPP (1-CLIC REAL + COLA)
# ---------------------------------------------------------

def _notify_supabase_sync() -> None:
    try:
        from app.services.supabase_sync_service import signal_supabase_sync
        signal_supabase_sync()
    except Exception:
        pass


def _get_scoped_appointment(db: Session, appointment_id: int, current_user) -> Appointment:
    from app.routers.patients import resolve_current_doctor_id

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    doc_id = resolve_current_doctor_id(db, current_user)
    if doc_id and appt.doctor_id is not None and appt.doctor_id != doc_id:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    return appt


def _parse_queue_target_date(target_date: Optional[str]) -> date:
    if target_date:
        try:
            return datetime.strptime(target_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today() + timedelta(days=1)


def _build_daily_whatsapp_queue(
    db: Session,
    current_user,
    target_date: Optional[str] = None,
    include_sent: bool = True,
) -> dict:
    from app.routers.patients import resolve_current_doctor_id

    target = _parse_queue_target_date(target_date)
    doc_id = resolve_current_doctor_id(db, current_user)

    query = db.query(Appointment).filter(
        Appointment.date == target,
        Appointment.status.in_(["Pendiente", "Confirmada"]),
    )
    if doc_id:
        query = query.filter(or_(Appointment.doctor_id == doc_id, Appointment.doctor_id == None))
    if not include_sent:
        query = query.filter(
            or_(Appointment.whatsapp_reminder_sent == False, Appointment.whatsapp_reminder_sent == None)
        )

    appts = query.order_by(Appointment.start_time.asc(), Appointment.id.asc()).all()

    items = []
    ready_count = 0
    invalid_phone_count = 0
    sent_count = 0
    pending_count = 0

    for a in appts:
        info = WhatsAppService.get_appointment_reminder(db, a)
        valid_phone = bool(info["valid_phone"])
        already_sent = bool(info["already_sent"])

        if valid_phone:
            ready_count += 1
        else:
            invalid_phone_count += 1

        if already_sent:
            sent_count += 1
        else:
            pending_count += 1

        items.append({
            "id": a.id,
            "patient_name": info["patient_name"],
            "raw_phone": info["raw_phone"],
            "clean_phone": info["clean_phone"],
            "valid_phone": valid_phone,
            "time": a.start_time.strftime("%I:%M %p") if a.start_time else "Por definir",
            "date": a.date.strftime("%d/%m/%Y") if a.date else "",
            "status": a.status or "Pendiente",
            "message": info["message"],
            "wa_link": info["wa_link"],
            "already_sent": already_sent,
            "sent_at": info["sent_at"],
        })

    return {
        "success": True,
        "mode": "wa_link",
        "target_date": target.strftime("%Y-%m-%d"),
        "target_date_display": target.strftime("%d/%m/%Y"),
        "total": len(items),
        "ready_count": ready_count,
        "invalid_phone_count": invalid_phone_count,
        "sent_count": sent_count,
        "pending_count": pending_count,
        "items": items,
    }


@router.get("/whatsapp/daily-queue")
def get_daily_whatsapp_queue(
    target_date: Optional[str] = Query(None),
    include_sent: bool = Query(True),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments')),
):
    """
    Devuelve la Cola Interactiva diaria de recordatorios WhatsApp (solo lectura, nunca muta DB).
    """
    queue_data = _build_daily_whatsapp_queue(
        db=db,
        current_user=current_user,
        target_date=target_date,
        include_sent=include_sent,
    )
    return JSONResponse(content=queue_data)


@router.post("/whatsapp/send-all-daily-reminders")
def send_all_daily_reminders(
    target_date: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments')),
):
    """
    Devuelve la cola diaria sin marcar envíos automáticos falsos (Modo 1-Clic Real).
    """
    queue_data = _build_daily_whatsapp_queue(
        db=db,
        current_user=current_user,
        target_date=target_date,
        include_sent=False,
    )
    return JSONResponse(content={
        "success": True,
        "mode": "wa_link",
        "requires_manual_confirmation": True,
        "target_date": queue_data["target_date_display"],
        "target_date_iso": queue_data["target_date"],
        "total_eligible": queue_data["total"],
        "ready_count": queue_data["ready_count"],
        "invalid_phone_count": queue_data["invalid_phone_count"],
        "sent_count": 0,
        "skipped_count": queue_data["invalid_phone_count"],
        "items": queue_data["items"],
        "detail": "Usa la Cola Interactiva para abrir WhatsApp y confirmar cada envío real.",
    })


@router.get("/{appointment_id}/whatsapp-info")
def get_appointment_whatsapp_info(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """Devuelve el texto formateado, enlace wa.me y estado de la cita."""
    appt = _get_scoped_appointment(db, appointment_id, current_user)
    info = WhatsAppService.get_appointment_reminder(db, appt)
    return JSONResponse(content=info)


@router.post("/{appointment_id}/whatsapp-send")
def send_appointment_whatsapp(
    appointment_id: int,
    send_mode: str = Form("manual"),
    confirm_sent: bool = Form(False),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """
    Genera el enlace wa.me 1-Clic y marca 'whatsapp_reminder_sent = True' únicamente
    cuando 'confirm_sent' es True tras la confirmación del usuario.
    """
    appt = _get_scoped_appointment(db, appointment_id, current_user)
    info = WhatsAppService.get_appointment_reminder(db, appt)
    if not info["clean_phone"]:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "El paciente no tiene un número telefónico válido (mínimo 10 dígitos)."}
        )

    dispatch_res = WhatsAppService.dispatch_message(
        phone=info["clean_phone"],
        message=info["message"],
        force_manual=True,
    )
    if not dispatch_res.get("success"):
        return JSONResponse(status_code=400, content=dispatch_res)

    if confirm_sent:
        appt.whatsapp_reminder_sent = True
        appt.whatsapp_reminder_sent_at = datetime.utcnow()
        appt.updated_at = datetime.utcnow()
        db.commit()
        gateway_manager.record_confirmed_send()
        _notify_supabase_sync()

    return JSONResponse(content={
        "success": True,
        "mode": "wa_link",
        "wa_link": dispatch_res["wa_link"],
        "already_sent": bool(appt.whatsapp_reminder_sent),
        "sent_at": appt.whatsapp_reminder_sent_at.strftime("%d/%m/%Y %H:%M") if appt.whatsapp_reminder_sent_at else None,
        "patient_name": info["patient_name"],
        "detail": (
            "Recordatorio confirmado y registrado en agenda."
            if confirm_sent
            else "Enlace WhatsApp 1-Clic generado (pendiente de confirmación)."
        ),
    })


@router.get("/{appointment_id}/waiting-alert-wa")
def get_waiting_alert_wa(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """Genera el mensaje y enlace de WhatsApp para avisar al Dr. que el paciente llegó."""
    appt = _get_scoped_appointment(db, appointment_id, current_user)
    alert_info = WhatsAppService.get_waiting_alert(db, appt)
    return JSONResponse(content=alert_info)

@router.post("/close-day")
def close_day_appointments(
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """
    Cierre de jornada / Limpieza de sala de espera:
    Marca todas las citas en espera o pendientes de hoy y días anteriores como 'Completada',
    libera la sala para reiniciar turnos y sincroniza de inmediato a Supabase.
    """
    from app.routers.patients import resolve_current_doctor_id
    from app.services.appointment_reconciliation import compute_monotonic_sync_utc
    today = date.today()
    doc_id = resolve_current_doctor_id(db, current_user)
    q = db.query(Appointment).filter(
        Appointment.date <= today,
        Appointment.status.in_(["En Espera", "Pendiente", "Confirmada", "En Consulta", "en_consulta", "En espera", "en espera"])
    )
    if doc_id:
        q = q.filter((Appointment.doctor_id == doc_id) | (Appointment.doctor_id.is_(None)))
    pending_appts = q.all()

    sync_now = compute_monotonic_sync_utc(db)
    closed_count = 0
    for a in pending_appts:
        a.status = "Completada"
        a.queue_number = None
        a.updated_at = sync_now
        closed_count += 1

    db.commit()

    # Notificar inmediatamente al puente Supabase sin bloquear UI
    try:
        from app.services.supabase_sync_service import signal_supabase_sync
        signal_supabase_sync()
    except Exception:
        pass

    return JSONResponse(content={
        "success": True,
        "closed_count": closed_count,
        "message": f"Jornada cerrada correctamente. Se completaron {closed_count} turnos pendientes."
    })



