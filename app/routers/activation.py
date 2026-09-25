"""app/routers/activation.py — Pantalla de activacion de licencia."""
from typing import Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sys
from pathlib import Path

BASE_DIR = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter()


@router.get("/activate", response_class=HTMLResponse)
async def activation_page(request: Request):
    from app.services.license_service import get_machine_id, get_license_mode
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
):
    from app.services.license_service import activate, get_machine_id, LicenseStatus

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
