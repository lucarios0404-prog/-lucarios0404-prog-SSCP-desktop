import asyncio
from contextlib import asynccontextmanager
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

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
    services,
    insurance_preauthorizations,
    reception,
    relay,
)
from app.routers.activation import router as activation_router
from app.core.deps import get_current_user

async def run_periodic_sync():
    """Desktop es 100% independiente y local. Sincronización automática con la web desactivada."""
    return


async def run_peer_continuous_sync():
    """Tarea en segundo plano: sincronización P2P desatendida entre Doctor y Secretaría cada 45s."""
    while True:
        try:
            await asyncio.sleep(45)
            from app.services.sync_service import SyncService
            from app.models.setting import Setting
            with SessionLocal() as db:
                setting = db.query(Setting).first()
                if setting and setting.central_station_url and setting.central_station_url.strip():
                    peer_url = setting.central_station_url.strip()
                    await SyncService.sync_with_peer(db, peer_url)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


def _execute_relay_sync_cycle():
    """Ejecuta un ciclo de sincronización incremental con Supabase en hilo de fondo sin bloquear la UI."""
    from app.services.supabase_sync_service import SupabaseSyncService
    from app.services.license_service import check_license, LicenseStatus
    try:
        if check_license().status != LicenseStatus.ACTIVE:
            return
        SupabaseSyncService.run_incremental_cycle()
    except Exception:
        pass


async def run_relay_continuous_sync():
    """Tarea en segundo plano: mantiene sincronizado incrementalmente SQLite y el Puente Supabase cada 20s o al guardar cambios."""
    from app.services.supabase_sync_service import wait_for_sync_signal
    # Ejecutar primer ciclo rapido al iniciar para publicar IP actual y absorber pendientes
    try:
        await asyncio.sleep(2)
        await asyncio.to_thread(_execute_relay_sync_cycle)
    except asyncio.CancelledError:
        return
    except Exception:
        pass

    while True:
        try:
            await asyncio.to_thread(wait_for_sync_signal, 20.0)
            await asyncio.to_thread(_execute_relay_sync_cycle)
        except asyncio.CancelledError:
            break
        except Exception:
            pass



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
            if "insurance_name" not in col_names:
                conn.execute(text("ALTER TABLE patients ADD COLUMN insurance_name TEXT DEFAULT 'Privado'"))
            if "insurance_number" not in col_names:
                conn.execute(text("ALTER TABLE patients ADD COLUMN insurance_number TEXT"))
            if "doctor_id" not in col_names:
                conn.execute(text("ALTER TABLE patients ADD COLUMN doctor_id INTEGER"))

            res_u = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            u_cols = [r[1] for r in res_u]
            if "assigned_doctor_id" not in u_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN assigned_doctor_id INTEGER"))

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
            if "doctor_logo_path" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN doctor_logo_path TEXT"))
            if "doctor_exequatur" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN doctor_exequatur TEXT DEFAULT '165-10'"))
            if "doctor_cedula" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN doctor_cedula TEXT DEFAULT '001-1418378-3'"))
            if "station_role" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN station_role TEXT DEFAULT 'doctor_principal'"))
            if "central_station_url" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN central_station_url TEXT"))
            if "relay_channel_id" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN relay_channel_id TEXT"))
            if "station_secret" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN station_secret TEXT"))
            if "supabase_url" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN supabase_url TEXT"))
            if "supabase_anon_key" not in s_cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN supabase_anon_key TEXT"))


            # 3. Migraciones en appointments (Turnos, Servicios, WhatsApp, Doctor)
            res_a = conn.execute(text("PRAGMA table_info(appointments)")).fetchall()
            a_cols = [r[1] for r in res_a]
            if "doctor_id" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN doctor_id INTEGER"))
            if "queue_number" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN queue_number INTEGER"))
            if "service_id" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN service_id INTEGER"))
            if "price" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN price FLOAT DEFAULT 0.0"))
            if "whatsapp_reminder_sent" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN whatsapp_reminder_sent BOOLEAN DEFAULT 0"))
            if "whatsapp_reminder_sent_at" not in a_cols:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN whatsapp_reminder_sent_at DATETIME"))

            # 4. Migraciones en payments (ARS y Talonario de Servicios)
            res_p = conn.execute(text("PRAGMA table_info(payments)")).fetchall()
            p_cols = [r[1] for r in res_p]
            if "insurance_name" not in p_cols:
                conn.execute(text("ALTER TABLE payments ADD COLUMN insurance_name TEXT DEFAULT 'Privado'"))
            if "service_id" not in p_cols:
                conn.execute(text("ALTER TABLE payments ADD COLUMN service_id INTEGER"))

            # 5. Migraciones en consultations (Historia Clínica Unificada v1.2.0)
            res_c = conn.execute(text("PRAGMA table_info(consultations)")).fetchall()
            c_cols = [r[1] for r in res_c]
            if "clinical_history" not in c_cols:
                conn.execute(text("ALTER TABLE consultations ADD COLUMN clinical_history TEXT"))
            if "is_first_visit" not in c_cols:
                conn.execute(text("ALTER TABLE consultations ADD COLUMN is_first_visit BOOLEAN DEFAULT 0"))
            if "edit_version" not in c_cols:
                conn.execute(text("ALTER TABLE consultations ADD COLUMN edit_version INTEGER DEFAULT 1"))

            # 6. Tabla lab_orders (Solicitud de Laboratorios Digital v1.2.0)
            from app.models.lab_order import LabOrder
            LabOrder.__table__.create(bind=conn, checkfirst=True)

            # 7. Tabla insurance_preauthorizations (Historia Clínica & Pre-Autorizaciones ARS)
            from app.models.insurance_preauthorization import InsurancePreauthorization
            InsurancePreauthorization.__table__.create(bind=conn, checkfirst=True)

            conn.commit()
    except Exception as e:
        print(f"[Schema Migration] Aviso: {e}")

