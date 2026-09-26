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

def assign_next_queue_number(db: Session, target_date: date) -> int:
    """Calcula y asigna el siguiente número correlativo de turno para la fecha dada."""
    max_q = db.query(func.max(Appointment.queue_number)).filter(Appointment.date == target_date).scalar() or 0
    return int(max_q) + 1

@router.get("/")
def list_appointments(
    request: Request,
    view: str = Query("list", pattern="^(list|calendar)$"),
    filter_date: str = Query(None),
    status: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(Appointment).order_by(Appointment.date.asc(), Appointment.start_time.asc())
    
    if filter_date:
        try:
            d = datetime.strptime(filter_date, "%Y-%m-%d").date()
            query = query.filter(Appointment.date == d)
        except ValueError:
            pass

    if status:
        query = query.filter(Appointment.status == status)

    appointments = query.all()
    
    # Pre-organizar citas por fecha para el calendario y recopilar datos WhatsApp
    calendar_events = []
    whatsapp_info = {}
    unsent_reminders_count = 0

    for a in appointments:
        p_name = f"{a.patient.first_name} {a.patient.last_name}" if a.patient else "Paciente no registrado"
        calendar_events.append({
            "id": a.id,
            "title": f"{a.start_time.strftime('%H:%M')} - {p_name} ({a.reason})",
            "start": f"{a.date}T{a.start_time}",
            "end": f"{a.date}T{a.end_time}",
            "status": a.status,
            "patient_name": p_name,
        })
        
        # Información de WhatsApp para 1-clic y Gateway
        w_data = WhatsAppService.get_appointment_reminder(db, a)
        whatsapp_info[a.id] = w_data
        if not a.whatsapp_reminder_sent and a.status in ["Pendiente", "Confirmada"]:
            unsent_reminders_count += 1

    today_str = date.today().strftime("%Y-%m-%d")
    all_patients = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).order_by(Patient.last_name).all()
    waiting_count = db.query(Appointment).filter(
        Appointment.date == date.today(),
        Appointment.status == "En Espera"
    ).count()

    gateway_status = gateway_manager.get_status()
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
            "filter_date": filter_date or "",
            "status_filter": status or "all",
            "whatsapp_info": whatsapp_info,
            "unsent_reminders_count": unsent_reminders_count,
            "gateway_status": gateway_status,
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
        pending_payment = Payment(
            receipt_number=generate_receipt_number(),
            patient_id=patient_id,
            appointment_id=first_appt.id,
            service_id=service_id if service_id and service_id > 0 else None,
            amount=price if (price and price > 0) else 0.0,
            payment_method="Pendiente",
            status="pending",
            notes=f"Cuenta por cobrar generada al agendar cita #{first_appt.id}",
            created_by_id=current_user.id
        )
        db.add(pending_payment)
        db.commit()
        return RedirectResponse(url=f"/appointments?msg=created_pay_later", status_code=303)

    return RedirectResponse(url="/appointments", status_code=303)

