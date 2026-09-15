from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pathlib import Path
from datetime import datetime
import random
import string

from app.database import get_db
from app.models.payment import Payment
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.core.deps import require_current_user

router = APIRouter(prefix="/payments", tags=["payments"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

def generate_receipt_number():
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"REC-{random_chars}"

@router.get("/")
def list_payments(
    request: Request,
    status: str = Query("all", pattern="^(all|paid|pending|receivables)$"),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(Payment).order_by(Payment.created_at.desc())
    
    if status == "paid":
        query = query.filter(Payment.status == "paid")
    elif status == "pending":
        query = query.filter(Payment.status == "pending")
    
    payments = query.all()
    
    # Calcular totales y cuentas por cobrar (F13)
    total_cobrado = sum(p.total for p in payments if p.status == "paid")
    total_pendiente = sum(p.total for p in payments if p.status == "pending")
    
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
    
    return templates.TemplateResponse(
        request=request,
        name="payments/index.html",
        context={
            "user": current_user,
            "payments": payments,
            "status_filter": status,
            "total_cobrado": total_cobrado,
            "total_pendiente": total_pendiente,
            "debtors": debtors,
        }
    )

@router.get("/create")
def create_payment_form(
    request: Request,
    patient_id: int = Query(None),
    appointment_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patients = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).order_by(Patient.last_name).all()
    appointments = []
    if patient_id:
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
            "appointments": appointments,
            "selected_patient_id": patient_id,
            "selected_appointment_id": appointment_id,
            "default_receipt": default_receipt,
        }
    )

@router.post("/create")
def create_payment(
    request: Request,
    patient_id: int = Form(...),
    appointment_id: int = Form(None),
    service_name: str = Form("Consulta Médica General"),
    amount: float = Form(...),
    discount: float = Form(0.0),
    payment_method: str = Form("cash"),
    status: str = Form("paid"),
    receipt_number: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    if not receipt_number:
        receipt_number = generate_receipt_number()

    total = max(0.0, float(amount) - float(discount or 0.0))

    new_payment = Payment(
        patient_id=patient_id,
        appointment_id=appointment_id if appointment_id and appointment_id > 0 else None,
        service_name=service_name,
        amount=amount,
        discount=discount,
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
    if payment:
        payment.status = "paid"
        payment.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/payments", status_code=303)
