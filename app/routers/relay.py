from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException, Body, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.database import get_db
from app.services.relay_service import RelayService
from app.models.setting import Setting
from app.services.qr_service import generate_qr_code_image_bytes

router = APIRouter(prefix="/api/relay", tags=["relay"])

@router.get("/status")
def global_relay_status(db: Session = Depends(get_db)):
    """Estado global del buzón relay local."""
    clinic_id = RelayService.get_clinic_id(db)
    messages = RelayService.pull_messages(db, clinic_id=clinic_id, limit=5)
    return {
        "status": "online",
        "service": "SSCP Local-First Relay Mailbox",
        "clinic_id": clinic_id,
        "recent_messages_count": len(messages),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/{clinic_id}/status")
def clinic_relay_status(clinic_id: str, db: Session = Depends(get_db)):
    """Estado del buzón para una clínica específica."""
    messages = RelayService.pull_messages(db, clinic_id=clinic_id, limit=100)
    return {
        "status": "online",
        "clinic_id": clinic_id,
        "pending_deltas_count": len(messages),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/{clinic_id}/push")
def push_to_relay(
    clinic_id: str,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Deposita un lote de cambios en el buzón relay.
    Utilizado por la tablet de la secretaria para dejar citas y pacientes
    aunque la PC del doctor esté apagada o en otra red.
    """
    device_id = payload.get("device_id", "tablet_secretaria")
    data = payload.get("data", payload)
    message_type = payload.get("message_type", "delta")

    msg = RelayService.push_message(
        db=db,
        clinic_id=clinic_id,
        device_id=device_id,
        payload=data,
        message_type=message_type
    )

    return {
        "success": True,
        "message_id": msg.id,
        "clinic_id": clinic_id,
        "stored_at": msg.created_at.isoformat() if msg.created_at else datetime.utcnow().isoformat()
    }

@router.get("/{clinic_id}/pull")
def pull_from_relay(
    clinic_id: str,
    since: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Recupera los deltas pendientes del buzón.
    Utilizado por la PC del doctor al encender a las 8:30 AM para
    traer todo lo que la secretaria registró a primera hora.
    """
    messages = RelayService.pull_messages(
        db=db,
        clinic_id=clinic_id,
        since_iso=since,
        exclude_device_id=device_id,
        limit=100
    )

    return {
        "success": True,
        "clinic_id": clinic_id,
        "deltas_count": len(messages),
        "messages": messages,
        "pulled_at": datetime.utcnow().isoformat()
    }

@router.post("/sync-local")
def sync_local_default(
    since: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Sincroniza directamente usando el clinic_id configurado en la clínica."""
    clinic_id = RelayService.get_clinic_id(db)
    return sync_local_from_relay(clinic_id=clinic_id, since=since, db=db)

@router.post("/{clinic_id}/sync-local")
def sync_local_from_relay(
    clinic_id: str,
    since: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Descarga del buzón (tanto del Cloud Relay por Internet como local)
    e integra directamente en la base SQLite local de la PC del Doctor.
    """
    # 1. Absorber deltas pendientes desde el buzón Cloud Relay (Internet público)
    cloud_stats = RelayService.pull_from_cloud(db=db, clinic_id=clinic_id)

    # 2. Absorber deltas del buzón SQLite local si hubiera mensajes directos
    messages = RelayService.pull_messages(
        db=db,
        clinic_id=clinic_id,
        since_iso=since,
        exclude_device_id="pc_doctor",
        limit=100
    )

    total_patients = cloud_stats.get("processed_patients", 0)
    total_appts = cloud_stats.get("processed_appointments", 0)
    total_payments = cloud_stats.get("processed_payments", 0)

    for m in messages:
        payload = m.get("payload", {})
        res = RelayService.reconcile_incoming_delta(db, payload)
        total_patients += res.get("processed_patients", 0)
        total_appts += res.get("processed_appointments", 0)
        total_payments += res.get("processed_payments", 0)

    return {
        "success": True,
        "cloud_messages": cloud_stats.get("pulled_messages", 0),
        "processed_messages": len(messages) + cloud_stats.get("pulled_messages", 0),
        "total_patients_merged": total_patients,
        "total_appointments_merged": total_appts,
        "total_payments_merged": total_payments,
        "synced_at": datetime.utcnow().isoformat()
    }


@router.get("/qr-link")
def get_relay_qr_image(request: Request, db: Session = Depends(get_db)):
    """Genera la imagen PNG del Código QR para conectar la tablet en 2 segundos."""
    from app.routers.sync import get_local_ip
    import os

    clinic_id = RelayService.get_clinic_id(db)
    # Genera enlace que funciona por Internet en cualquier red (Wi-Fi, 4G o cable)
    connection_data = f"https://sscp.laxarusdevs.com/reception/agenda?clinic_id={clinic_id}&server=https://sscp.laxarusdevs.com"

    qr_bytes = generate_qr_code_image_bytes(connection_data)
    return Response(content=qr_bytes, media_type="image/png")

