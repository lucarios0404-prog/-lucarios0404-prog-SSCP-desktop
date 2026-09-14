from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, date, time, timedelta

from app.database import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.core.deps import require_current_user

router = APIRouter(prefix="/appointments", tags=["appointments"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

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
    
    # Pre-organizar citas por fecha para el calendario
    calendar_events = []
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

    today_str = date.today().strftime("%Y-%m-%d")

    return templates.TemplateResponse(
        request=request,
        name="appointments/index.html",
        context={
            "user": current_user,
            "appointments": appointments,
            "view_mode": view,
            "calendar_events": calendar_events,
            "today_str": today_str,
            "filter_date": filter_date or "",
            "status_filter": status or "all",
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
    patients = db.query(Patient).order_by(Patient.last_name).all()
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
    is_recurring: bool = Form(False),
    recurrence_count: int = Form(1), # Número de ocurrencias para F14
    recurrence_interval_days: int = Form(30), # Intervalo en días (30 = mensual)
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    base_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    start_time_obj = datetime.strptime(start_time_str, "%H:%M").time()
    end_time_obj = datetime.strptime(end_time_str, "%H:%M").time()
    
    # Determinar cuántas citas crear (F14: citas recurrentes)
    count = max(1, min(12, recurrence_count if is_recurring else 1))
    
    for i in range(count):
        current_appt_date = base_date + timedelta(days=i * recurrence_interval_days)
        reason_label = reason if i == 0 else f"{reason} (Control recurrente #{i+1})"
        
        new_appointment = Appointment(
            patient_id=patient_id,
            doctor_id=current_user.id,
            date=current_appt_date,
            start_time=start_time_obj,
            end_time=end_time_obj,
            reason=reason_label,
            notes=notes,
            is_recurring=is_recurring,
            status="Pendiente"
        )
        db.add(new_appointment)

    db.commit()
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
        appt.status = new_status
        appt.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/appointments", status_code=303)
