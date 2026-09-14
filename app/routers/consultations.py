from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime
import json

from app.database import get_db
from app.models.consultation import Consultation
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.core.deps import require_current_user

router = APIRouter(prefix="/consultations", tags=["consultations"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Diagnósticos CIE-10 comunes para autocompletar / sugerencias rápidas
CIE10_COMMON = [
    {"code": "J00", "description": "Rinofaringitis aguda [resfriado común]"},
    {"code": "J02.9", "description": "Faringitis aguda, no especificada"},
    {"code": "I10", "description": "Hipertensión esencial (primaria)"},
    {"code": "E11.9", "description": "Diabetes mellitus tipo 2 sin mención de complicación"},
    {"code": "K29.7", "description": "Gastritis, no especificada"},
    {"code": "M54.5", "description": "Lumbago no especificado"},
    {"code": "A09", "description": "Gastroenteritis y colitis de origen no especificado"},
    {"code": "R51", "description": "Cefalea"},
    {"code": "J20.9", "description": "Bronquitis aguda, no especificada"},
    {"code": "N39.0", "description": "Infección de vías urinarias, sitio no especificado"},
]

@router.get("/")
def list_consultations(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(Consultation).order_by(Consultation.created_at.desc())
    if patient_id:
        query = query.filter(Consultation.patient_id == patient_id)
    
    consultations = query.all()
    patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="consultations/index.html",
        context={
            "user": current_user,
            "consultations": consultations,
            "selected_patient": patient,
        }
    )

@router.get("/create")
def create_consultation_form(
    request: Request,
    patient_id: int = Query(None),
    appointment_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patients = db.query(Patient).order_by(Patient.last_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None
    
    return templates.TemplateResponse(
        request=request,
        name="consultations/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "selected_appointment_id": appointment_id,
            "cie10_common": CIE10_COMMON,
        }
    )

@router.post("/create")
def create_consultation(
    request: Request,
    patient_id: int = Form(...),
    appointment_id: int = Form(None),
    reason: str = Form(...),
    symptoms: str = Form(None),
    physical_exam: str = Form(None),
    diagnosis: str = Form(None),
    treatment: str = Form(None),
    prescription: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    new_consultation = Consultation(
        patient_id=patient_id,
        doctor_id=current_user.id,
        appointment_id=appointment_id if appointment_id and appointment_id > 0 else None,
        reason=reason,
        symptoms=symptoms,
        physical_exam=physical_exam,
        diagnosis=diagnosis,
        treatment=treatment,
        prescription=prescription,
        notes=notes,
        edit_history=json.dumps([{
            "action": "created",
            "user": current_user.email,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }])
    )
    db.add(new_consultation)
    
    # Si viene ligada a una cita, marcar la cita como completada
    if appointment_id and appointment_id > 0:
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if appt:
            appt.status = "Completada"
            
    db.commit()
    db.refresh(new_consultation)
    return RedirectResponse(url=f"/consultations/{new_consultation.id}", status_code=303)

@router.get("/{consultation_id}")
def view_consultation(
    request: Request,
    consultation_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")

    history_entries = []
    if consultation.edit_history:
        try:
            history_entries = json.loads(consultation.edit_history)
        except Exception:
            history_entries = []

    return templates.TemplateResponse(
        request=request,
        name="consultations/view.html",
        context={
            "user": current_user,
            "consultation": consultation,
            "history_entries": history_entries,
        }
    )

@router.get("/{consultation_id}/edit")
def edit_consultation_form(
    request: Request,
    consultation_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")

    return templates.TemplateResponse(
        request=request,
        name="consultations/edit.html",
        context={
            "user": current_user,
            "consultation": consultation,
            "cie10_common": CIE10_COMMON,
        }
    )

@router.post("/{consultation_id}/edit")
def update_consultation(
    request: Request,
    consultation_id: int,
    reason: str = Form(...),
    symptoms: str = Form(None),
    physical_exam: str = Form(None),
    diagnosis: str = Form(None),
    treatment: str = Form(None),
    prescription: str = Form(None),
    notes: str = Form(None),
    edit_reason: str = Form("Modificación de notas médicas"),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")

    # Registrar historial de edición (F3)
    history = []
    if consultation.edit_history:
        try:
            history = json.loads(consultation.edit_history)
        except Exception:
            history = []

    history.append({
        "action": "edited",
        "user": current_user.email,
        "reason": edit_reason,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    })

    consultation.reason = reason
    consultation.symptoms = symptoms
    consultation.physical_exam = physical_exam
    consultation.diagnosis = diagnosis
    consultation.treatment = treatment
    consultation.prescription = prescription
    consultation.notes = notes
    consultation.updated_by_id = current_user.id
    consultation.updated_at = datetime.utcnow()
    consultation.edit_history = json.dumps(history)

    db.commit()
    return RedirectResponse(url=f"/consultations/{consultation_id}", status_code=303)
