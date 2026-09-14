from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime
import json

from app.database import get_db
from app.models.setting import Setting
from app.core.deps import require_current_user
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/")
async def sync_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    stats = SyncService.get_sync_stats(db)
    setting = db.query(Setting).first()
    remote_url = setting.email if (setting and "http" in (setting.email or "")) else "https://sscp.laxarusdevs.com"
    if setting and setting.tailscale_ip:
        remote_url = f"http://{setting.tailscale_ip}:8000"

    # Chequeo no bloqueante rápido
    conn_result = await SyncService.check_connection(remote_url, timeout=1.5)
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
    current_user = Depends(require_current_user)
):
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

    return RedirectResponse(url=f"/sync?msg={msg}&type={msg_type}", status_code=303)

@router.post("/push")
async def push_sync(
    remote_url: str = Form("https://sscp.laxarusdevs.com"),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    setting = db.query(Setting).first()
    res = await SyncService.push_to_remote(db, remote_url, node_ip=setting.tailscale_ip if setting else None)
    msg_type = "success" if res.get("success") else "warning"
    return RedirectResponse(url=f"/sync?msg={res.get('message')}&type={msg_type}", status_code=303)

@router.post("/pull")
async def pull_sync(
    remote_url: str = Form("https://sscp.laxarusdevs.com"),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    setting = db.query(Setting).first()
    res = await SyncService.pull_from_remote(db, remote_url, node_ip=setting.tailscale_ip if setting else None)
    msg_type = "success" if res.get("success") else "warning"
    return RedirectResponse(url=f"/sync?msg={res.get('message')}&type={msg_type}", status_code=303)

@router.get("/export")
def export_sync_package(
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
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
    current_user = Depends(require_current_user)
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

    return RedirectResponse(url=f"/sync?msg={msg}&type={msg_type}", status_code=303)
