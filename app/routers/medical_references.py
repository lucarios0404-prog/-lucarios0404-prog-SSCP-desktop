from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models.patient import Patient
from app.models.medical_reference import MedicalReference
from app.models.setting import Setting
from app.models.template import ClinicalTemplate
from app.core.deps import require_current_user, require_permission
from app.services.pdf_service import generate_medical_reference_pdf

router = APIRouter(prefix="/references", tags=["references"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/")
def list_references(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('references'))
):
    query = db.query(MedicalReference).order_by(MedicalReference.created_at.desc())
    if patient_id:
        query = query.filter(MedicalReference.patient_id == patient_id)
    references = query.all()

    return templates.TemplateResponse(
        request=request,
        name="references/index.html",
        context={
            "user": current_user,
            "references": references,
        }
    )

@router.get("/create")
def create_reference_form(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('references'))
):
    patients = db.query(Patient).order_by(Patient.first_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None
    templates_list = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "reference").all()

    return templates.TemplateResponse(
        request=request,
        name="references/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "templates": templates_list,
        }
    )

@router.post("/create")
def submit_reference(
    patient_id: int = Form(...),
    referred_to_doctor_or_specialty: str = Form(...),
    institution: str = Form(None),
    reason_for_referral: str = Form(...),
    clinical_summary: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('references'))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    ref_obj = MedicalReference(
        patient_id=patient.id,
        doctor_id=current_user.id,
        referred_to_doctor_or_specialty=referred_to_doctor_or_specialty,
        institution=institution,
        reason_for_referral=reason_for_referral,
        clinical_summary=clinical_summary,
        notes=notes,
        sede_origen="local"
    )
    db.add(ref_obj)
    db.commit()
    db.refresh(ref_obj)

    return RedirectResponse(url=f"/references/{ref_obj.id}/pdf", status_code=303)

@router.get("/{reference_id}/pdf")
def download_reference_pdf(
    reference_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    ref_obj = db.query(MedicalReference).filter(MedicalReference.id == reference_id).first()
    if not ref_obj:
        raise HTTPException(status_code=404, detail="Carta de referencia no encontrada")

    setting = db.query(Setting).first()
    pdf_buffer = generate_medical_reference_pdf(ref_obj, setting)

    filename = f"Referencia_Medica_{ref_obj.patient_id}_{ref_obj.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )
