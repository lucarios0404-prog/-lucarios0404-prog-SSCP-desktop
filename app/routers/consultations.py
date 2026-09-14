from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pathlib import Path
from datetime import datetime
import json

from app.database import get_db
from app.models.consultation import Consultation
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.setting import Setting
from app.models.vital_sign import VitalSign
from app.models.template import ClinicalTemplate
from app.core.deps import require_current_user
from app.services.pdf_service import generate_prescription_pdf, generate_consultation_report_pdf
from app.services.audit_service import AuditService

router = APIRouter(prefix="/consultations", tags=["consultations"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Diagnósticos CIE-10 comunes para autocompletar / sugerencias rápidas
CIE10_COMMON = [
    {"code": "J00", "description": "Rinofaringitis aguda (resfriado común)"},
    {"code": "I10", "description": "Hipertensión esencial (primaria)"},
    {"code": "E11", "description": "Diabetes mellitus tipo 2"},
    {"code": "J02.9", "description": "Faringitis aguda, no especificada"},
    {"code": "K29.7", "description": "Gastritis, no especificada"},
    {"code": "M54.5", "description": "Lumbago no especificado"},
    {"code": "A09", "description": "Gastroenteritis y colitis de origen no especificado"},
    {"code": "R51", "description": "Cefalea"},
    {"code": "J20.9", "description": "Bronquitis aguda, no especificada"},
]

@router.get("/")
def list_consultations(
    request: Request,
    q: str = Query(None),
    patient_id: int = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(Consultation).join(Patient, Consultation.patient_id == Patient.id, isouter=True)
    if patient_id:
        query = query.filter(Consultation.patient_id == patient_id)
    
    clean_q = q.strip() if q else ""
    if clean_q:
        search_pattern = f"%{clean_q}%"
        query = query.filter(
            or_(
                Patient.first_name.ilike(search_pattern),
                Patient.last_name.ilike(search_pattern),
                Patient.document_id.ilike(search_pattern),
                Consultation.diagnosis.ilike(search_pattern),
                Consultation.reason.ilike(search_pattern),
                Consultation.treatment.ilike(search_pattern),
                Consultation.notes.ilike(search_pattern),
            )
        )
    
    total_count = query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        
    offset = (page - 1) * per_page
    consultations = query.order_by(Consultation.created_at.desc()).offset(offset).limit(per_page).all()
    patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="consultations/index.html",
        context={
            "user": current_user,
            "consultations": consultations,
            "selected_patient": patient,
            "q": clean_q,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "start_item": offset + 1 if total_count > 0 else 0,
            "end_item": min(offset + per_page, total_count),
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
    consultation_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "consultation").order_by(ClinicalTemplate.title).all()
    prescription_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "prescription").order_by(ClinicalTemplate.title).all()
    
    return templates.TemplateResponse(
        request=request,
        name="consultations/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "selected_appointment_id": appointment_id,
            "cie10_common": CIE10_COMMON,
            "consultation_templates": consultation_templates,
            "prescription_templates": prescription_templates,
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

    # Registrar en auditoría médica (F13)
    AuditService.log_change(
        db=db,
        entity_type="consultation",
        entity_id=new_consultation.id,
        action="create",
        summary=f"Consulta médica creada: {new_consultation.reason}",
        patient_id=new_consultation.patient_id,
        user_id=current_user.id if current_user else 1,
        new_data={"reason": new_consultation.reason, "diagnosis": diagnosis}
    )

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

    consultation_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "consultation").order_by(ClinicalTemplate.title).all()
    prescription_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "prescription").order_by(ClinicalTemplate.title).all()

    return templates.TemplateResponse(
        request=request,
        name="consultations/edit.html",
        context={
            "user": current_user,
            "consultation": consultation,
            "cie10_common": CIE10_COMMON,
            "consultation_templates": consultation_templates,
            "prescription_templates": prescription_templates,
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

    old_data = {
        "reason": consultation.reason,
        "diagnosis": consultation.diagnosis,
        "treatment": consultation.treatment,
        "prescription": consultation.prescription
    }

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

    # Registrar en auditoría médica (F13)
    AuditService.log_change(
        db=db,
        entity_type="consultation",
        entity_id=consultation.id,
        action="update",
        summary=f"Consulta #{consultation.id} editada: {edit_reason}",
        patient_id=consultation.patient_id,
        user_id=current_user.id if current_user else 1,
        old_data=old_data,
        new_data={"reason": reason, "diagnosis": diagnosis, "treatment": treatment, "prescription": prescription}
    )

    return RedirectResponse(url=f"/consultations/{consultation_id}", status_code=303)

@router.get("/{consultation_id}/prescription/pdf")
def download_prescription_pdf(
    consultation_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")
    
    setting = db.query(Setting).first()
    pdf_buffer = generate_prescription_pdf(consultation, setting)
    
    filename = f"Receta_Consulta_{consultation.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )

@router.get("/{consultation_id}/report/pdf")
def download_consultation_report_pdf(
    consultation_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")
    
    setting = db.query(Setting).first()
    vitals = None
    if consultation.patient_id:
        vitals = db.query(VitalSign).filter(VitalSign.patient_id == consultation.patient_id).order_by(VitalSign.recorded_at.desc()).first()
        
    pdf_buffer = generate_consultation_report_pdf(consultation, setting, vitals)
    
    filename = f"Informe_Consulta_{consultation.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )
