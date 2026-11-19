from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate
from app.core import security, deps
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import time
import threading

router = APIRouter(tags=["auth"])

from app.core.templates import templates

# --- Brute-force protection (in-memory, per-IP) ---
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 30

def _check_and_record_attempt(ip: str) -> bool:
    """Returns True if the login should be allowed, False if locked out."""
    now = time.time()
    cutoff = now - _LOCKOUT_SECONDS
    with _login_lock:
        attempts = [t for t in _login_attempts.get(ip, []) if t > cutoff]
        if len(attempts) >= _MAX_ATTEMPTS:
            return False
        attempts.append(now)
        _login_attempts[ip] = attempts
    return True

def _clear_attempts(ip: str):
    with _login_lock:
        _login_attempts.pop(ip, None)

DEMO_EMAILS = ("admin@sscp.com", "doctor@sscp.com", "secretaria@sscp.com")

def has_custom_user(db: Session) -> bool:
    return db.query(User.id).filter(~User.email.in_(DEMO_EMAILS)).first() is not None

@router.post("/auth/token", response_model=Token)
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_and_record_attempt(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Espera {_LOCKOUT_SECONDS} segundos.",
        )
    uname = (form_data.username or "").strip().lower()
    user = db.query(User).filter(User.email == uname).first() or db.query(User).filter(User.email == (form_data.username or "").strip()).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    _clear_attempts(client_ip)
    access_token = security.create_access_token(data={"email": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login")
async def login(request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    show_setup = not has_custom_user(db)

    # Brute-force gate
    if not _check_and_record_attempt(client_ip):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": f"Demasiados intentos fallidos. Espera {_LOCKOUT_SECONDS} segundos antes de intentarlo de nuevo.", "show_setup_link": show_setup},
            status_code=429,
        )

    form = await request.form()
    username = str(form.get("username") or "").strip().lower()
    password = str(form.get("password") or "")
    remember_me = form.get("remember_me")

    user = db.query(User).filter(User.email == username).first() or db.query(User).filter(User.email == str(form.get("username") or "").strip()).first()
    if not user or not security.verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Credenciales incorrectas", "show_setup_link": show_setup},
            status_code=401,
        )

    if not user.is_active:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Esta cuenta está desactivada. Contacta al administrador.", "show_setup_link": show_setup},
            status_code=403,
        )

    # Successful login — clear attempt counter
    _clear_attempts(client_ip)

    # Extended session duration if remember_me is checked (30 days vs 7 days)
    if remember_me:
        session_delta = timedelta(days=30)
        cookie_max_age = 60 * 60 * 24 * 30
    else:
        session_delta = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
        cookie_max_age = security.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    access_token = security.create_access_token(
        data={"email": user.email, "role": user.role},
        expires_delta=session_delta,
    )
    
    # Conditional secure flag: only set on HTTPS connections
    is_https = request.url.scheme == "https"

    # Setear cookie y redirigir
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True, 
        max_age=cookie_max_age,
        samesite="lax",
        secure=is_https,
    )
    return response

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db), current_user = Depends(deps.get_current_user)):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"title": "Iniciar Sesión - SSCP Desktop", "error": None, "show_setup_link": not has_custom_user(db)}
    )

@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db), current_user = Depends(deps.get_current_user)):
    if has_custom_user(db) and (not current_user or current_user.role != "admin"):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    from app.services.license_service import check_license
    from app.services.supabase_sync_service import SupabaseSyncService
    lic = check_license()
    preset = SupabaseSyncService.load_preset()

    license_doctor_name = (lic.doctor_name if lic and lic.doctor_name else "") or (preset.get("doctor_name") if preset else "")

    return templates.TemplateResponse(
        request=request,
        name="auth/setup.html",
        context={
            "license_doctor_name": license_doctor_name,
            "default_email": "",
            "supabase_preset": preset,
            "error": None,
        }
    )

