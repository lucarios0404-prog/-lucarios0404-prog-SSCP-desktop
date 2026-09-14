from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pathlib import Path
from datetime import datetime, date

from app.database import get_db
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.core.deps import require_current_user
from app.services.qr_service import generate_patient_qr_base64

router = APIRouter(prefix="/patients", tags=["patients"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/")
def list_patients(
    request: Request,
    q: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(Patient)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Patient.first_name.ilike(search),
                Patient.last_name.ilike(search),
                Patient.document_id.ilike(search),
                Patient.phone.ilike(search)
            )
        )
    
    patients = query.order_by(Patient.last_name).all()
    
    # Calcular saldos pendientes para cada paciente (F8)
    patient_cards = []
    for p in patients:
        pending_sum = sum(pay.total for pay in p.payments if pay.status == "pending")
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
            "search_query": q or ""
        }
    )

@router.get("/create")
def create_patient_form(request: Request, current_user = Depends(require_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="patients/create.html",
        context={"user": current_user}
    )

@router.post("/create")
def create_patient(
    request: Request,
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
        emergency_contact_phone=emergency_contact_phone
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return RedirectResponse(url=f"/patients/{new_patient.id}", status_code=303)

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

    # F8: Cálculo de deuda pendiente
    pending_payments = [p for p in payments if p.status == "pending"]
    balance_due = sum(p.total for p in pending_payments)

    # F17: Código QR del Paciente
    qr_code_base64 = generate_patient_qr_base64(patient)

    return templates.TemplateResponse(
        request=request,
        name="patients/view.html",
        context={
            "user": current_user,
            "patient": patient,
            "appointments": appointments,
            "consultations": consultations,
            "payments": payments,
            "balance_due": balance_due,
            "qr_code_base64": qr_code_base64,
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
    patient.updated_at = datetime.utcnow()

    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}", status_code=303)
