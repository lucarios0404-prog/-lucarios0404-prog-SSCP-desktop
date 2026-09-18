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

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

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

@router.post("/auth/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
        
    access_token = security.create_access_token(data={"email": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login")
async def login(request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"

    # Brute-force gate
    if not _check_and_record_attempt(client_ip):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": f"Demasiados intentos fallidos. Espera {_LOCKOUT_SECONDS} segundos antes de intentarlo de nuevo."},
            status_code=429,
        )

    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    remember_me = form.get("remember_me")

    user = db.query(User).filter(User.email == username).first()
    if not user or not security.verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Credenciales incorrectas"}
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
def login_page(request: Request, current_user = Depends(deps.get_current_user)):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"title": "Iniciar Sesión - SSCP Desktop", "error": None}
    )

@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    from app.services.license_service import check_license
    lic = check_license()

    license_doctor_name = lic.doctor_name if lic and lic.doctor_name else ""

    return templates.TemplateResponse(
        request=request,
        name="auth/setup.html",
        context={
            "license_doctor_name": license_doctor_name,
            "default_email": "",
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
    db: Session = Depends(get_db),
):
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

    # Verificar si el usuario ya existe o crear uno nuevo
    user = db.query(User).filter(User.email == email).first()
    if user:
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

    # Si es perfil médico, sincronizar los datos de la clínica local
    if role == "doctor":
        from app.models.setting import Setting
        setting = db.query(Setting).first()
        if setting:
            setting.doctor_name = name
            if not setting.email or "local" in setting.email or "example" in setting.email:
                setting.email = email
        else:
            setting = Setting(
                clinic_name=f"Consultorio {name}",
                doctor_name=name,
                email=email,
                specialty="Medicina General",
                currency="RD$",
            )
            db.add(setting)

    db.commit()
    db.refresh(user)

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
    return response
