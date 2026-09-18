"""app/routers/activation.py — Pantalla de activacion de licencia."""
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
        },
    )


@router.post("/activate", response_class=HTMLResponse)
async def activate_license(
    request: Request,
    license_key: str = Form(...),
    mode: str = Form("offline"),
):
    from app.services.license_service import activate, get_machine_id, LicenseStatus

    machine_id = get_machine_id()
    info = activate(license_key, mode)

    error_messages = {
        LicenseStatus.UNLICENSED: "Clave de licencia invalida o incorrecta.",
        LicenseStatus.EXPIRED: "La licencia ha vencido. Contacta a info@laxarusdevs.com para renovar.",
        LicenseStatus.MACHINE_MISMATCH: "Esta clave fue emitida para otro equipo. Contacta a soporte.",
        LicenseStatus.SERVER_UNREACHABLE: "No se pudo conectar al servidor. Verifica tu internet o usa Modalidad Offline.",
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
            "submitted_key": license_key,
        },
        status_code=400,
    )
