import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.core.deps import require_current_user, require_admin
from app.core.security import get_password_hash
from app.core.permissions import AVAILABLE_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS, ROLE_LABELS

router = APIRouter(prefix="/users", tags=["users"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Listado de todos los usuarios registrados en el sistema."""
    users = db.query(User).order_by(User.id.asc()).all()
    
    # Preparar resumen de permisos por usuario
    users_data = []
    for u in users:
        # Calcular permisos efectivos
        effective_perms = []
        if u.role == "admin":
            effective_perms = [p["key"] for p in AVAILABLE_PERMISSIONS]
        elif u.permissions:
            try:
                effective_perms = json.loads(u.permissions)
            except Exception:
                effective_perms = DEFAULT_ROLE_PERMISSIONS.get(u.role, [])
        else:
            effective_perms = DEFAULT_ROLE_PERMISSIONS.get(u.role, [])

        users_data.append({
            "user": u,
            "role_label": ROLE_LABELS.get(u.role, u.role.capitalize()),
            "perm_count": len(effective_perms) if u.role != "admin" else "Total (17)",
            "is_custom": bool(u.permissions and u.role != "admin")
        })

    return templates.TemplateResponse(
        request=request,
        name="users/index.html",
        context={
            "user": current_user,
            "users_data": users_data,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error")
        }
    )

@router.get("/create")
def create_user_form(
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Formulario de creación de un nuevo usuario."""
    return templates.TemplateResponse(
        request=request,
        name="users/create.html",
        context={
            "user": current_user,
            "available_permissions": AVAILABLE_PERMISSIONS,
            "default_permissions_json": json.dumps(DEFAULT_ROLE_PERMISSIONS),
            "role_labels": ROLE_LABELS,
            "error": None
        }
    )

@router.post("/create")
def create_user_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    is_active: bool = Form(True),
    custom_permissions: Optional[List[str]] = Form(None),
    use_custom_perms: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Procesar alta de nuevo usuario con rol y delimitación de permisos."""
    clean_email = email.strip().lower()
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="users/create.html",
            context={
                "user": current_user,
                "available_permissions": AVAILABLE_PERMISSIONS,
                "default_permissions_json": json.dumps(DEFAULT_ROLE_PERMISSIONS),
                "role_labels": ROLE_LABELS,
                "error": f"Ya existe un usuario registrado con el correo '{clean_email}'."
            },
            status_code=400
        )

    # Si se especificaron permisos personalizados
    perms_json = None
    if use_custom_perms == "1" and custom_permissions is not None:
        perms_json = json.dumps(custom_permissions)

    new_user = User(
        name=name.strip(),
        email=clean_email,
        hashed_password=get_password_hash(password),
        role=role,
        permissions=perms_json,
        is_active=is_active
    )
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/users?success=creado", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{user_id}/edit")
def edit_user_form(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Formulario de edición de usuario y permisos."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/users?error=usuario_no_encontrado", status_code=status.HTTP_303_SEE_OTHER)

    # Permisos actuales del usuario
    current_perms = []
    has_custom = False
    if target_user.permissions:
        try:
            current_perms = json.loads(target_user.permissions)
            has_custom = True
        except Exception:
            current_perms = DEFAULT_ROLE_PERMISSIONS.get(target_user.role, [])
    else:
        current_perms = DEFAULT_ROLE_PERMISSIONS.get(target_user.role, [])

    return templates.TemplateResponse(
        request=request,
        name="users/edit.html",
        context={
            "user": current_user,
            "target_user": target_user,
            "current_perms": current_perms,
            "has_custom": has_custom,
            "available_permissions": AVAILABLE_PERMISSIONS,
            "default_permissions_json": json.dumps(DEFAULT_ROLE_PERMISSIONS),
            "role_labels": ROLE_LABELS,
            "error": None
        }
    )

@router.post("/{user_id}/edit")
def edit_user_submit(
    user_id: int,
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: Optional[str] = Form(None),
    role: str = Form(...),
    is_active: Optional[str] = Form(None),
    custom_permissions: Optional[List[str]] = Form(None),
    use_custom_perms: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Guardar modificaciones de usuario y permisos."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/users?error=usuario_no_encontrado", status_code=status.HTTP_303_SEE_OTHER)

    clean_email = email.strip().lower()
    # Verificar colisión de correo con otro usuario
    existing_other = db.query(User).filter(User.email == clean_email, User.id != user_id).first()
    if existing_other:
        return RedirectResponse(url=f"/users/{user_id}/edit?error=email_duplicado", status_code=status.HTTP_303_SEE_OTHER)

    target_user.name = name.strip()
    target_user.email = clean_email
    target_user.role = role

    # Control de estado activo (evitar auto-desactivación del propio admin)
    if current_user.id == target_user.id:
        target_user.is_active = True
    else:
        target_user.is_active = (is_active == "1" or is_active == "true" or is_active == "on")

    # Contraseña opcional al editar
    if password and password.strip():
        target_user.hashed_password = get_password_hash(password.strip())

    # Permisos
    if role == "admin":
        target_user.permissions = None
    elif use_custom_perms == "1" and custom_permissions is not None:
        target_user.permissions = json.dumps(custom_permissions)
    else:
        target_user.permissions = None  # Usar los predeterminados del rol

    db.commit()
    return RedirectResponse(url="/users?success=actualizado", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{user_id}/delete")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Eliminar usuario del sistema."""
    if current_user.id == user_id:
        return RedirectResponse(url="/users?error=no_puedes_eliminarte_a_ti_mismo", status_code=status.HTTP_303_SEE_OTHER)

    target_user = db.query(User).filter(User.id == user_id).first()
    if target_user:
        db.delete(target_user)
        db.commit()
        return RedirectResponse(url="/users?success=eliminado", status_code=status.HTTP_303_SEE_OTHER)
    
    return RedirectResponse(url="/users?error=usuario_no_encontrado", status_code=status.HTTP_303_SEE_OTHER)