_last_whatsapp_cron_day = None


def check_pending_daily_whatsapp_reminders(target_date=None) -> int:
    """
    Revisa recordatorios pendientes del día siguiente sin marcar envíos falsos.
    En Modo 1-Clic Real solo el usuario confirma el envío real desde WhatsApp.
    """
    from sqlalchemy import or_
    from app.models.appointment import Appointment

    if target_date is None:
        target_date = datetime.now().date() + timedelta(days=1)

    with SessionLocal() as db:
        count = (
            db.query(Appointment)
            .filter(
                Appointment.date == target_date,
                Appointment.status.in_(["Pendiente", "Confirmada"]),
                or_(
                    Appointment.whatsapp_reminder_sent == False,
                    Appointment.whatsapp_reminder_sent == None,
                ),
            )
            .count()
        )
    return int(count)


async def run_whatsapp_scheduled_reminders():
    """Tarea en segundo plano: registra en log cuántos recordatorios están pendientes para la Cola 1-Clic."""
    global _last_whatsapp_cron_day
    while True:
        try:
            await asyncio.sleep(60)  # Revisa cada minuto
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            with SessionLocal() as db:
                from app.models.setting import Setting

                setting = db.query(Setting).first()
                scheduled_time = ((setting.whatsapp_auto_hour if setting else None) or "08:30").strip()

            if current_time_str == scheduled_time and _last_whatsapp_cron_day != today_str:
                _last_whatsapp_cron_day = today_str
                tomorrow = now.date() + timedelta(days=1)
                pending_count = check_pending_daily_whatsapp_reminders(tomorrow)
                if pending_count > 0:
                    print(
                        f"[WhatsApp 1-Clic] {pending_count} recordatorios pendientes para mañana ({tomorrow}). "
                        "Ábrelos desde Citas -> Cola WhatsApp."
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[WhatsApp 1-Clic] Aviso no crítico: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Asegurar integridad de SQLite, creación de tablas e inicialización de catálogo oficial CIE-10
    def _init_and_seed_db():
        from app.database import Base, engine, SessionLocal, DB_PATH, repair_sqlite_if_malformed
        repair_sqlite_if_malformed(DB_PATH, reset_if_unrecoverable=True)
        import app.models # Registrar todos los modelos
        try:
            Base.metadata.create_all(bind=engine)
            ensure_schema_migrations(engine)
        except Exception as init_exc:
            if "malformed" in str(init_exc).lower() or "databaseerror" in str(init_exc).lower():
                try:
                    engine.dispose()
                except Exception:
                    pass
                repair_sqlite_if_malformed(DB_PATH, reset_if_unrecoverable=True)
                Base.metadata.create_all(bind=engine)
                ensure_schema_migrations(engine)
            else:
                raise

        from app.data.cie10_catalog import seed_cie10_catalog
        with SessionLocal() as db:
            seed_cie10_catalog(db)
            from app.core.permissions import seed_permissions_if_empty
            seed_permissions_if_empty(db)
            from app.core.initial_data import seed_initial_data_if_empty
            seed_initial_data_if_empty(db)
            from app.data.services_catalog import seed_services_if_empty
            seed_services_if_empty(db)

    try:
        _init_and_seed_db()
    except Exception as e:
        print(f"[Startup Database] Aviso: {e}")

    peer_sync_task = asyncio.create_task(run_peer_continuous_sync())
    relay_sync_task = asyncio.create_task(run_relay_continuous_sync())
    wa_task = asyncio.create_task(run_whatsapp_scheduled_reminders())
    yield
    peer_sync_task.cancel()
    relay_sync_task.cancel()
    wa_task.cancel()
    try:
        await peer_sync_task
    except asyncio.CancelledError:
        pass
    try:
        await relay_sync_task
    except asyncio.CancelledError:
        pass
    try:
        await wa_task
    except asyncio.CancelledError:
        pass
    try:
        from sqlalchemy import text
        from app.database import engine
        with engine.connect() as conn:
            conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        engine.dispose()
    except Exception:
        pass

from app.version import SUITE_VERSION
app = FastAPI(title="SSCP Desktop", version=SUITE_VERSION, lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from app.routers import mobile_api

# CORS restringido: permite aplicaciones móviles locales, Electron y la red local de la clínica
# Evita que sitios web de terceros en el navegador puedan sondear la API local del consultorio
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|100\.\d+\.\d+\.\d+|.*\.laxarusdevs\.com)(:\d+)?|https?://appassets\.androidplatform\.net|app://.*|capacitor://.*|file://.*)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    allow_private_network=True,
)

