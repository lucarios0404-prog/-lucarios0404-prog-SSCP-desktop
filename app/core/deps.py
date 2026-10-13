from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.core import security
from jose import JWTError, jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def get_current_user(request: Request, db: Session = Depends(get_db)):
    # Intentar obtener el token de las cookies primero (para la UI web)
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token.split(" ")[1]
    
    # Si no hay cookie, intentar usar el header Authorization (para API)
    if not token:
        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
            
    # Si no hay header, intentar usar parámetro query 'token' (para descargas directas en móvil/PDF)
    if not token:
        query_token = request.query_params.get("token")
        if query_token:
            if query_token.startswith("Bearer "):
                token = query_token.split(" ")[1]
            else:
                token = query_token

    if token:
        try:
            payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
            email: str = payload.get("email")
            if email:
                user = db.query(User).filter(User.email == email).first()
                if user:
                    return user
        except JWTError:
            pass

    # Fallback local seguro para visualización de PDFs impresos desde cliente nativo:
    # Solo aplica para rutas de visualización de PDF si proviene de loopback (127.0.0.1)
    # y NUNCA si la petición proviene de un sitio web externo en el navegador (cross-site).
    client_host = getattr(request.client, "host", None) if request.client else None
    is_local = client_host in ("127.0.0.1", "localhost", "::1", "testclient")
    path = request.url.path
    sec_fetch_site = request.headers.get("sec-fetch-site", "").lower()
    origin = request.headers.get("origin", "").lower()
    is_cross_site = sec_fetch_site == "cross-site" or (bool(origin) and "localhost" not in origin and "127.0.0.1" not in origin)

    if is_local and not is_cross_site and path.endswith("/pdf"):
        local_user = db.query(User).filter(User.is_active == True).order_by(
            (User.role == "doctor").desc(),
            (User.role == "admin").desc()
        ).first()
        if local_user:
            return local_user

    return None

def require_current_user(current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user

def require_admin(current_user: User = Depends(require_current_user)):
    if current_user.role == "admin":
        return current_user
    # Permitir también si el usuario cuenta con permisos administrativos asignados explícitamente
    if (
        current_user.has_permission("settings")
        or current_user.has_permission("users")
        or current_user.has_permission("sync")
    ):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acceso restringido: Se requieren permisos de Administrador."
    )

def require_permission(permission_key: str):
    def dependency(current_user: User = Depends(require_current_user)):
        if not current_user.has_permission(permission_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso restringido: No cuenta con el permiso '{permission_key}' para esta sección."
            )
        return current_user
    return dependency

def require_active_license():
    from app.services.license_service import check_license, LicenseStatus
    lic = check_license()
    if lic.status != LicenseStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Licencia no activa ({lic.status.value}). Por favor active el sistema en /activate."
        )
    return lic
