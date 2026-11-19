from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, Query, Body, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode, urlparse
import hmac
import ipaddress
import json

from app.database import get_db
from app.models.setting import Setting
from app.core.deps import get_current_user, require_admin, require_permission
from app.services.sync_service import SyncService
from app.services.supabase_sync_service import hash_station_secret

router = APIRouter(prefix="/sync", tags=["sync"])
from app.core.templates import templates


def _is_safe_peer_url(raw_url: str) -> bool:
    try:
        parsed = urlparse((raw_url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return True
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_link_local:
                return False
            return ip.is_private or str(ip).startswith("100.")
        except ValueError:
            return host.endswith(".local") or host.endswith(".ts.net") or "." not in host
    except Exception:
        return False


def require_peer_or_sync(request: Request, db: Session = Depends(get_db)):
    peer_key = request.headers.get("X-Peer-Key", "").strip()
    if peer_key:
        setting = db.query(Setting).first()
        sec = getattr(setting, "station_secret", None) if setting else None
        if sec and (hmac.compare_digest(peer_key, sec) or hmac.compare_digest(peer_key, hash_station_secret(sec))):
            return None
    current_user = get_current_user(request, db)
    if current_user and current_user.is_active and current_user.has_permission("sync"):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticación o clave X-Peer-Key requerida para sincronización P2P.",
    )

def _sync_redirect(msg: str, msg_type: str = "info") -> RedirectResponse:
    query = urlencode({"msg": msg or "", "type": msg_type or "info"})
    return RedirectResponse(url=f"/sync?{query}", status_code=303)

import socket
import os

def get_local_ip() -> str:
    """Detecta la IP local de la computadora en la red Wi-Fi o Ethernet del consultorio."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@router.get("/")
async def sync_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    stats = SyncService.get_sync_stats(db)
    setting = db.query(Setting).first()

    local_ip = get_local_ip()
    local_port = int(os.environ.get("SSCP_PORT", 8080))
    mobile_url = f"http://{local_ip}:{local_port}/mobile"

    return templates.TemplateResponse(
        request=request,
        name="sync/index.html",
        context={
            "user": current_user,
            "stats": stats,
            "setting": setting,
            "local_ip": local_ip,
            "local_port": local_port,
            "mobile_url": mobile_url,
            "message": request.query_params.get("msg"),
            "msg_type": request.query_params.get("type", "info")
        }
    )

@router.post("/firewall-rule")
async def enable_firewall_rule(
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Asegura la regla de Windows Firewall para permitir acceso de Tablets en la red local."""
    import subprocess
    try:
        cmd = 'netsh advfirewall firewall add rule name="SSCP Desktop Server (Port 8080)" dir=in action=allow protocol=TCP localport=8080 profile=any'
        subprocess.run(cmd, shell=True, check=True)
        return _sync_redirect("Regla de Firewall de Windows habilitada con éxito para el puerto 8080.", "success")
    except Exception as e:
        return _sync_redirect(f"Aviso: Ejecuta SSCP como Administrador para habilitar el firewall ({e})", "warning")

@router.get("/export")
def export_sync_package(
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    package = SyncService.export_full_package(db)
    content = json.dumps(package, indent=2, ensure_ascii=False)
    filename = f"SSCP_Sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/import")
async def import_sync_package(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    try:
        content = await file.read()
        package_data = json.loads(content.decode("utf-8"))
        result = SyncService.import_package(db, package_data)
        
        msg = result["message"]
        msg_type = "success" if result.get("success") else "danger"
    except Exception as e:
        msg = f"Error al procesar archivo de importación: {str(e)}"
        msg_type = "danger"

    return _sync_redirect(msg, msg_type)

# ==========================================
# FASE 5: ENDPOINTS DE SINCRONIZACIÓN P2P ENTRE ESTACIONES (Doctor <-> Secretaría)
# ==========================================

@router.get("/peer/status")
def peer_station_status(db: Session = Depends(get_db)):
    """
    Retorna el estado de la estación local para que otra estación en la red la reconozca.
    """
    setting = db.query(Setting).first()
    return JSONResponse(content={
        "status": "online",
        "station_role": getattr(setting, "station_role", "doctor_principal"),
        "clinic_name": getattr(setting, "clinic_name", "SSCP Clínica"),
        "sede_name": getattr(setting, "sede_name", "Sede Principal"),
        "version": "1.2.0",
        "server_time": datetime.utcnow().isoformat()
    })

@router.get("/peer/ping")
async def ping_peer_station(
    peer_url: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync")),
):
    """
    Comprueba conectividad con la estación par vía HTTP.
    """
    setting = db.query(Setting).first()
    target_url = (peer_url or (setting.central_station_url if setting else None) or "").strip()
    if not target_url:
        return JSONResponse(status_code=400, content={"online": False, "message": "No se ha configurado la dirección URL de la estación par."})
    if not _is_safe_peer_url(target_url):
        return JSONResponse(status_code=400, content={"online": False, "message": "URL de estación par no permitida (solo red local o Tailscale)."})

    import httpx
    clean_target = target_url.rstrip("/")
    try:
        verify_ssl = SyncService._should_verify_ssl(clean_target)
        async with httpx.AsyncClient(timeout=3.0, verify=verify_ssl) as client:
            resp = await client.get(f"{clean_target}/sync/peer/status")
            if resp.status_code == 200:
                data = resp.json()
                return JSONResponse(content={
                    "online": True,
                    "target_url": clean_target,
                    "station_role": data.get("station_role"),
                    "clinic_name": data.get("clinic_name"),
                    "message": f"Conexión establecida con {data.get('clinic_name', 'Estación')} ({data.get('station_role', 'nodo')})."
                })
            else:
                return JSONResponse(content={
                    "online": False,
                    "target_url": clean_target,
                    "message": f"La estación par respondió con código HTTP {resp.status_code}."
                })
    except Exception as e:
        return JSONResponse(content={
            "online": False,
            "target_url": clean_target,
            "message": f"Estación par no accesible ({str(e)[:80]}). Compruebe la IP y que SSCP esté abierto."
        })

@router.get("/peer/delta")
def export_peer_delta(
    since: str = Query(None),
    db: Session = Depends(get_db),
    _auth = Depends(require_peer_or_sync),
):
    """
    Exporta delta de cambios para la estación par.
    """
    delta = SyncService.export_delta(db, since_iso=since)
    return JSONResponse(content=delta)

@router.post("/peer/import")
def import_peer_delta(
    package: dict = Body(...),
    db: Session = Depends(get_db),
    _auth = Depends(require_peer_or_sync),
):
    """
    Recibe y reconcilia registros enviados por la otra estación sin sobrescritura destructiva.
    """
    result = SyncService.import_delta(db, package)
    return JSONResponse(content=result)

@router.post("/peer/trigger")
async def trigger_peer_sync(
    request: Request,
    peer_url: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    """
    Dispara la sincronización bidireccional inmediata con la estación par (Doctor <-> Secretaría).
    """
    setting = db.query(Setting).first()
    target_url = (peer_url or (setting.central_station_url if setting else None) or "").strip()
    if not target_url:
        return _sync_redirect("Por favor configure la dirección IP o URL de la estación par en Ajustes.", "warning")

    res = await SyncService.sync_with_peer(db, target_url)
    msg_type = "success" if res.get("success") else "warning"
    return _sync_redirect(res.get("message", "Sincronización P2P procesada."), msg_type)
