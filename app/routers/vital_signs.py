from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime

from app.database import get_db
from app.models.vital_sign import VitalSign
from app.models.patient import Patient
from app.core.deps import require_current_user

router = APIRouter(prefix="/vitals", tags=["vitals"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/patient/{patient_id}")
def view_patient_vitals(
    request: Request,
    patient_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    vitals = db.query(VitalSign).filter(VitalSign.patient_id == patient_id).order_by(VitalSign.recorded_at.asc()).all()

    # Pre-formatear datos para gráficas Chart.js (F11)
    dates = [v.recorded_at.strftime("%d/%m/%y") for v in vitals]
    weights = [v.weight_kg for v in vitals]
    systolics = [v.systolic_bp for v in vitals]
    diastolics = [v.diastolic_bp for v in vitals]
    heart_rates = [v.heart_rate for v in vitals]
    glucoses = [v.glucose_mg_dl for v in vitals]

    return templates.TemplateResponse(
        request=request,
        name="vitals/view.html",
        context={
            "user": current_user,
            "patient": patient,
            "vitals": list(reversed(vitals)),
            "chart_dates": dates,
            "chart_weights": weights,
            "chart_systolics": systolics,
            "chart_diastolics": diastolics,
            "chart_heart_rates": heart_rates,
            "chart_glucoses": glucoses,
        }
    )

@router.get("/patient/{patient_id}/api/evolution")
def api_vitals_evolution(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    vitals = db.query(VitalSign).filter(VitalSign.patient_id == patient_id).order_by(VitalSign.recorded_at.asc()).all()
    return {
        "dates": [v.recorded_at.strftime("%d/%m/%Y") for v in vitals],
        "weight": [v.weight_kg for v in vitals],
        "systolic": [v.systolic_bp for v in vitals],
        "diastolic": [v.diastolic_bp for v in vitals],
        "heart_rate": [v.heart_rate for v in vitals],
        "glucose": [v.glucose_mg_dl for v in vitals],
    }

@router.post("/patient/{patient_id}/create")
def create_vital_sign(
    request: Request,
    patient_id: int,
    weight_kg: float = Form(None),
    height_cm: float = Form(None),
    systolic_bp: int = Form(None),
    diastolic_bp: int = Form(None),
    heart_rate: int = Form(None),
    respiratory_rate: int = Form(None),
    temperature_c: float = Form(None),
    oxygen_saturation: float = Form(None),
    glucose_mg_dl: float = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    bmi = None
    if weight_kg and height_cm and height_cm > 0:
        height_m = height_cm / 100.0
        bmi = round(weight_kg / (height_m * height_m), 1)

    new_vital = VitalSign(
        patient_id=patient_id,
        weight_kg=weight_kg,
        height_cm=height_cm,
        bmi=bmi,
        systolic_bp=systolic_bp,
        diastolic_bp=diastolic_bp,
        heart_rate=heart_rate,
        respiratory_rate=respiratory_rate,
        temperature_c=temperature_c,
        oxygen_saturation=oxygen_saturation,
        glucose_mg_dl=glucose_mg_dl,
        notes=notes,
        recorded_by_id=current_user.id,
    )
    db.add(new_vital)
    db.commit()
    return RedirectResponse(url=f"/vitals/patient/{patient_id}", status_code=303)
