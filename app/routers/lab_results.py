from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, date

from app.database import get_db
from app.models.lab_result import LabResult
from app.models.patient import Patient
from app.core.deps import require_current_user

router = APIRouter(prefix="/lab-results", tags=["lab_results"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

COMMON_TESTS = [
    {"name": "Hemograma Completo", "category": "Hematología"},
    {"name": "Perfil Lipídico (Colesterol, Triglicéridos, HDL, LDL)", "category": "Bioquímica"},
    {"name": "Glucemia en Ayunas", "category": "Bioquímica"},
    {"name": "Hemoglobina Glicosilada (HbA1c)", "category": "Bioquímica"},
    {"name": "Examen General de Orina (EGO)", "category": "Uroanálisis"},
    {"name": "Perfil Tiroideo (TSH, T3, T4 Libre)", "category": "Endocrinología"},
    {"name": "Creatinina y Urea en Sangre", "category": "Función Renal"},
    {"name": "Coprológico y Coproparasitario", "category": "Parasitología"},
    {"name": "Electrocardiograma (EKG)", "category": "Cardiología"},
]

@router.get("/")
def list_lab_results(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(LabResult).order_by(LabResult.result_date.desc())
    if patient_id:
        query = query.filter(LabResult.patient_id == patient_id)
        
    results = query.all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="labs/index.html",
        context={
            "user": current_user,
            "results": results,
            "selected_patient": selected_patient,
        }
    )

@router.get("/create")
def create_lab_result_form(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patients = db.query(Patient).order_by(Patient.last_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="labs/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "common_tests": COMMON_TESTS,
            "today": date.today().strftime("%Y-%m-%d"),
        }
    )

@router.post("/create")
def create_lab_result(
    request: Request,
    patient_id: int = Form(...),
    test_name: str = Form(...),
    test_category: str = Form("General"),
    result_date_str: str = Form(..., alias="result_date"),
    summary_findings: str = Form(...),
    is_abnormal: bool = Form(False),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    res_date = datetime.strptime(result_date_str, "%Y-%m-%d").date()

    new_lab = LabResult(
        patient_id=patient_id,
        test_name=test_name,
        test_category=test_category,
        result_date=res_date,
        summary_findings=summary_findings,
        is_abnormal=is_abnormal,
        recorded_by_id=current_user.id,
    )
    db.add(new_lab)
    db.commit()
    return RedirectResponse(url=f"/lab-results?patient_id={patient_id}", status_code=303)
