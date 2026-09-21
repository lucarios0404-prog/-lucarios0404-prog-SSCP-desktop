from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime
import shutil
import os

from app.database import get_db, DB_PATH
from app.models.setting import Setting
from app.core.deps import require_admin
from app.services.whatsapp_gateway import gateway_manager
from app.services.whatsapp_service import (
    WhatsAppService,
    DEFAULT_REMINDER_TEMPLATE,
    DEFAULT_WAITING_TEMPLATE,
    DEFAULT_FOLLOWUP_TEMPLATE,
)

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
            whatsapp_doctor_phone="809-555-0199",
            whatsapp_auto_send=False,
            whatsapp_auto_hour="08:30",
            whatsapp_template_reminder=DEFAULT_REMINDER_TEMPLATE,
            whatsapp_template_waiting=DEFAULT_WAITING_TEMPLATE,
            whatsapp_template_followup=DEFAULT_FOLLOWUP_TEMPLATE,
            whatsapp_gateway_status="disconnected"
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting

@router.get("/")
def view_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    setting = get_or_create_settings(db)
    gw_status = gateway_manager.get_status()
    
    # Sincronizar estado en DB si hubo cambios
    if setting.whatsapp_gateway_status != gw_status["status"]:
        setting.whatsapp_gateway_status = gw_status["status"]
        setting.whatsapp_connected_phone = gw_status["connected_phone"]
        db.commit()

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "user": current_user,
            "setting": setting,
            "gateway_status": gw_status,
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
    # Campos WhatsApp
    whatsapp_doctor_phone: str = Form(None),
    whatsapp_auto_send: bool = Form(False),
    whatsapp_auto_hour: str = Form("08:30"),
    whatsapp_template_reminder: str = Form(None),
    whatsapp_template_waiting: str = Form(None),
    whatsapp_template_followup: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
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
    
    # Guardar campos WhatsApp
    setting.whatsapp_doctor_phone = whatsapp_doctor_phone
    setting.whatsapp_auto_send = whatsapp_auto_send
    setting.whatsapp_auto_hour = whatsapp_auto_hour or "08:30"
    if whatsapp_template_reminder:
        setting.whatsapp_template_reminder = whatsapp_template_reminder
    if whatsapp_template_waiting:
        setting.whatsapp_template_waiting = whatsapp_template_waiting
    if whatsapp_template_followup:
        setting.whatsapp_template_followup = whatsapp_template_followup

    setting.updated_at = datetime.utcnow()
    db.commit()

    gw_status = gateway_manager.get_status()

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "user": current_user,
            "setting": setting,
            "gateway_status": gw_status,
            "saved": True
        }
    )

UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_SIZE_MB = 5

# Magic bytes for allowed image formats
_MAGIC_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"RIFF": ".webp",  # WebP starts with RIFF....WEBP
}


def _detect_image_type(content: bytes) -> str | None:
    """Returns extension if content matches a known image magic signature, else None."""
    for magic, ext in _MAGIC_SIGNATURES.items():
        if content.startswith(magic):
            # Extra check for WebP: bytes 8-12 must be 'WEBP'
            if ext == ".webp" and content[8:12] != b"WEBP":
                continue
            return ext
    return None


