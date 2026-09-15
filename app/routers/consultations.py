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
from app.models.cie10 import Cie10Code
from app.data.cie10_catalog import OFFICIAL_CIE10_CATALOG, seed_cie10_catalog
from app.core.deps import require_current_user, require_permission
from app.services.pdf_service import generate_prescription_pdf, generate_consultation_report_pdf
from app.services.audit_service import AuditService

router = APIRouter(prefix="/consultations", tags=["consultations"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Diagnósticos CIE-10 comunes para sugerencias rápidas iniciales
CIE10_COMMON = [
    {"code": "I10", "description": "Hipertensión esencial (primaria)"},
    {"code": "E11.9", "description": "Diabetes mellitus tipo 2 sin mención de complicación"},
    {"code": "J00", "description": "Rinofaringitis aguda (resfriado común)"},
    {"code": "J02.9", "description": "Faringitis aguda, no especificada"},
    {"code": "K29.7", "description": "Gastritis, no especificada"},
    {"code": "M54.5", "description": "Lumbago no especificado (lumbalgia)"},
    {"code": "A09", "description": "Diarrea y gastroenteritis de presunto origen infeccioso"},
    {"code": "R51", "description": "Cefalea (dolor de cabeza)"},
    {"code": "J20.9", "description": "Bronquitis aguda, no especificada"},
    {"code": "J45.9", "description": "Asma, no especificada"},
    {"code": "N39.0", "description": "Infección de vías urinarias (IVU)"},
    {"code": "E78.5", "description": "Dislipidemia / Hiperlipidemia"},
]

import unicodedata

def strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()

@router.get("/cie10/search")
def search_cie10_codes(
    q: str = Query("", description="Término o código a buscar"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('consultations'))
):
    # Si la BD no estaba sembrada aún, autosembrar al vuelo
    if not db.query(Cie10Code).first():
        seed_cie10_catalog(db)

    clean_q = q.strip() if q else ""
    if not clean_q:
        results = db.query(Cie10Code).order_by(Cie10Code.is_custom.desc(), Cie10Code.id.asc()).limit(limit).all()
        return [r.to_dict() for r in results]

    # Búsqueda tolerante a tildes/acentos y mayúsculas
    norm_q = strip_accents(clean_q)
    all_codes = db.query(Cie10Code).all()
    matching = []
    for c in all_codes:
        c_code_norm = strip_accents(c.code)
        c_desc_norm = strip_accents(c.description)
        c_chap_norm = strip_accents(c.chapter or "")
        if norm_q in c_code_norm or norm_q in c_desc_norm or norm_q in c_chap_norm:
            matching.append(c)

    # Ordenar: primero códigos que empiezan con la consulta, luego custom, luego alfabético
    matching.sort(key=lambda x: (
        not strip_accents(x.code).startswith(norm_q),
        not x.is_custom,
        x.code
    ))
    return [r.to_dict() for r in matching[:limit]]


@router.post("/cie10/custom")
def add_custom_cie10_code(
    code: str = Form(None),
    description: str = Form(...),
    chapter: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('consultations'))
):
    clean_desc = description.strip()
    if not clean_desc:
        raise HTTPException(status_code=400, detail="La descripción del diagnóstico es obligatoria.")
    
    clean_code = (code.strip().upper() if code else "").strip()
    if not clean_code:
        custom_count = db.query(Cie10Code).filter(Cie10Code.is_custom == True).count()
        clean_code = f"PERS-{custom_count + 1:02d}"

    existing = db.query(Cie10Code).filter(Cie10Code.code == clean_code, Cie10Code.description == clean_desc).first()
    if existing:
        return {"success": True, "item": existing.to_dict(), "message": "Código ya existente"}

    new_code = Cie10Code(
        code=clean_code,
        description=clean_desc,
        chapter=chapter.strip() if chapter else "Diagnóstico Clínico Personalizado",
        is_custom=True,
        doctor_id=current_user.id
    )
    db.add(new_code)
    db.commit()
    db.refresh(new_code)

    return {"success": True, "item": new_code.to_dict(), "message": "Diagnóstico personalizado agregado exitosamente"}

@router.get("/")
def list_consultations(
    request: Request,
    q: str = Query(None),
    patient_id: int = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('consultations'))
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
    current_user = Depends(require_permission('consultations'))
):
    patients = db.query(Patient).order_by(Patient.last_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None
    consultation_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "consultation").order_by(ClinicalTemplate.title).all()
    prescription_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "prescription").order_by(ClinicalTemplate.title).all()
    
    # Obtener sugerencias comunes oficiales de la BD
    common_db = db.query(Cie10Code).filter(Cie10Code.is_custom == False).limit(14).all()
    dynamic_cie10 = [{"code": c.code, "description": c.description} for c in common_db] if common_db else CIE10_COMMON

    return templates.TemplateResponse(
        request=request,
        name="consultations/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "selected_appointment_id": appointment_id,
            "cie10_common": dynamic_cie10,
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
    current_user = Depends(require_permission('consultations'))
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
    if not (current_user.has_permission('consultations') or current_user.has_permission('print_prescriptions')):
        raise HTTPException(
            status_code=403,
            detail="Acceso restringido: No cuenta con permisos para ver consultas clínicas ni imprimir recetas."
        )
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
    current_user = Depends(require_permission('consultations'))
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")

    consultation_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "consultation").order_by(ClinicalTemplate.title).all()
    prescription_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "prescription").order_by(ClinicalTemplate.title).all()

    # Obtener sugerencias comunes oficiales de la BD
    common_db = db.query(Cie10Code).filter(Cie10Code.is_custom == False).limit(14).all()
    dynamic_cie10 = [{"code": c.code, "description": c.description} for c in common_db] if common_db else CIE10_COMMON

    return templates.TemplateResponse(
        request=request,
        name="consultations/edit.html",
        context={
            "user": current_user,
            "consultation": consultation,
            "cie10_common": dynamic_cie10,
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
    current_user = Depends(require_permission('consultations'))
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
    current_user = Depends(require_permission('print_prescriptions'))
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
    current_user = Depends(require_permission('consultations'))
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
