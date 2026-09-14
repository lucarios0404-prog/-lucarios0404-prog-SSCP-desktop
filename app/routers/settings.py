from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime

from app.database import get_db
from app.models.setting import Setting
from app.core.deps import require_current_user

router = APIRouter(prefix="/settings", tags=["settings"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

def get_or_create_settings(db: Session) -> Setting:
    setting = db.query(Setting).first()
    if not setting:
        setting = Setting(
            clinic_name="Centro Médico SSCP",
            doctor_name="Dr. Especialista",
            specialty="Medicina General",
            phone="809-555-0199",
            email="contacto@sscp.local",
            address="Av. Principal #100, Santo Domingo",
            currency="RD$",
            sede_name="Sede Central",
            tailscale_ip="",
            sync_interval_minutes=5,
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting

@router.get("/")
def view_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    setting = get_or_create_settings(db)
    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "user": current_user,
            "setting": setting,
            "saved": False
        }
    )

@router.post("/")
def update_settings(
    request: Request,
    clinic_name: str = Form(...),
    doctor_name: str = Form(None),
    specialty: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    currency: str = Form("RD$"),
    sede_name: str = Form("Sede Central"),
    tailscale_ip: str = Form(None),
    sync_interval_minutes: int = Form(5),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    setting = get_or_create_settings(db)
    setting.clinic_name = clinic_name
    setting.doctor_name = doctor_name
    setting.specialty = specialty
    setting.phone = phone
    setting.email = email
    setting.address = address
    setting.currency = currency
    setting.sede_name = sede_name
    setting.tailscale_ip = tailscale_ip
    setting.sync_interval_minutes = sync_interval_minutes
    setting.updated_at = datetime.utcnow()
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "user": current_user,
            "setting": setting,
            "saved": True
        }
    )