@router.post("/upload-logo")
async def upload_doctor_logo(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """
    Carga del logo/membrete del doctor para incluir en recetas, licencias y reportes PDF.
    Acepta PNG, JPG o WEBP (máx. 5 MB). Guarda en static/uploads/doctor_logo.{ext}.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no permitido. Use PNG, JPG o WEBP.")

    contents = await file.read()
    if len(contents) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera el límite de {MAX_SIZE_MB} MB.")

    # Validate actual file content via magic bytes (prevent extension spoofing)
    detected_ext = _detect_image_type(contents)
    if not detected_ext:
        raise HTTPException(
            status_code=400,
            detail="El archivo no es una imagen válida. Por favor sube un PNG, JPG o WEBP real."
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = UPLOAD_DIR / f"doctor_logo{detected_ext}"

    with open(dest_path, "wb") as f:
        f.write(contents)

    setting = get_or_create_settings(db)
    setting.doctor_logo_path = str(dest_path)
    setting.updated_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url="/settings?logo_saved=1", status_code=303)

# ---------------------------------------------------------
# ENDPOINTS ESPECÍFICOS DEL GATEWAY DE WHATSAPP
# ---------------------------------------------------------

@router.get("/whatsapp/status")
def get_whatsapp_gateway_status(
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Retorna el estado de conexión actual del gateway y estadísticas."""
    status = gateway_manager.get_status()
    return JSONResponse(content=status)

@router.post("/whatsapp/generate-qr")
def generate_whatsapp_qr(
    phone: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Genera un nuevo código QR dinámico para vinculación de WhatsApp."""
    setting = get_or_create_settings(db)
    doctor_phone = phone or setting.whatsapp_doctor_phone or setting.phone
    qr_data = gateway_manager.generate_pairing_qr(custom_phone=doctor_phone)
    
    setting.whatsapp_gateway_status = "pairing"
    db.commit()
    
    return JSONResponse(content=qr_data)

@router.post("/whatsapp/confirm-pairing")
def confirm_whatsapp_pairing(
    phone: str = Form("+1 (809) 555-0199"),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Confirma la vinculación del dispositivo (tras escanear el QR)."""
    result = gateway_manager.confirm_pairing(phone=phone)
    
    setting = get_or_create_settings(db)
    setting.whatsapp_gateway_status = "connected"
    setting.whatsapp_connected_phone = phone
    db.commit()

    return JSONResponse(content=result)

@router.post("/whatsapp/disconnect")
def disconnect_whatsapp_gateway(
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Desvincula la sesión activa del Gateway de WhatsApp."""
    result = gateway_manager.disconnect()
    
    setting = get_or_create_settings(db)
    setting.whatsapp_gateway_status = "disconnected"
    setting.whatsapp_connected_phone = None
    db.commit()

    return JSONResponse(content=result)

@router.post("/whatsapp/send-test")
def send_whatsapp_test_message(
    phone: str = Form(...),
    message: str = Form("Mensaje de prueba desde SSCP Desktop: La integración de WhatsApp está funcionando correctamente."),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Prueba el envío de un mensaje de WhatsApp (vía gateway o wa.me)."""
    result = WhatsAppService.dispatch_message(phone=phone, message=message)
    return JSONResponse(content=result)

@router.get("/backup/export")
def export_backup(
    current_user = Depends(require_admin)
):
    """Genera y descarga una copia de seguridad exacta de la base de datos SQLite."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Archivo de base de datos no encontrado.")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"SSCP_Backup_{timestamp}.db"
    return FileResponse(
        path=str(DB_PATH),
        filename=backup_filename,
        media_type="application/x-sqlite3"
    )

@router.post("/backup/restore")
async def restore_backup(
    request: Request,
    backup_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Restaura una copia de seguridad SQLite previa verificación de integridad."""
    content = await backup_file.read()
    if len(content) < 16 or not content.startswith(b"SQLite format 3\x00"):
        setting = get_or_create_settings(db)
        return templates.TemplateResponse(
            request=request,
            name="settings/index.html",
            context={
                "user": current_user,
                "setting": setting,
                "gateway_status": gateway_manager.get_status(),
                "error": "El archivo proporcionado no es una base de datos SQLite válida de SSCP."
            },
            status_code=400
        )

    # 1. Crear copia de seguridad preventiva del estado actual
    if DB_PATH.exists():
        pre_restore_bak = DB_PATH.with_suffix(".pre_restore.bak")
        try:
            shutil.copy2(DB_PATH, pre_restore_bak)
        except Exception:
            pass

    # 2. Escribir el nuevo contenido en DB_PATH
    with open(DB_PATH, "wb") as f:
        f.write(content)

    return RedirectResponse(url="/settings?backup_restored=1", status_code=303)

