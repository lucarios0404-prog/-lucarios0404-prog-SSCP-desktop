import asyncio
from contextlib import asynccontextmanager
import sys
from pathlib import Path
from datetime import date
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
)
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
            conn.commit()
    except Exception as e:
        print(f"[Schema Migration] Aviso: {e}")

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
    except Exception as e:
        print(f"[Startup Database] Aviso: {e}")

    sync_task = asyncio.create_task(run_periodic_sync())
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="SSCP Desktop", lifespan=lifespan)

# Soporte para PyInstaller (empaquetado .exe) y desarrollo local
BASE_DIR = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Incluir todos los módulos Core, Clínicos y de Productividad (Fase 4 y Fase 6)
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
