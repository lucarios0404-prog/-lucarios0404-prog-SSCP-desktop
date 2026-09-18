from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
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
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"

    # Brute-force gate
    if not _check_and_record_attempt(client_ip):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": f"Demasiados intentos fallidos. Espera {_LOCKOUT_SECONDS} segundos antes de intentarlo de nuevo."},
            status_code=429,
        )

    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        # Para UI, devolver error
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Credenciales incorrectas"}
        )

    # Successful login — clear attempt counter
    _clear_attempts(client_ip)

    access_token = security.create_access_token(data={"email": user.email, "role": user.role})
    
    # Conditional secure flag: only set on HTTPS connections
    is_https = request.url.scheme == "https"

    # Setear cookie y redirigir
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True, 
        max_age=security.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=is_https,
    )
    return response

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response
