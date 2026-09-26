import asyncio
from contextlib import asynccontextmanager
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.database import get_db, SessionLocal
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
    quick_prescriptions,
    templates as clinical_templates,
    medical_licenses,
    medical_references,
    reports,
    users,
    data_import,
    permissions,
)
from app.routers.activation import router as activation_router
from app.core.deps import get_current_user

async def run_periodic_sync():
    """Tarea en segundo plano: sincronización periódica cada 5 minutos (Fase 6)"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutos
            from app.services.sync_service import SyncService
            from app.models.setting import Setting
            with SessionLocal() as db:
                setting = db.query(Setting).first()
                remote_url = setting.email if (setting and "http" in (setting.email or "")) else "https://sscp.laxarusdevs.com"
                node_ip = setting.tailscale_ip if setting else None
                await SyncService.background_sync(db, remote_url, node_ip)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Auto-Sync Background] Error no crítico: {e}")

def ensure_schema_migrations(engine):
    """Garantiza la adición segura e idempotente de nuevas columnas a SQLite."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # 1. Migraciones en patients
            res = conn.execute(text("PRAGMA table_info(patients)")).fetchall()
            col_names = [r[1] for r in res]
            if "is_active" not in col_names:
                conn.execute(text("ALTER TABLE patients ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            if "archived_at" not in col_names:
                conn.execute(text("ALTER TABLE patients ADD COLUMN archived_at DATETIME"))
            if "archived_reason" not in col_names:
                conn.execute(text("ALTER TABLE patients ADD COLUMN archived_reason TEXT"))
            if "archived_by_id" not in col_names:
                conn.execute(text("ALTER TABLE patients ADD COLUMN archived_by_id INTEGER"))

            # 2. Migraciones en settings (WhatsApp)
            res_s = conn.execute(text("PRAGMA table_info(settings)")).fetchall()
            s_cols = [r[1] for r in res_s]
            if "whatsapp_doctor_phone" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_doctor_phone TEXT"))
            if "whatsapp_auto_send" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_auto_send BOOLEAN DEFAULT 0"))
            if "whatsapp_auto_hour" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_auto_hour TEXT DEFAULT '08:30'"))
            if "whatsapp_template_reminder" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_template_reminder TEXT"))
            if "whatsapp_template_waiting" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_template_waiting TEXT"))
            if "whatsapp_template_followup" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_template_followup TEXT"))
            if "whatsapp_gateway_status" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_gateway_status TEXT DEFAULT 'disconnected'"))
            if "whatsapp_connected_phone" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN whatsapp_connected_phone TEXT"))

            # 3. Migraciones en appointments (WhatsApp)
            res_a = conn.execute(text("PRAGMA table_info(appointments)")).fetchall()
            a_cols = [r[1] for r in res_a]
            if "whatsapp_reminder_sent" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN whatsapp_reminder_sent BOOLEAN DEFAULT 0"))
            if "whatsapp_reminder_sent_at" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN whatsapp_reminder_sent_at DATETIME"))

            conn.commit()
    except Exception as e:
        print(f"[Schema Migration] Aviso: {e}")

_last_whatsapp_cron_day = None

async def run_whatsapp_scheduled_reminders():
    """Tarea en segundo plano: envía recordatorios automáticos de WhatsApp a la hora configurada."""
    global _last_whatsapp_cron_day
    while True:
        try:
            await asyncio.sleep(60)  # Revisa cada minuto
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            with SessionLocal() as db:
                from app.models.setting import Setting
                from app.models.appointment import Appointment
                from app.services.whatsapp_service import WhatsAppService

                setting = db.query(Setting).first()
                if not setting or not setting.whatsapp_auto_send:
                    continue

                scheduled_time = (setting.whatsapp_auto_hour or "08:30").strip()

                if current_time_str == scheduled_time and _last_whatsapp_cron_day != today_str:
                    _last_whatsapp_cron_day = today_str
                    print(f"[WhatsApp Scheduler] Disparando recordatorios automáticos de las {scheduled_time}...")
                    
                    target_date = now.date() + timedelta(days=1)
                    appts = db.query(Appointment).filter(
                        Appointment.date == target_date,
                        Appointment.status.in_(["Pendiente", "Confirmada"]),
                        Appointment.whatsapp_reminder_sent == False
                    ).all()

                    sent = 0
                    for a in appts:
                        info = WhatsAppService.get_appointment_reminder(db, a)
                        if info["clean_phone"]:
                            WhatsAppService.dispatch_message(info["clean_phone"], info["message"])
                            a.whatsapp_reminder_sent = True
                            a.whatsapp_reminder_sent_at = datetime.utcnow()
                            sent += 1

                    db.commit()
                    print(f"[WhatsApp Scheduler] Recordatorios enviados con éxito: {sent}/{len(appts)} citas.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[WhatsApp Scheduler] Aviso no crítico: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Asegurar creación de tablas e inicialización de catálogo oficial CIE-10
    try:
        from app.database import Base, engine, SessionLocal
        import app.models # Registrar todos los modelos
        Base.metadata.create_all(bind=engine)
        ensure_schema_migrations(engine)
        
        from app.data.cie10_catalog import seed_cie10_catalog
        with SessionLocal() as db:
            seed_cie10_catalog(db)
            from app.core.permissions import seed_permissions_if_empty
            seed_permissions_if_empty(db)
            from app.core.initial_data import seed_initial_data_if_empty
            seed_initial_data_if_empty(db)
    except Exception as e:
        print(f"[Startup Database] Aviso: {e}")

    sync_task = asyncio.create_task(run_periodic_sync())
    wa_task = asyncio.create_task(run_whatsapp_scheduled_reminders())
    yield
    sync_task.cancel()
    wa_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    try:
        await wa_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="SSCP Desktop", lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from app.routers import mobile_api

# Habilitar CORS para permitir solicitudes desde aplicaciones móviles Android y tablets
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Soporte para PyInstaller (empaquetado .exe) y desarrollo local
BASE_DIR = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# === GATE DE LICENCIA (Middleware Global) ===
# El router de activacion siempre esta disponible
app.include_router(activation_router)

# Todos los routers de la aplicacion se registran normalmente
app.include_router(auth.router)
app.include_router(data_import.router)
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
app.include_router(quick_prescriptions.router)
app.include_router(clinical_templates.router)
app.include_router(medical_licenses.router)
app.include_router(medical_references.router)
app.include_router(reports.router)
app.include_router(users.router)
app.include_router(permissions.router)
app.include_router(mobile_api.router)

from fastapi.exceptions import RequestValidationError
from app.services.license_service import check_license, LicenseStatus

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path == "/activate":
        from app.services.license_service import get_machine_id, get_license_mode
        return templates.TemplateResponse(
            request=request,
            name="activation/index.html",
            context={
                "machine_id": get_machine_id(),
                "default_mode": get_license_mode(),
                "error": "Por favor ingresa la clave de licencia antes de activar.",
                "submitted_key": "",
            },
            status_code=200,
        )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.middleware("http")
async def license_gate_middleware(request: Request, call_next):
    # Rutas publicas exentas de validacion de licencia
    exempt_prefixes = ("/activate", "/static", "/favicon.ico", "/docs", "/openapi.json", "/api/mobile/ping", "/download/apk", "/mobile")
    if any(request.url.path.startswith(p) for p in exempt_prefixes):
        return await call_next(request)

    lic = check_license()
    if lic.status != LicenseStatus.ACTIVE:
        accept = request.headers.get("accept", "")
        # Si la peticion es de API pura (solicita json explicitamente sin html/*/*)
        if "application/json" in accept and "text/html" not in accept and "*/*" not in accept:
            return JSONResponse(
                status_code=403,
                content={"detail": "Licencia no activa", "status": lic.status.value}
            )
        return RedirectResponse(url="/activate", status_code=303)

    return await call_next(request)

@app.get("/download/apk")
def download_mobile_apk():
    """Descarga directa del paquete APK compilado para Android."""
    apk_candidates = [
        BASE_DIR / "static" / "downloads" / "SSCP-Mobile.apk",
        BASE_DIR.parent / "sscp-mobile" / "SSCP-Mobile.apk",
        Path(__file__).resolve().parent.parent / "sscp-mobile" / "SSCP-Mobile.apk",
        Path(__file__).resolve().parent / "static" / "downloads" / "SSCP-Mobile.apk",
    ]
    for candidate in apk_candidates:
        if candidate.exists():
            return FileResponse(
                path=str(candidate),
                filename="SSCP-Mobile.apk",
                media_type="application/vnd.android.package-archive"
            )
    return JSONResponse(
        status_code=404,
        content={"error": "El instalador APK de Android se encuentra en proceso de compilación o empaquetado."}
    )

@app.get("/mobile")
def mobile_web_view(request: Request):
    """Interfaz web móvil optimizada para teléfonos y tablets (Doctor y Secretaria)."""
    return templates.TemplateResponse(
        request=request,
        name="mobile/index.html",
        context={"request": request}
    )

@app.get("/")
async def root(request: Request, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user:
        return RedirectResponse(url="/dashboard")

    # Si es una instalación limpia o sin usuario personalizado, redirigir al setup inicial
    from app.models.user import User
    demo_emails = ["admin@sscp.com", "doctor@sscp.com", "secretaria@sscp.com"]
    has_custom_user = db.query(User).filter(~User.email.in_(demo_emails)).first() is not None

    if not has_custom_user:
        return RedirectResponse(url="/setup")

    return RedirectResponse(url="/login")

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

    # Pacientes en sala de espera hoy (notificados por secretaría para atención inmediata)
    today = date.today()
    waiting_patients = db.query(Appointment).filter(
        Appointment.date == today,
        Appointment.status == "En Espera"
    ).order_by(Appointment.start_time.asc()).all()

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
            "waiting_patients": waiting_patients,
        }
    )