@router.post("/{appointment_id}/status")
def update_appointment_status(
    appointment_id: int,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appt:
        # Al marcar como En Espera (llegada del paciente), asignar Turno correlativo diario si aún no tiene
        if new_status == "En Espera" and not appt.queue_number:
            appt.queue_number = assign_next_queue_number(db, appt.date)
        appt.status = new_status
        appt.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/appointments", status_code=303)

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
    notes: str = Form(None),
    redirect_to: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    today = date.today()
    now_time = datetime.now().time()
    
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
        if notes:
            existing.notes = f"{existing.notes} | {notes}" if existing.notes else notes
        existing.updated_at = datetime.utcnow()
        db.commit()
        appt = existing
    else:
        # Crear cita espontánea / walk-in directa para hoy con su Turno correlativo
        end_time_val = (datetime.now() + timedelta(minutes=30)).time()
        next_q = assign_next_queue_number(db, today)
        appt = Appointment(
            patient_id=patient_id,
            doctor_id=current_user.id if current_user.role == "doctor" else 1,
            date=today,
            start_time=now_time,
            end_time=end_time_val,
            reason="Llegada espontánea (Sin cita previa) - En Espera",
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


@router.get("/secretary-daily-pdf")
def redirect_secretary_daily_pdf(report_date: str = Query(None)):
    """Acceso directo para secretaría al reporte diario en PDF."""
    url = "/reports/export/secretary-daily-pdf"
    if report_date:
        url += f"?report_date={report_date}"
    return RedirectResponse(url=url, status_code=303)


# ---------------------------------------------------------
# ENDPOINTS DE INTEGRACIÓN DE WHATSAPP (1-CLIC + GATEWAY)
# ---------------------------------------------------------

@router.get("/{appointment_id}/whatsapp-info")
def get_appointment_whatsapp_info(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """Devuelve el texto formateado, enlace wa.me y estado de la cita."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    info = WhatsAppService.get_appointment_reminder(db, appt)
    return JSONResponse(content=info)

@router.post("/{appointment_id}/whatsapp-send")
def send_appointment_whatsapp(
    appointment_id: int,
    send_mode: str = Form("auto"),  # auto (intenta gateway primero), manual (forzar wa.me)
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """
    Despacha el recordatorio de la cita por WhatsApp:
    - Si el gateway está conectado y send_mode == 'auto', lo envía desatendido.
    - Si no, devuelve el enlace wa.me para apertura de 1-clic.
    - En ambos casos actualiza 'whatsapp_reminder_sent = True'.
    """
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    info = WhatsAppService.get_appointment_reminder(db, appt)
    if not info["clean_phone"]:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "El paciente no tiene un número telefónico registrado."}
        )
    
    force_manual = (send_mode == "manual")
    dispatch_res = WhatsAppService.dispatch_message(
        phone=info["clean_phone"],
        message=info["message"],
        force_manual=force_manual
    )
    
    # Marcar como enviado en base de datos
    appt.whatsapp_reminder_sent = True
    appt.whatsapp_reminder_sent_at = datetime.utcnow()
    db.commit()

    return JSONResponse(content={
        "success": dispatch_res.get("success", True),
        "mode": dispatch_res.get("mode", "wa_link"),
        "wa_link": dispatch_res.get("wa_link"),
        "already_sent": True,
        "sent_at": appt.whatsapp_reminder_sent_at.strftime("%d/%m/%Y %H:%M"),
        "patient_name": info["patient_name"],
        "detail": dispatch_res.get("detail", "Recordatorio procesado.")
    })

@router.get("/{appointment_id}/waiting-alert-wa")
def get_waiting_alert_wa(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """Genera el mensaje y enlace de WhatsApp para avisar al Dr. que el paciente llegó."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
        
    alert_info = WhatsAppService.get_waiting_alert(db, appt)
    return JSONResponse(content=alert_info)

@router.post("/whatsapp/send-all-daily-reminders")
def send_all_daily_reminders(
    target_date: str = Form(None),  # YYYY-MM-DD (por defecto: mañana)
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('appointments'))
):
    """
    Envía en lote los recordatorios de WhatsApp para todas las citas pendientes/confirmadas
    de la fecha seleccionada (por defecto mañana) que aún no hayan sido notificadas.
    """
    if target_date:
        try:
            target = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            target = date.today() + timedelta(days=1)
    else:
        target = date.today() + timedelta(days=1)

    appts = db.query(Appointment).filter(
        Appointment.date == target,
        Appointment.status.in_(["Pendiente", "Confirmada"]),
        Appointment.whatsapp_reminder_sent == False
    ).all()

    sent_count = 0
    skipped_count = 0
    results = []

    for a in appts:
        info = WhatsAppService.get_appointment_reminder(db, a)
        if info["clean_phone"]:
            res = WhatsAppService.dispatch_message(info["clean_phone"], info["message"])
            a.whatsapp_reminder_sent = True
            a.whatsapp_reminder_sent_at = datetime.utcnow()
            sent_count += 1
            results.append({"id": a.id, "patient": info["patient_name"], "status": "sent", "mode": res["mode"]})
        else:
            skipped_count += 1
            results.append({"id": a.id, "patient": info["patient_name"], "status": "skipped", "reason": "no_phone"})

    db.commit()

    return JSONResponse(content={
        "success": True,
        "target_date": target.strftime("%d/%m/%Y"),
        "total_eligible": len(appts),
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "results": results
    })


