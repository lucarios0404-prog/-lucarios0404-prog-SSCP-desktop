from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models.vaccine import VaccineRecord
from app.models.patient import Patient
from app.core.deps import require_current_user

router = APIRouter(prefix="/vaccines", tags=["vaccines"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

COMMON_VACCINES = [
    {"name": "Hepatitis B", "schedule": "Al nacer, 2m, 4m, 6m"},
    {"name": "Influenza Estacional", "schedule": "Anual"},
    {"name": "Tétanos - Difteria (Td / DTPa)", "schedule": "Refuerzo cada 10 años"},
    {"name": "COVID-19 (Bivalente / Actualizada)", "schedule": "Dosis periódica"},
    {"name": "Neumococo Conjugada (PCV13 / PPSV23)", "schedule": "Adultos mayores y riesgo"},
    {"name": "Virus del Papiloma Humano (VPH)", "schedule": "2 o 3 dosis"},
    {"name": "Sarampión, Rubéola, Paperas (SRP)", "schedule": "Infantil / Refuerzo"},
    {"name": "Fiebre Amarilla", "schedule": "Dosis única (viajeros)"},
]

@router.get("/")
def list_vaccines(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(VaccineRecord).order_by(VaccineRecord.application_date.desc())
    if patient_id:
        query = query.filter(VaccineRecord.patient_id == patient_id)

    records = query.all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="vaccines/index.html",
        context={
            "user": current_user,
            "records": records,
            "selected_patient": selected_patient,
            "common_vaccines": COMMON_VACCINES,
        }
    )

@router.get("/create")
def create_vaccine_form(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patients = db.query(Patient).order_by(Patient.last_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None
    today = date.today()

    return templates.TemplateResponse(
        request=request,
        name="vaccines/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "common_vaccines": COMMON_VACCINES,
            "today": today.strftime("%Y-%m-%d"),
            "next_year": (today + timedelta(days=365)).strftime("%Y-%m-%d"),
        }
    )

@router.post("/create")
def create_vaccine(
    request: Request,
    patient_id: int = Form(...),
    vaccine_name: str = Form(...),
    dose: str = Form("1ra Dosis"),
    application_date_str: str = Form(..., alias="application_date"),
    next_due_date_str: str = Form(None, alias="next_due_date"),
    lot_number: str = Form(None),
    administered_by: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    app_date = datetime.strptime(application_date_str, "%Y-%m-%d").date()
    due_date = datetime.strptime(next_due_date_str, "%Y-%m-%d").date() if next_due_date_str else None

    new_vaccine = VaccineRecord(
        patient_id=patient_id,
        vaccine_name=vaccine_name,
        dose=dose,
        application_date=app_date,
        next_due_date=due_date,
        lot_number=lot_number,
        administered_by=administered_by or (current_user.name or current_user.email),
        notes=notes,
    )
    db.add(new_vaccine)
    db.commit()
    return RedirectResponse(url=f"/vaccines?patient_id={patient_id}", status_code=303)
