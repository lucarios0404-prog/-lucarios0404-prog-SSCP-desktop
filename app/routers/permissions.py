import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from fastapi import status

from app.database import get_db
from app.models.user import User
from app.models.permission_catalog import PermissionCatalog
from app.core.deps import require_admin
from app.core.permissions import (
    get_all_permissions,
    get_permissions_by_category,
    AVAILABLE_PERMISSIONS,
    invalidate_permissions_cache,
)

router = APIRouter(prefix="/permissions", tags=["permissions"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/")
def list_permissions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Panel de gestión de Áreas y Permisos del sistema."""
    grouped = get_permissions_by_category(db)

    # Contar usuarios con cada permiso para mostrar en el panel
    all_users = db.query(User).filter(User.is_active == True).all()
    usage_count: dict[str, int] = {}
    for u in all_users:
        if u.role == "admin":
            for p in AVAILABLE_PERMISSIONS:
                usage_count[p["key"]] = usage_count.get(p["key"], 0) + 1
        elif u.permissions:
            try:
                perms = json.loads(u.permissions)
                for pk in perms:
                    usage_count[pk] = usage_count.get(pk, 0) + 1
            except Exception:
                pass

    return templates.TemplateResponse(
        request=request,
        name="permissions/index.html",
        context={
            "user": current_user,
            "grouped": grouped,
            "usage_count": usage_count,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/create")
def create_permission_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Formulario para crear un nuevo permiso."""
    existing_categories = sorted(
        {p["category"] for p in get_all_permissions(db)}
    )
    return templates.TemplateResponse(
        request=request,
        name="permissions/create.html",
        context={
            "user": current_user,
            "categories": existing_categories,
            "error": None,
        },
    )


@router.post("/create")
def create_permission_submit(
    request: Request,
    key: str = Form(...),
    label: str = Form(...),
    description: Optional[str] = Form(""),
    category: str = Form(...),
    new_category: Optional[str] = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guardar nuevo permiso en la BD."""
    # Usar categoría nueva si se especificó
    final_category = new_category.strip() if new_category and new_category.strip() else category.strip()
    clean_key = key.strip().lower().replace(" ", "_")

    existing_categories = sorted({p["category"] for p in get_all_permissions(db)})

    if not clean_key or not label.strip() or not final_category:
        return templates.TemplateResponse(
            request=request,
            name="permissions/create.html",
            context={
                "user": current_user,
                "categories": existing_categories,
                "error": "La clave, etiqueta y área son requeridos.",
            },
            status_code=400,
        )

    # Verificar clave única
    existing = db.query(PermissionCatalog).filter(PermissionCatalog.key == clean_key).first()
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="permissions/create.html",
            context={
                "user": current_user,
                "categories": existing_categories,
                "error": f"Ya existe un permiso con la clave '{clean_key}'. Las claves deben ser únicas.",
            },
            status_code=400,
        )

    # Determinar sort_order al final de la categoría
    last = (
        db.query(PermissionCatalog)
        .filter(PermissionCatalog.category == final_category)
        .order_by(PermissionCatalog.sort_order.desc())
        .first()
    )
    next_order = (last.sort_order + 1) if last else 0

    record = PermissionCatalog(
        key=clean_key,
        label=label.strip(),
        description=description.strip() if description else "",
        category=final_category,
        sort_order=next_order,
        is_active=True,
    )
    db.add(record)
    db.commit()
    invalidate_permissions_cache()

    return RedirectResponse(url="/permissions?success=creado", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{perm_id}/edit")
def edit_permission_form(
    perm_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Formulario de edición de un permiso."""
    record = db.query(PermissionCatalog).filter(PermissionCatalog.id == perm_id).first()
    if not record:
        return RedirectResponse(url="/permissions?error=permiso_no_encontrado", status_code=status.HTTP_303_SEE_OTHER)

    existing_categories = sorted({p["category"] for p in get_all_permissions(db)})

    # Contar usuarios que usan este permiso
    all_users = db.query(User).filter(User.is_active == True).all()
    usage = sum(
        1 for u in all_users
        if u.role == "admin"
        or (u.permissions and record.key in (json.loads(u.permissions) if u.permissions else []))
    )

    return templates.TemplateResponse(
        request=request,
        name="permissions/edit.html",
        context={
            "user": current_user,
            "perm": record,
            "categories": existing_categories,
            "usage_count": usage,
            "error": None,
        },
    )


@router.post("/{perm_id}/edit")
def edit_permission_submit(
    perm_id: int,
    request: Request,
    label: str = Form(...),
    description: Optional[str] = Form(""),
    category: str = Form(...),
    new_category: Optional[str] = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Guardar cambios del permiso."""
    record = db.query(PermissionCatalog).filter(PermissionCatalog.id == perm_id).first()
    if not record:
        return RedirectResponse(url="/permissions?error=permiso_no_encontrado", status_code=status.HTTP_303_SEE_OTHER)

    final_category = new_category.strip() if new_category and new_category.strip() else category.strip()

    record.label = label.strip()
    record.description = description.strip() if description else ""
    record.category = final_category
    db.commit()
    invalidate_permissions_cache()

    return RedirectResponse(url="/permissions?success=actualizado", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{perm_id}/toggle")
def toggle_permission(
    perm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Activar o desactivar un permiso sin eliminarlo."""
    record = db.query(PermissionCatalog).filter(PermissionCatalog.id == perm_id).first()
    if not record:
        return RedirectResponse(url="/permissions?error=permiso_no_encontrado", status_code=status.HTTP_303_SEE_OTHER)

    record.is_active = not record.is_active
    db.commit()
    invalidate_permissions_cache()

    action = "activado" if record.is_active else "desactivado"
    return RedirectResponse(url=f"/permissions?success={action}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{perm_id}/delete")
def delete_permission(
    perm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Eliminar permiso si no está en uso por ningún usuario personalizado."""
    record = db.query(PermissionCatalog).filter(PermissionCatalog.id == perm_id).first()
    if not record:
        return RedirectResponse(url="/permissions?error=permiso_no_encontrado", status_code=status.HTTP_303_SEE_OTHER)

    # Verificar si algún usuario no-admin tiene este permiso personalizado
    users_with_perm = db.query(User).filter(User.permissions.isnot(None)).all()
    in_use = any(
        record.key in (json.loads(u.permissions) if u.permissions else [])
        for u in users_with_perm
    )

    if in_use:
        return RedirectResponse(
            url=f"/permissions?error=en_uso",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.delete(record)
    db.commit()
    invalidate_permissions_cache()
    return RedirectResponse(url="/permissions?success=eliminado", status_code=status.HTTP_303_SEE_OTHER)

