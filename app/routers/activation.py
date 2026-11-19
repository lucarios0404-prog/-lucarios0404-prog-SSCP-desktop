"""app/routers/activation.py — Pantalla de activacion de licencia."""
from typing import Optional
from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.templates import templates
from app.core.deps import get_current_user
from app.database import get_db
router = APIRouter()


def _can_manage_active_license(current_user) -> bool:
    return bool(
        current_user
        and current_user.is_active
        and current_user.role in ("admin", "doctor")
        and current_user.has_permission("settings")
    )


@router.get("/activate", response_class=HTMLResponse)
async def activation_page(request: Request, db: Session = Depends(get_db)):
    from app.services.license_service import get_machine_id, get_license_mode, check_license, LicenseStatus
    if check_license().status == LicenseStatus.ACTIVE:
        current_user = get_current_user(request, db)
        if not _can_manage_active_license(current_user):
            return RedirectResponse(url="/", status_code=303)
    machine_id = get_machine_id()
    mode = get_license_mode()
    return templates.TemplateResponse(
        request=request,
        name="activation/index.html",
        context={
            "machine_id": machine_id,
            "default_mode": mode,
            "error": None,
            "submitted_key": "",
        },
    )


@router.post("/activate", response_class=HTMLResponse)
async def activate_license(
    request: Request,
    license_key: Optional[str] = Form(None),
    mode: str = Form("offline"),
    db: Session = Depends(get_db),
):
    from app.services.license_service import activate, get_machine_id, check_license, LicenseStatus

    if check_license().status == LicenseStatus.ACTIVE:
        current_user = get_current_user(request, db)
        if not _can_manage_active_license(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo un administrador autenticado puede reemplazar una licencia activa.",
            )

    machine_id = get_machine_id()

    # Validar que se haya ingresado una clave no vacía
    cleaned_key = (license_key or "").strip()
    if not cleaned_key:
        return templates.TemplateResponse(
            request=request,
            name="activation/index.html",
            context={
                "machine_id": machine_id,
                "default_mode": mode,
                "error": "Por favor ingresa la clave de licencia antes de activar.",
                "submitted_key": "",
            },
            status_code=200,
        )

    try:
        info = activate(cleaned_key, mode)
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="activation/index.html",
            context={
                "machine_id": machine_id,
                "default_mode": mode,
                "error": f"Error al procesar la activación: {str(e)}",
                "submitted_key": cleaned_key,
            },
            status_code=200,
        )

    error_messages = {
        LicenseStatus.UNLICENSED: "Clave de licencia inválida o formato incorrecto.",
        LicenseStatus.EXPIRED: "La licencia ha vencido. Contacta a info@laxarusdevs.com para renovar.",
        LicenseStatus.MACHINE_MISMATCH: "Esta clave fue emitida para otro equipo. Contacta a soporte.",
        LicenseStatus.SERVER_UNREACHABLE: "No se pudo conectar al servidor de licencias. Verifica tu conexión a internet o solicita una clave en Modalidad Offline.",
    }

    if info.status == LicenseStatus.ACTIVE:
        return RedirectResponse(url="/", status_code=303)

    error = error_messages.get(info.status, "Error desconocido. Contacta a soporte.")
    return templates.TemplateResponse(
        request=request,
        name="activation/index.html",
        context={
            "machine_id": machine_id,
            "default_mode": mode,
            "error": error,
            "submitted_key": cleaned_key,
        },
        status_code=200,
    )