@router.post("/setup")
def setup_account(
    request: Request,
    role: str = Form("doctor"),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    remember_credentials: str | None = Form(None),
    supabase_token: str | None = Form(None),
    supabase_project_ref: str | None = Form(None),
    supabase_url: str | None = Form(None),
    supabase_anon_key: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(deps.get_current_user),
):
    already_configured = has_custom_user(db)
    if already_configured and (not current_user or current_user.role != "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El asistente inicial ya fue completado. Inicia sesión como Administrador para reconfigurar.",
        )

    name = name.strip()
    email = email.strip().lower()

    if not name or not email:
        return templates.TemplateResponse(
            request=request,
            name="auth/setup.html",
            context={
                "error": "Por favor completa todos los campos requeridos.",
                "license_doctor_name": name,
                "default_email": email,
            },
            status_code=400,
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            request=request,
            name="auth/setup.html",
            context={
                "error": "Las contraseñas no coinciden. Intenta de nuevo.",
                "license_doctor_name": name,
                "default_email": email,
            },
            status_code=400,
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="auth/setup.html",
            context={
                "error": "La contraseña debe tener al menos 6 caracteres.",
                "license_doctor_name": name,
                "default_email": email,
            },
            status_code=400,
        )

    if role not in ("doctor", "secretaria"):
        role = "doctor"

    # Verificar si el usuario ya existe: nunca sobrescribir usuarios reales existentes desde /setup
    user = db.query(User).filter(User.email == email).first()
    if user:
        if already_configured or email not in DEMO_EMAILS:
            return templates.TemplateResponse(
                request=request,
                name="auth/setup.html",
                context={
                    "error": f"Ya existe una cuenta registrada con el correo '{email}'. Inicia sesión o usa otro correo.",
                    "license_doctor_name": name,
                    "default_email": email,
                },
                status_code=400,
            )
        user.name = name
        user.role = role
        user.hashed_password = security.get_password_hash(password)
        user.is_active = True
    else:
        user = User(
            name=name,
            email=email,
            hashed_password=security.get_password_hash(password),
            role=role,
            is_active=True,
        )
        db.add(user)

    # Desactivar credenciales demo por defecto cuando se configura un usuario real del consultorio
    if email not in DEMO_EMAILS:
        for demo_u in db.query(User).filter(User.email.in_(DEMO_EMAILS)).all():
            demo_u.is_active = False

    # Sincronizar configuración local de la clínica según el rol seleccionado en /setup
    from app.models.setting import Setting
    from app.services.relay_service import RelayService
    from app.services.supabase_sync_service import SupabaseSyncService, signal_supabase_sync

    preset = SupabaseSyncService.load_preset()
    preset_cid = (preset.get("clinic_id") or "").strip() if preset else ""

    setting = db.query(Setting).first()
    if role == "doctor":
        if setting:
            setting.doctor_name = name
            setting.station_role = "doctor_principal"
            if not setting.clinic_name or "SSCP" in setting.clinic_name or "Carlos" in setting.clinic_name:
                setting.clinic_name = f"Consultorio {name}"
            if not setting.email or "local" in setting.email or "example" in setting.email:
                setting.email = email
            if preset_cid:
                setting.relay_channel_id = preset_cid
            elif not setting.relay_channel_id or setting.relay_channel_id in ("dr_carlos_mendoza", "dr_carlos_heredia", "dr_especialista", "dr_cristian_garcia"):
                setting.relay_channel_id = None
                db.flush()
                setting.relay_channel_id = RelayService.get_clinic_id(db)
        else:
            setting = Setting(
                clinic_name=f"Consultorio {name}",
                doctor_name=name,
                email=email,
                specialty="Medicina General",
                currency="RD$",
                station_role="doctor_principal",
                relay_channel_id=preset_cid or None,
            )
            db.add(setting)
            db.flush()
            if not setting.relay_channel_id:
                setting.relay_channel_id = RelayService.get_clinic_id(db)
    else:
        # Perfil Secretaría / Recepción
        if setting:
            setting.station_role = "secretaria"
            if preset_cid and not setting.relay_channel_id:
                setting.relay_channel_id = preset_cid
        else:
            setting = Setting(
                clinic_name="Consultorio Médico SSCP",
                doctor_name="Médico Principal",
                email=email,
                specialty="Medicina General",
                currency="RD$",
                station_role="secretaria",
                relay_channel_id=preset_cid or None,
            )
            db.add(setting)
            db.flush()
        if not getattr(user, "assigned_doctor_id", None):
            primary_doc = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
            if primary_doc:
                user.assigned_doctor_id = primary_doc.id

    db.commit()
    db.refresh(user)

    # Paso 3: Provisionar Supabase si se ingresaron datos en /setup, o sincronizar el preset del instalador
    has_supa_input = bool(
        (supabase_token and supabase_token.strip())
        or (supabase_url and supabase_url.strip())
        or (supabase_anon_key and supabase_anon_key.strip())
    )
    if has_supa_input:
        prov = SupabaseSyncService.provision_doctor_supabase(
            db,
            access_token=supabase_token,
            project_ref=supabase_project_ref,
            manual_url=supabase_url,
            manual_anon_key=supabase_anon_key,
        )
        if not prov.get("ok"):
            return templates.TemplateResponse(
                request=request,
                name="auth/setup.html",
                context={
                    "error": f"Perfil guardado, pero falló la conexión con Supabase: {prov.get('error')}",
                    "license_doctor_name": name,
                    "default_email": email,
                    "supabase_preset": SupabaseSyncService.load_preset(),
                },
                status_code=400,
            )
    else:
        cfg = SupabaseSyncService.get_bridge_config(db)
        if cfg.get("enabled"):
            SupabaseSyncService.upsert_station(cfg, force=True, db=db)
            signal_supabase_sync()

    # Iniciar sesión automáticamente
    session_delta = timedelta(days=30) if remember_credentials else timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    cookie_max_age = 60 * 60 * 24 * 30 if remember_credentials else security.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    access_token = security.create_access_token(
        data={"email": user.email, "role": user.role},
        expires_delta=session_delta,
    )
    is_https = request.url.scheme == "https"

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=cookie_max_age,
        samesite="lax",
        secure=is_https,
    )
    return response

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response
