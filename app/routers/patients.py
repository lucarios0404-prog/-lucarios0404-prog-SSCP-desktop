from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pathlib import Path
from datetime import datetime, date

from app.database import get_db
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.vital_sign import VitalSign
from app.core.deps import require_current_user
from app.services.qr_service import generate_patient_qr_base64
from app.services.patient_service import PatientService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/patients", tags=["patients"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

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
    page: int = Query(1, ge=1),
    per_page: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(Patient)
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
    patients = query.order_by(Patient.last_name.asc(), Patient.first_name.asc()).offset(offset).limit(per_page).all()
    
    # Calcular saldos pendientes solo para los pacientes visibles en esta página
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
            "search_query": clean_q,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "start_item": offset + 1 if total_count > 0 else 0,
            "end_item": min(offset + per_page, total_count),
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
            "vitals": list(reversed(vitals)),
            "vitals_evolution": vitals_evolution,
            "audit_logs": audit_logs,
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

    old_data = {
        "name": f"{patient.first_name} {patient.last_name}",
        "phone": patient.phone,
        "allergies": patient.allergies,
        "address": patient.address
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