@app.middleware("http")
async def add_private_network_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

# Soporte para PyInstaller (empaquetado .exe) y desarrollo local
BASE_DIR = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
from app.core.templates import templates

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
app.include_router(services.router)
app.include_router(insurance_preauthorizations.router)
app.include_router(reception.router)
app.include_router(relay.router)

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

from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        accept = request.headers.get("accept", "")
        if "text/html" in accept or "*/*" in accept:
            return templates.TemplateResponse(
                request=request,
                name="errors/404.html",
                context={"request": request},
                status_code=404
            )
        return JSONResponse(status_code=404, content={"detail": exc.detail})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    accept = request.headers.get("accept", "")
    if "text/html" in accept or "*/*" in accept:
        return templates.TemplateResponse(
            request=request,
            name="errors/500.html",
            context={
                "request": request,
                "error_detail": str(exc) if "NoneType" in str(exc) or "database" in str(exc).lower() else "Ocurrió un error inesperado al procesar la solicitud."
            },
            status_code=500
        )
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor", "error": str(exc)})


@app.middleware("http")
async def license_gate_middleware(request: Request, call_next):
    # Rutas publicas exentas de validacion de licencia
    exempt_prefixes = ("/activate", "/static", "/favicon.ico", "/docs", "/openapi.json", "/api/mobile/ping", "/api/internal/graceful-shutdown", "/download/apk", "/mobile")
    if any(request.url.path.startswith(p) for p in exempt_prefixes):
        return await call_next(request)

    lic = check_license()
    if lic.status != LicenseStatus.ACTIVE:
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Licencia no activa", "status": lic.status.value}
            )
        accept = request.headers.get("accept", "")
        # Si la peticion es de API pura (solicita json explicitamente sin html/*/*)
        if "application/json" in accept and "text/html" not in accept:
            return JSONResponse(
                status_code=403,
                content={"detail": "Licencia no activa", "status": lic.status.value}
            )
        return RedirectResponse(url="/activate", status_code=303)

    return await call_next(request)

@app.post("/api/internal/graceful-shutdown")
def internal_graceful_shutdown(request: Request):
    """Ejecuta sync final, checkpoint WAL limpio y finaliza el backend ante cierre desde Electron."""
    import hmac
    import os
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return JSONResponse(status_code=403, content={"detail": "Solo permitido desde localhost."})
    expected_ipc = os.environ.get("SSCP_IPC_SECRET", "").strip()
    if expected_ipc:
        provided_ipc = request.headers.get("X-SSCP-IPC-Secret", "").strip()
        if not provided_ipc or not hmac.compare_digest(provided_ipc, expected_ipc):
            return JSONResponse(status_code=403, content={"detail": "Secreto IPC inválido."})
    try:
        from app.database import SessionLocal
        from app.services.supabase_sync_service import SupabaseSyncService
        db = SessionLocal()
        try:
            cfg = SupabaseSyncService.get_bridge_config(db)
            if cfg.get("enabled"):
                SupabaseSyncService.run_incremental_cycle(db)
        finally:
            db.close()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        from app.database import engine
        with engine.connect() as conn:
            conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        engine.dispose()
    except Exception:
        pass
    import threading
    threading.Timer(0.15, lambda: os._exit(0)).start()
    return {"ok": True}


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

