from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode
import json

from app.database import get_db
from app.models.setting import Setting
from app.core.deps import require_admin, require_permission
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])
from app.core.templates import templates

def _sync_redirect(msg: str, msg_type: str = "info") -> RedirectResponse:
    query = urlencode({"msg": msg or "", "type": msg_type or "info"})
    return RedirectResponse(url=f"/sync?{query}", status_code=303)

@router.get("/")
async def sync_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    stats = SyncService.get_sync_stats(db)
    setting = db.query(Setting).first()

    # Si la base de datos local aún tiene la IP quemada de laxarusserver (100.111.106.27), limpiarla
    if setting and setting.tailscale_ip == "100.111.106.27":
        setting.tailscale_ip = None
        db.commit()

    DEFAULT_REMOTE_URL = "https://sscp.laxarusdevs.com"
    remote_url = DEFAULT_REMOTE_URL

    if setting and setting.email and ("http://" in setting.email or "https://" in setting.email):
        remote_url = setting.email.strip()
    elif setting and setting.tailscale_ip and setting.tailscale_ip.strip() and setting.tailscale_ip.strip() != "100.111.106.27":
        candidate_url = f"http://{setting.tailscale_ip.strip()}:8000"
        candidate_chk = await SyncService.check_connection(candidate_url, timeout=1.0)
        if candidate_chk.get("online"):
            remote_url = candidate_url

    # Chequeo no bloqueante rápido
    conn_result = await SyncService.check_connection(remote_url, timeout=2.0)
    recent_logs = SyncService.get_recent_logs(db, limit=10)

    return templates.TemplateResponse(
        request=request,
        name="sync/index.html",
        context={
            "user": current_user,
            "stats": stats,
            "setting": setting,
            "remote_url": remote_url,
            "connection": conn_result,
            "recent_logs": recent_logs,
            "message": request.query_params.get("msg"),
            "msg_type": request.query_params.get("type", "info")
        }
    )

@router.post("/trigger")
async def trigger_sync(
    request: Request,
    remote_url: str = Form("https://sscp.laxarusdevs.com"),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    if not remote_url or "100.111.106.27" in remote_url:
        remote_url = "https://sscp.laxarusdevs.com"

    setting = db.query(Setting).first()
    node_ip = setting.tailscale_ip if setting else None
    
    # Ejecutar Push y Pull con política último gana
    push_res = await SyncService.push_to_remote(db, remote_url, node_ip)
    pull_res = await SyncService.pull_from_remote(db, remote_url, node_ip)

    if setting:
        setting.updated_at = datetime.utcnow()
        db.commit()

    if push_res.get("success") or pull_res.get("success"):
        msg = f"Sincronización completada. Subidos: {push_res.get('sent', 0)} registros. Recibidos: {pull_res.get('received', 0)} registros."
        msg_type = "success"
    else:
        msg = f"Modo Offline: No se pudo conectar al servidor central ({push_res.get('message')}). Los datos están protegidos en SQLite local."
        msg_type = "warning"

    return _sync_redirect(msg, msg_type)

@router.post("/push")
async def push_sync(
    remote_url: str = Form("https://sscp.laxarusdevs.com"),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    if not remote_url or "100.111.106.27" in remote_url:
        remote_url = "https://sscp.laxarusdevs.com"

    setting = db.query(Setting).first()
    res = await SyncService.push_to_remote(db, remote_url, node_ip=setting.tailscale_ip if setting else None)
    msg_type = "success" if res.get("success") else "warning"
    return _sync_redirect(res.get("message", ""), msg_type)

@router.post("/pull")
async def pull_sync(
    remote_url: str = Form("https://sscp.laxarusdevs.com"),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("sync"))
):
    if not remote_url or "100.111.106.27" in remote_url:
        remote_url = "https://sscp.laxarusdevs.com"

    setting = db.query(Setting).first()
    res = await SyncService.pull_from_remote(db, remote_url, node_ip=setting.tailscale_ip if setting else None)
    msg_type = "success" if res.get("success") else "warning"
    return _sync_redirect(res.get("message", ""), msg_type)

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
    db: Session = Depends(get_db)
):
    """
    Comprueba conectividad con la estación par vía HTTP.
    """
    setting = db.query(Setting).first()
    target_url = (peer_url or (setting.central_station_url if setting else None) or "").strip()
    if not target_url:
        return JSONResponse(status_code=400, content={"online": False, "message": "No se ha configurado la dirección URL de la estación par."})

    import httpx
    clean_target = target_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
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
    db: Session = Depends(get_db)
):
    """
    Exporta delta de cambios para la estación par.
    """
    delta = SyncService.export_delta(db, since_iso=since)
    return JSONResponse(content=delta)

@router.post("/peer/import")
def import_peer_delta(
    package: dict = Body(...),
    db: Session = Depends(get_db)
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
