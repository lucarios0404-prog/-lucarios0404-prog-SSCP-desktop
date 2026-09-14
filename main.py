from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pathlib import Path
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.payment import Payment
from app.routers import (
    auth,
    patients,
    appointments,
    payments,
    consultations,
    settings,
    vital_signs,
    lab_results,
    vaccines,
    messages,
    inventory,
    sync,
)
from app.core.deps import get_current_user
import sys

app = FastAPI(title="SSCP Desktop")

# Soporte para PyInstaller (empaquetado .exe) y desarrollo local
BASE_DIR = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Incluir todos los módulos Core y Clínicos
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(appointments.router)
app.include_router(payments.router)
app.include_router(consultations.router)
app.include_router(settings.router)
app.include_router(vital_signs.router)
app.include_router(lab_results.router)
app.include_router(vaccines.router)
app.include_router(messages.router)
app.include_router(inventory.router)
app.include_router(sync.router)

@app.get("/")
async def root(request: Request, current_user = Depends(get_current_user)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request, name="auth/login.html", context={"title": "Iniciar Sesión - SSCP Desktop"}
    )

@app.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if not current_user:
        return RedirectResponse(url="/")
        
    total_patients = db.query(Patient).count()
    total_appointments = db.query(Appointment).count()
    total_consultations = db.query(Consultation).count()
    
    pending_payments = db.query(Payment).filter(Payment.status == "pending").all()
    total_pending_debt = sum(p.total for p in pending_payments)

    recent_appointments = db.query(Appointment).order_by(Appointment.date.desc()).limit(5).all()
    recent_consultations = db.query(Consultation).order_by(Consultation.created_at.desc()).limit(5).all()

    return templates.TemplateResponse(
        request=request, name="dashboard.html", context={
            "title": "Panel Principal - SSCP Desktop",
            "user": current_user,
            "total_patients": total_patients,
            "total_appointments": total_appointments,
            "total_consultations": total_consultations,
            "total_pending_debt": total_pending_debt,
            "recent_appointments": recent_appointments,
            "recent_consultations": recent_consultations,
        }
    )