@app.get("/mobile/chart.min.js")
def mobile_chart_js():
    """Sirve chart.min.js localmente para la vista /mobile sin depender de CDN externo."""
    chart_path = BASE_DIR / "static" / "js" / "chart.min.js"
    if chart_path.exists():
        return FileResponse(path=str(chart_path), media_type="application/javascript")
    return JSONResponse(status_code=404, content={"error": "chart.min.js no encontrado"})

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
    if not current_user or not current_user.is_active:
        return RedirectResponse(url="/")
        
    from app.routers.patients import resolve_current_doctor_id
    doc_id = resolve_current_doctor_id(db, current_user)
    today = date.today()

    # Auto-reconciliación: Si un paciente ya tuvo consulta médica asociada o del día, marcar la cita como Completada
    try:
        from app.services.appointment_reconciliation import reconcile_completed_appointments
        if reconcile_completed_appointments(db) > 0:
            db.commit()
            try:
                from app.services.supabase_sync_service import signal_supabase_sync
                signal_supabase_sync()
            except Exception:
                pass
    except Exception:
        pass

    pat_q = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None))
    appt_q = db.query(Appointment).filter(
        Appointment.status.in_(["Pendiente", "Confirmada", "En Espera", "En espera", "en espera"]),
        Appointment.date >= today
    )
    cons_q = db.query(Consultation)

    if doc_id:
        pat_q = pat_q.filter(or_(Patient.doctor_id == doc_id, Patient.doctor_id == None))
        appt_q = appt_q.filter(or_(Appointment.doctor_id == doc_id, Appointment.doctor_id == None))
        cons_q = cons_q.filter(or_(Consultation.doctor_id == doc_id, Consultation.doctor_id == None))

    total_patients = pat_q.count()
    total_appointments = appt_q.count()
    total_consultations = cons_q.count()
    
    pending_payments = db.query(Payment).filter(Payment.status == "pending").all()
    total_pending_debt = sum(p.total for p in pending_payments)

    # Próximas Citas: solo citas futuras pendientes/confirmadas (sin mezclar con sala de espera de hoy)
    tomorrow = today + timedelta(days=1)
    recent_appts_q = db.query(Appointment).filter(
        Appointment.status.in_(["Pendiente", "Confirmada", "Reagendada"]),
        Appointment.date >= tomorrow
    )
    if doc_id:
        recent_appts_q = recent_appts_q.filter(or_(Appointment.doctor_id == doc_id, Appointment.doctor_id == None))
    recent_appointments = recent_appts_q.order_by(Appointment.date.asc(), Appointment.start_time.asc()).limit(5).all()

    recent_cons_q = db.query(Consultation)
    if doc_id:
        recent_cons_q = recent_cons_q.filter(or_(Consultation.doctor_id == doc_id, Consultation.doctor_id == None))
    recent_consultations = recent_cons_q.order_by(Consultation.created_at.desc()).limit(5).all()

    # Pacientes en sala de espera hoy (notificados por secretaría para atención inmediata)
    waiting_patients_q = db.query(Appointment).filter(
        Appointment.date == today,
        Appointment.status.in_(["En Espera", "En espera", "en espera"])
    )
    if doc_id:
        waiting_patients_q = waiting_patients_q.filter(or_(Appointment.doctor_id == doc_id, Appointment.doctor_id == None))
    waiting_patients = waiting_patients_q.order_by(Appointment.start_time.asc(), Appointment.id.asc()).all()

    from app.routers.appointments import assign_next_queue_number
    from sqlalchemy.sql import func
    needs_commit = False
    # Asegurar turnos secuenciales limpios sin números duplicados
    seen_queues = set()
    for idx, wp in enumerate(waiting_patients, start=1):
        if not wp.queue_number or wp.queue_number in seen_queues:
            wp.queue_number = idx
            needs_commit = True
        seen_queues.add(wp.queue_number)
        if not wp.is_paid:
            pay = db.query(Payment).filter(
                Payment.patient_id == wp.patient_id,
                Payment.status == "paid",
                func.date(Payment.created_at) == today
            ).first()
            if pay:
                pay.appointment_id = wp.id
                needs_commit = True
    if needs_commit:
        db.commit()

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
