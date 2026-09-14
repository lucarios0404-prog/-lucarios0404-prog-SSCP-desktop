from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models.patient import Patient
from app.models.medical_license import MedicalLicense
from app.models.setting import Setting
from app.models.template import ClinicalTemplate
from app.core.deps import require_current_user
from app.services.pdf_service import generate_medical_license_pdf

router = APIRouter(prefix="/licenses", tags=["licenses"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/")
def list_licenses(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(MedicalLicense).order_by(MedicalLicense.created_at.desc())
    if patient_id:
        query = query.filter(MedicalLicense.patient_id == patient_id)
    licenses = query.all()

    return templates.TemplateResponse(
        request=request,
        name="licenses/index.html",
        context={
            "user": current_user,
            "licenses": licenses,
        }
    )

@router.get("/create")
def create_license_form(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patients = db.query(Patient).order_by(Patient.first_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None
    templates_list = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "license").all()

    return templates.TemplateResponse(
        request=request,
        name="licenses/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "templates": templates_list,
            "today": date.today().strftime("%Y-%m-%d"),
            "tomorrow": (date.today() + timedelta(days=2)).strftime("%Y-%m-%d"),
        }
    )

@router.post("/create")
def submit_license(
    patient_id: int = Form(...),
    diagnosis: str = Form(...),
    days_rest: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    workplace_or_school: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    license_obj = MedicalLicense(
        patient_id=patient.id,
        doctor_id=current_user.id,
        diagnosis=diagnosis,
        days_rest=days_rest,
        start_date=s_date,
        end_date=e_date,
        workplace_or_school=workplace_or_school,
        notes=notes,
        sede_origen="local"
    )
    db.add(license_obj)
    db.commit()
    db.refresh(license_obj)

    return RedirectResponse(url=f"/licenses/{license_obj.id}/pdf", status_code=303)

@router.get("/{license_id}/pdf")
def download_license_pdf(
    license_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    license_obj = db.query(MedicalLicense).filter(MedicalLicense.id == license_id).first()
    if not license_obj:
        raise HTTPException(status_code=404, detail="Licencia médica no encontrada")

    setting = db.query(Setting).first()
    pdf_buffer = generate_medical_license_pdf(license_obj, setting)

    filename = f"Licencia_Medica_{license_obj.patient_id}_{license_obj.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )
