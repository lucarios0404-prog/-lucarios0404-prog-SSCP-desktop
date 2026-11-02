import re
from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional
import random
import string

from app.database import get_db
from app.models.payment import Payment
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.service import Service
from app.core.deps import require_current_user
from app.core.templates import templates
from app.services.ars_service import get_all_ars

router = APIRouter(prefix="/payments", tags=["payments"])

def generate_receipt_number():
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"REC-{random_chars}"

@router.get("/")
def list_payments(
    request: Request,
    status: str = Query("all", pattern="^(all|paid|pending|receivables)$"),
    date_filter: str = Query("all"),
    custom_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    start_today = datetime.combine(today, datetime.min.time())
    end_today = datetime.combine(today, datetime.max.time())

    # 1. Calcular siempre el total cobrado el DÍA DE HOY (métrica fija destacada)
    today_records = db.query(Payment).filter(
        Payment.created_at >= start_today,
        Payment.created_at <= end_today
    ).all()
    total_cobrado_hoy = sum(p.total for p in today_records if p.status == "paid")
    total_cobrado_hoy_count = sum(1 for p in today_records if p.status == "paid")
    breakdown_hoy = {
        "cash": sum(p.total for p in today_records if p.status == "paid" and p.payment_method == "cash"),
        "card": sum(p.total for p in today_records if p.status == "paid" and p.payment_method == "card"),
        "transfer": sum(p.total for p in today_records if p.status == "paid" and p.payment_method == "transfer"),
        "insurance": sum(p.total for p in today_records if p.status == "paid" and p.payment_method == "insurance"),
    }

    # 2. Filtrado de la lista principal
    query = db.query(Payment).order_by(Payment.created_at.desc())
    
    if status == "paid":
        query = query.filter(Payment.status == "paid")
    elif status == "pending":
        query = query.filter(Payment.status == "pending")

    # Aplicar filtro por día / fecha
    active_date_filter = date_filter
    if custom_date and custom_date.strip():
        try:
            c_date = datetime.strptime(custom_date.strip(), "%Y-%m-%d").date()
            query = query.filter(
                Payment.created_at >= datetime.combine(c_date, datetime.min.time()),
                Payment.created_at <= datetime.combine(c_date, datetime.max.time())
            )
            active_date_filter = custom_date.strip()
        except ValueError:
            pass
    elif date_filter == "today":
        query = query.filter(
            Payment.created_at >= start_today,
            Payment.created_at <= end_today
        )
    elif date_filter == "yesterday":
        yesterday = today - timedelta(days=1)
        query = query.filter(
            Payment.created_at >= datetime.combine(yesterday, datetime.min.time()),
            Payment.created_at <= datetime.combine(yesterday, datetime.max.time())
        )
    elif date_filter == "this_week":
        start_week = today - timedelta(days=today.weekday())
        query = query.filter(
            Payment.created_at >= datetime.combine(start_week, datetime.min.time())
        )
    elif date_filter and re.match(r"^\d{4}-\d{2}-\d{2}$", date_filter):
        try:
            spec_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            query = query.filter(
                Payment.created_at >= datetime.combine(spec_date, datetime.min.time()),
                Payment.created_at <= datetime.combine(spec_date, datetime.max.time())
            )
        except ValueError:
            pass
    
    payments = query.all()
    
    # Calcular totales del período filtrado
    total_cobrado = sum(p.total for p in payments if p.status == "paid")
    total_pendiente = sum(p.total for p in payments if p.status == "pending")

    # 3. Agrupación y división por días
    from collections import OrderedDict
    payments_by_day = OrderedDict()
    for p in payments:
        p_date = p.created_at.date() if p.created_at else today
        p_key = p_date.strftime("%Y-%m-%d")
        if p_key not in payments_by_day:
            if p_date == today:
                day_lbl = f"Hoy ({p_date.strftime('%d/%m/%Y')})"
            elif p_date == today - timedelta(days=1):
                day_lbl = f"Ayer ({p_date.strftime('%d/%m/%Y')})"
            else:
                day_lbl = p_date.strftime("%d/%m/%Y")

            payments_by_day[p_key] = {
                "date_key": p_key,
                "label": day_lbl,
                "records": [],
                "day_paid": 0.0,
                "day_pending": 0.0,
                "count": 0
            }
        payments_by_day[p_key]["records"].append(p)
        if p.status == "paid":
            payments_by_day[p_key]["day_paid"] += p.total
        elif p.status == "pending":
            payments_by_day[p_key]["day_pending"] += p.total
        payments_by_day[p_key]["count"] += 1
    
    # Lista de pacientes con saldo pendiente (Cuentas por cobrar F13)
    pending_payments = db.query(Payment).filter(Payment.status == "pending").all()
    receivables = {}
    for p in pending_payments:
        pid = p.patient_id
        if pid not in receivables:
            receivables[pid] = {
                "patient": p.patient,
                "total_debt": 0.0,
                "pending_count": 0,
                "payments": []
            }
        receivables[pid]["total_debt"] += p.total
        receivables[pid]["pending_count"] += 1
        receivables[pid]["payments"].append(p)
    
    debtors = list(receivables.values())
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category.asc(), Service.name.asc()).all()
    
    return templates.TemplateResponse(
        request=request,
        name="payments/index.html",
        context={
            "user": current_user,
            "payments": payments,
            "services": services,
            "ars_list": get_all_ars(),
            "status_filter": status,
            "date_filter": active_date_filter,
            "custom_date": custom_date or (active_date_filter if re.match(r"^\d{4}-\d{2}-\d{2}$", active_date_filter) else ""),
            "today_str": today_str,
            "total_cobrado": total_cobrado,
            "total_pendiente": total_pendiente,
            "total_cobrado_hoy": total_cobrado_hoy,
            "total_cobrado_hoy_count": total_cobrado_hoy_count,
            "breakdown_hoy": breakdown_hoy,
            "payments_by_day": payments_by_day,
            "debtors": debtors,
        }
    )

@router.get("/create")
def create_payment_form(
    request: Request,
    patient_id: Optional[int] = Query(None),
    appointment_id: Optional[int] = Query(None),
    service_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    # Si viene appointment_id pero no patient_id, obtener patient_id y posible service_id de la cita
    if appointment_id:
        selected_appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if selected_appt:
            if not patient_id:
                patient_id = selected_appt.patient_id
            if not service_id and selected_appt.service_id:
                service_id = selected_appt.service_id

    patients = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).order_by(Patient.last_name).all()
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category.asc(), Service.name.asc()).all()
    appointments = []
    selected_patient = None
    if patient_id:
        selected_patient = db.query(Patient).filter(Patient.id == patient_id).first()
        appointments = db.query(Appointment).filter(Appointment.patient_id == patient_id).order_by(Appointment.date.desc()).all()
    else:
        appointments = db.query(Appointment).order_by(Appointment.date.desc()).limit(20).all()

    default_receipt = generate_receipt_number()
    return templates.TemplateResponse(
        request=request,
        name="payments/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "services": services,
            "ars_list": get_all_ars(),
            "appointments": appointments,
            "selected_patient_id": patient_id,
            "selected_appointment_id": appointment_id,
            "selected_service_id": service_id,
            "default_receipt": default_receipt,
        }
    )

@router.post("/create")
def create_payment(
    request: Request,
    patient_id: int = Form(...),
    appointment_id: Optional[int] = Form(None),
    service_id: Optional[int] = Form(None),
    service_name: Optional[str] = Form("Consulta Médica General"),
    insurance_name: Optional[str] = Form(None),
    amount: float = Form(...),
    discount: Optional[float] = Form(0.0),
    payment_method: str = Form("cash"),
    status: str = Form("paid"),
    receipt_number: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    if not receipt_number:
        receipt_number = generate_receipt_number()

    # Si se seleccionó un servicio del talonario, sincronizar nombre
    if service_id:
        svc = db.query(Service).filter(Service.id == service_id).first()
        if svc and (not service_name or service_name == "Consulta Médica General"):
            service_name = svc.name

    # Si no se pasó seguro explícito, heredar el seguro registrado del paciente
    if not insurance_name:
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if p and p.insurance_name:
            insurance_name = p.insurance_name

    disc = float(discount or 0.0)
    base_amount = float(amount or 0.0)
    total = max(0.0, base_amount - disc)

    appt_id = appointment_id if appointment_id and appointment_id > 0 else None
    if not appt_id:
        from datetime import date
        today = date.today()
        today_appt = db.query(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.date == today
        ).first()
        if today_appt:
            appt_id = today_appt.id

    new_payment = Payment(
        patient_id=patient_id,
        appointment_id=appt_id,
        service_id=service_id if service_id and service_id > 0 else None,
        service_name=service_name or "Consulta Médica General",
        insurance_name=insurance_name or "Privado / Particular",
        amount=base_amount,
        discount=disc,
        total=total,
        payment_method=payment_method,
        status=status,
        receipt_number=receipt_number,
        notes=notes,
        created_by_id=current_user.id,
    )
    db.add(new_payment)
    db.commit()
    return RedirectResponse(url="/payments", status_code=303)

@router.post("/{payment_id}/pay")
def mark_payment_paid(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    payment.status = "paid"
    payment.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url="/payments", status_code=303)
