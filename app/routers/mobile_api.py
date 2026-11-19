from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc, text
from datetime import datetime, date, time
from typing import Optional, List, Union, Any
from pydantic import BaseModel, EmailStr
import random
import string

from app.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.payment import Payment
from app.models.service import Service
from app.models.setting import Setting
from app.core import security
from app.core.deps import require_current_user, require_permission
from app.routers.patients import resolve_current_doctor_id

router = APIRouter(prefix="/api/mobile", tags=["mobile"])


def _ensure_mobile_sync_keys_table(db: Session) -> None:
    """Crea de forma idempotente la tabla ligera para evitar duplicados por reintentos móviles."""
    from app.services.supabase_sync_service import SupabaseSyncService
    SupabaseSyncService.ensure_sync_tables(db)


def _notify_supabase() -> None:
    """Despierta el puente incremental con Supabase tras cambios locales."""
    try:
        from app.services.supabase_sync_service import signal_supabase_sync
        signal_supabase_sync()
    except Exception:
        pass


def _lookup_mobile_sync_key(db: Session, client_uuid: Optional[str], entity_type: str) -> Optional[int]:
    if not client_uuid or not str(client_uuid).strip():
        return None
    _ensure_mobile_sync_keys_table(db)
    row = db.execute(
        text("SELECT entity_id FROM mobile_sync_keys WHERE client_uuid = :cu AND entity_type = :et"),
        {"cu": str(client_uuid).strip(), "et": entity_type},
    ).fetchone()
    return int(row[0]) if row else None


def _record_mobile_sync_key(db: Session, client_uuid: Optional[str], entity_type: str, entity_id: int) -> None:
    if not client_uuid or not str(client_uuid).strip() or not entity_id:
        return
    _ensure_mobile_sync_keys_table(db)
    db.execute(
        text("""
            INSERT OR REPLACE INTO mobile_sync_keys (client_uuid, entity_type, entity_id, created_at)
            VALUES (:cu, :et, :eid, :ca)
        """),
        {"cu": str(client_uuid).strip(), "et": entity_type, "eid": int(entity_id), "ca": datetime.utcnow().isoformat()},
    )
    db.commit()

# --- Pydantic Schemas for Mobile ---
class MobileLoginRequest(BaseModel):
    email: str
    password: str

class StatusUpdateRequest(BaseModel):
    status: str  # Pendiente, En Espera, En Consulta, Atendida, Cancelada

class QuickAppointmentRequest(BaseModel):
    client_uuid: Optional[str] = None
    patient_id: Optional[Union[int, str]] = None
    patient_name: Optional[str] = None
    patient_last_name: Optional[str] = None
    patient_document_id: Optional[str] = None
    patient_phone: Optional[str] = None
    patient_allergies: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD
    start_time: Optional[str] = None  # HH:MM
    reason: str
    service_id: Optional[Union[int, str]] = None
    price: Optional[float] = None
    insurance_name: Optional[str] = None
    insurance_number: Optional[str] = None
    status: Optional[str] = None
    # Lógica de Cobro Inmediato vs Cobrar Más Tarde
    collect_now: Optional[bool] = False
    payment_amount: Optional[float] = None
    payment_method: Optional[str] = "Efectivo"
    payment_notes: Optional[str] = None

class MobilePatientCreateRequest(BaseModel):
    client_uuid: Optional[str] = None
    first_name: str
    last_name: str
    document_id: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None  # YYYY-MM-DD
    gender: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    insurance_name: Optional[str] = "Privado / Particular"
    insurance_number: Optional[str] = None

class QuickConsultationRequest(BaseModel):
    client_uuid: Optional[str] = None
    patient_id: Union[int, str]
    appointment_id: Optional[Union[int, str]] = None
    reason: Optional[str] = "Consulta General"
    clinical_history: Optional[str] = ""
    symptoms: Optional[str] = ""
    diagnosis: str
    treatment: Optional[str] = ""
    prescription: Optional[str] = ""
    notes: Optional[str] = ""
    weight_kg: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    heart_rate: Optional[int] = None
    temperature_c: Optional[float] = None
    oxygen_saturation: Optional[int] = None
    force_allergy_override: bool = False

class MobilePreauthCreateRequest(BaseModel):
    patient_id: Optional[Union[int, str]] = None
    patient_name: Optional[str] = None
    patient_doc: Optional[str] = None
    patient_phone: Optional[str] = None
    ars_name: str
    card_number: Optional[str] = None
    service_type: str
    cie10_code: Optional[str] = None
    clinical_indication: Optional[str] = None

class QuickPaymentRequest(BaseModel):
    client_uuid: Optional[str] = None
    patient_id: Union[int, str]
    amount: float
    payment_method: str = "Efectivo"
    appointment_id: Optional[Union[int, str]] = None
    service_id: Optional[Union[int, str]] = None
    service_name: Optional[str] = "Consulta Médica General"
    insurance_name: Optional[str] = None
    item_type: Optional[str] = "servicio"  # "servicio" o "articulo"
    notes: Optional[str] = "Pago registrado desde aplicación móvil"

class MobileServiceCreateRequest(BaseModel):
    name: str
    price: float = 0.0
    category: Optional[str] = "General"
    color: Optional[str] = "#0d9488"

class MobileServiceUpdateRequest(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

class MobilePatientUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    document_id: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    insurance_name: Optional[str] = None
    insurance_number: Optional[str] = None

class MobilePaymentUpdateRequest(BaseModel):
    payment_method: str
    amount: Optional[float] = None
    notes: Optional[str] = None

class MobileArsSaveRequest(BaseModel):
    id: Optional[Union[str, int]] = None
    name: str
    short_name: Optional[str] = None

# --- Schemas de Sincronización Diferida / Offline-First (Tailscale / LAN) ---
class BatchSyncPatientItem(BaseModel):
    client_uuid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None
    document_id: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    insurance_name: Optional[str] = "Privado / Particular"
    insurance_number: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: Optional[str] = None

class BatchSyncAppointmentItem(BaseModel):
    client_uuid: Optional[str] = None
    patient_client_uuid: Optional[str] = None
    patient_id: Optional[Union[int, str]] = None
    patient_name: Optional[str] = None
    patient_last_name: Optional[str] = None
    patient_display_name: Optional[str] = None
    patient_document_id: Optional[str] = None
    patient_phone: Optional[str] = None
    patient_allergies: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD
    start_time: Optional[str] = None  # HH:MM
    reason: Optional[str] = "Consulta General"
    service_id: Optional[Union[int, str]] = None
    price: Optional[Union[float, int, str]] = None
    insurance_name: Optional[str] = None
    insurance_number: Optional[str] = None
    status: Optional[str] = "En Espera"
    collect_now: Optional[bool] = False
    payment_amount: Optional[Union[float, int, str]] = None
    payment_method: Optional[str] = "Efectivo"
    payment_notes: Optional[str] = None
    created_at: Optional[str] = None

class BatchSyncPatientUpdateItem(BaseModel):
    id: Optional[Union[int, str]] = None
    client_uuid: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None
    document_id: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    insurance_name: Optional[str] = None
    insurance_number: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    updated_at: Optional[str] = None

class MobileBatchSyncRequest(BaseModel):
    patients: List[BatchSyncPatientItem] = []
    appointments: List[BatchSyncAppointmentItem] = []
    patient_updates: List[BatchSyncPatientUpdateItem] = []
    last_synced_at: Optional[str] = None


# --- Public Ping Endpoint for Connection Testing ---
@router.get("/ping")
def ping_server(db: Session = Depends(get_db)):
    from app.version import SUITE_VERSION
    setting = db.query(Setting).first()
    return {
        "status": "online",
        "app": "SSCP Desktop & Mobile Gateway",
        "version": SUITE_VERSION,
        "clinic_name": setting.clinic_name if setting else "Centro Médico SSCP",
        "doctor_name": setting.doctor_name if setting else "Dr. Especialista",
        "timestamp": datetime.now().isoformat()
    }

# --- Mobile Login ---
@router.post("/login")
def mobile_login(request: Request, payload: MobileLoginRequest, db: Session = Depends(get_db)):
    from app.routers.auth import _check_and_record_attempt, _clear_attempts, _LOCKOUT_SECONDS
    client_ip = request.client.host if request.client else "unknown"
    if not _check_and_record_attempt(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Espera {_LOCKOUT_SECONDS} segundos."
        )
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not security.verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas. Verifique correo y contraseña."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo. Contacte al administrador."
        )
    _clear_attempts(client_ip)

    token = security.create_access_token(data={"email": user.email, "role": user.role})
    setting = db.query(Setting).first()

    from app.services.supabase_sync_service import SupabaseSyncService
    bridge_cfg = SupabaseSyncService.get_bridge_config(db)
    bridge_payload = {
        "enabled": bool(bridge_cfg.get("enabled")),
        "clinic_id": bridge_cfg.get("clinic_id"),
        "secret_hash": bridge_cfg.get("secret_hash"),
        "supabase_url": bridge_cfg.get("supabase_url"),
        "supabase_anon_key": bridge_cfg.get("supabase_anon_key"),
        "doctor_name": bridge_cfg.get("doctor_name"),
        "clinic_name": bridge_cfg.get("clinic_name"),
    } if bridge_cfg.get("enabled") else {"enabled": False}

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
        "clinic": {
            "name": setting.clinic_name if setting else "Centro Médico SSCP",
            "doctor_name": setting.doctor_name if setting else "Dr. Especialista",
            "specialty": setting.specialty if setting else "Medicina General",
            "currency": setting.currency if setting else "RD$",
            "phone": setting.phone if setting else "",
        },
        "supabase_bridge": bridge_payload,
    }


@router.get("/supabase-bridge")
def get_mobile_supabase_bridge(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Entrega al dispositivo movil autenticado las credenciales aisladas del puente Supabase del doctor."""
    from app.services.supabase_sync_service import SupabaseSyncService
    cfg = SupabaseSyncService.get_bridge_config(db)
    if not cfg.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "clinic_id": cfg["clinic_id"],
        "secret_hash": cfg["secret_hash"],
        "supabase_url": cfg["supabase_url"],
        "supabase_anon_key": cfg["supabase_anon_key"],
        "doctor_name": cfg["doctor_name"],
        "clinic_name": cfg["clinic_name"],
        "specialty": cfg["specialty"],
    }


@router.post("/supabase-sync-now")
def trigger_supabase_sync_now(
    current_user: User = Depends(require_permission("sync")),
):
    """Ejecuta un ciclo incremental inmediato contra Supabase."""
    from app.services.supabase_sync_service import SupabaseSyncService
    return SupabaseSyncService.run_incremental_cycle()

# --- Mobile Dashboard ---
@router.get("/dashboard")
def mobile_dashboard(
    filter_date: Optional[str] = None,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    target_date = date.today()
    if filter_date:
        try:
            target_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Conciliar citas activas ya atendidas en consulta antes de armar agenda móvil
    try:
        from app.services.appointment_reconciliation import reconcile_completed_appointments
        if reconcile_completed_appointments(db) > 0:
            db.commit()
    except Exception:
        pass

    # Query today's appointments (aislado estrictamente por médico y excluyendo citas canceladas)
    from app.routers.patients import resolve_current_doctor_id
    from app.routers.appointments import INACTIVE_APPT_STATUSES
    doc_id = resolve_current_doctor_id(db, current_user)
    appts_q = db.query(Appointment).filter(
        Appointment.date == target_date,
        or_(Appointment.status == None, Appointment.status.notin_(INACTIVE_APPT_STATUSES))
    )
    if doc_id:
        appts_q = appts_q.filter(Appointment.doctor_id == doc_id)
    appointments = appts_q.order_by(Appointment.start_time.asc()).all()

    stats = {
        "total": len(appointments),
        "waiting": sum(1 for a in appointments if a.status == "En Espera"),
        "in_consultation": sum(1 for a in appointments if a.status == "En Consulta"),
        "completed": sum(1 for a in appointments if a.status in ["Atendida", "Completada"]),
        "pending": sum(1 for a in appointments if a.status in ["Pendiente", "Confirmada"]),
    }

    from app.routers.appointments import assign_next_queue_number
    from sqlalchemy.sql import func
    needs_commit = False

    appts_data = []
    for a in appointments:
        p = a.patient
        p_name = f"{p.first_name} {p.last_name}" if p else "Paciente no registrado"
        p_phone = p.phone if p else ""

        # Auto-asignar turno si está en espera y no lo tiene
        if a.status == "En Espera" and not a.queue_number:
            a.queue_number = assign_next_queue_number(db, a.date)
            needs_commit = True

        # Verificar si la cita está pagada o si existe pago hoy de este paciente
        is_paid = False
        pay_obj = None
        if a.payments:
            pay_obj = next((py for py in a.payments if py.status == "paid"), None)
        if not pay_obj and a.patient_id:
            pay_obj = db.query(Payment).filter(
                Payment.patient_id == a.patient_id,
                Payment.status == "paid",
                func.date(Payment.created_at) == a.date
            ).order_by(Payment.id.desc()).first()
            if pay_obj and not pay_obj.appointment_id:
                pay_obj.appointment_id = a.id
                needs_commit = True

        if pay_obj:
            is_paid = True

        # Cantidad de visitas de este paciente (consultas previas o citas atendidas)
        past_consultations = db.query(func.count(Consultation.id)).filter(Consultation.patient_id == a.patient_id).scalar() or 0 if a.patient_id else 0
        past_appts = db.query(func.count(Appointment.id)).filter(
            Appointment.patient_id == a.patient_id,
            Appointment.status.in_(["Atendida", "Completada"])
        ).scalar() or 0 if a.patient_id else 0
        patient_visit_count = max(past_consultations, past_appts)

        pay_method_display = "Efectivo"
        if pay_obj and pay_obj.payment_method:
            pm = pay_obj.payment_method.lower()
            if "trans" in pm:
                pay_method_display = "Transferencia"
            elif "card" in pm or "tarjeta" in pm:
                pay_method_display = "Tarjeta"
            elif "insur" in pm or "seguro" in pm:
                pay_method_display = "Seguro Médico"
            else:
                pay_method_display = "Efectivo"

        appts_data.append({
            "id": a.id,
            "patient_id": a.patient_id,
            "patient_name": p_name,
            "patient_phone": p_phone,
            "reason": a.reason,
            "date": a.date.strftime("%Y-%m-%d"),
            "start_time": a.start_time.strftime("%H:%M") if a.start_time else "",
            "end_time": a.end_time.strftime("%H:%M") if a.end_time else "",
            "status": a.status,
            "queue_number": a.queue_number,
            "service_id": a.service_id,
            "service_name": a.service.name if a.service else "",
            "service_color": a.service.color if a.service else "#3b82f6",
            "price": a.price or (a.service.price if a.service else 0.0),
            "insurance_name": p.insurance_name if p and p.insurance_name else "Privado / Particular",
            "insurance_number": p.insurance_number if p and p.insurance_number else "",
            "is_paid": is_paid,
            "payment_id": pay_obj.id if pay_obj else None,
            "payment_method": pay_method_display if is_paid else "",
            "payment_amount": (pay_obj.total or pay_obj.amount) if pay_obj else (a.price or 0.0),
            "payment_status": "paid" if is_paid else "pending",
            "patient_visit_count": patient_visit_count,
            "notes": a.notes or "",
        })

    if needs_commit:
        db.commit()

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "stats": stats,
        "appointments": appts_data,
        "user_role": current_user.role,
        "user_name": current_user.name
    }

# --- Change Appointment Status (En Espera, En Consulta, Atendida, etc.) ---
@router.post("/appointments/{appointment_id}/status")
def update_appointment_status(
    appointment_id: int,
    payload: StatusUpdateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    doc_id = resolve_current_doctor_id(db, current_user)
    if doc_id and appt.doctor_id and int(appt.doctor_id) != int(doc_id):
        raise HTTPException(status_code=403, detail="No autorizado para modificar citas de otro médico.")

    if payload.status in ("Completada", "Atendida") and not current_user.has_permission("consultations"):
        raise HTTPException(
            status_code=403,
            detail="Solo el médico tratante puede finalizar o completar una consulta."
        )

    old_status = appt.status
    if payload.status == "En Espera" and not appt.queue_number:
        from app.routers.appointments import assign_next_queue_number
        appt.queue_number = assign_next_queue_number(db, appt.date)
    elif payload.status in ["Pendiente", "Cancelada", "cancelada", "canceled", "cancelled"]:
        appt.queue_number = None

    appt.status = payload.status
    appt.updated_at = datetime.utcnow()
    db.commit()
    _notify_supabase()

    return {
        "success": True,
        "appointment_id": appt.id,
        "queue_number": appt.queue_number,
        "old_status": old_status,
        "new_status": appt.status,
        "message": f"Estado actualizado a '{appt.status}' por {current_user.name}"
    }

@router.post("/appointments/{appointment_id}/remove-from-queue")
def mobile_remove_from_queue(
    appointment_id: int,
    payload: dict = Body(default={}),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Permite sacar a una paciente de la fila/sala de espera (volver a Pendiente o anular cita por error)."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    mode = str((payload or {}).get("mode") or "cancel").strip().lower()
    if mode not in ("unqueue", "cancel"):
        mode = "cancel"

    from app.routers.appointments import remove_appointment_from_queue
    msg = remove_appointment_from_queue(db, appt, mode=mode)
    _notify_supabase()
    return {
        "success": True,
        "appointment_id": appt.id,
        "status": appt.status,
        "queue_number": appt.queue_number,
        "message": msg
    }

# --- Check-in Móvil con Asignación Inmediata de Turno ---
@router.post("/appointments/{appointment_id}/check-in")
def mobile_check_in_appointment(
    appointment_id: int,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    appt.status = "En Espera"
    if not appt.queue_number:
        from app.routers.appointments import assign_next_queue_number
        appt.queue_number = assign_next_queue_number(db, appt.date)
    appt.updated_at = datetime.utcnow()
    db.commit()
    _notify_supabase()

    p_name = f"{appt.patient.first_name} {appt.patient.last_name}" if appt.patient else "Paciente"
    return {
        "success": True,
        "appointment_id": appt.id,
        "queue_number": appt.queue_number,
        "status": appt.status,
        "message": f"Turno #{appt.queue_number} asignado a {p_name}"
    }

# --- Próximas Citas para Seguimiento de Secretaría ---
@router.get("/appointments/upcoming")
def get_upcoming_appointments(
    range: str = Query("all", description="today, tomorrow, this_week, next_15_days, all"),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    from datetime import date, timedelta
    today = date.today()
    tomorrow = today + timedelta(days=1)

    doc_id = resolve_current_doctor_id(db, current_user)

    base_query = db.query(Appointment).filter(
        Appointment.date >= today,
        Appointment.status.notin_(["Cancelada", "cancelada", "Anulada", "anulada", "Atendida", "Completada"])
    )
    if doc_id:
        base_query = base_query.filter(Appointment.doctor_id == doc_id)

    tomorrow_count = base_query.filter(Appointment.date == tomorrow).count()
    unconfirmed_count = base_query.filter(
        or_(Appointment.status.in_(["Pendiente", "Sin Confirmar"]), Appointment.status == None)
    ).count()

    query = base_query
    if range == "today":
        query = query.filter(Appointment.date == today)
    elif range == "tomorrow":
        query = query.filter(Appointment.date == tomorrow)
    elif range == "this_week":
        end_week = today + timedelta(days=7)
        query = query.filter(Appointment.date <= end_week)
    elif range == "next_15_days":
        end_15 = today + timedelta(days=15)
        query = query.filter(Appointment.date <= end_15)

    if status and status != "all":
        if status == "unconfirmed":
            query = query.filter(or_(Appointment.status.in_(["Pendiente", "Sin Confirmar"]), Appointment.status == None))
        elif status == "confirmed":
            query = query.filter(Appointment.status == "Confirmada")
        else:
            query = query.filter(Appointment.status == status)

    appts = query.order_by(Appointment.date.asc(), Appointment.start_time.asc()).all()

    items = []
    for a in appts:
        p = a.patient
        p_name = f"{p.first_name} {p.last_name}" if p else "Paciente"
        p_doc = p.document_id if p else ""
        p_phone = p.phone if p else ""
        p_ins = p.insurance_name if p and p.insurance_name else "Privado / Particular"

        if search:
            s = search.lower().strip()
            if s not in p_name.lower() and s not in (p_doc or "").lower() and s not in (p_phone or "").lower():
                continue

        items.append({
            "id": a.id,
            "patient_id": a.patient_id,
            "patient_name": p_name,
            "patient_document_id": p_doc,
            "patient_phone": p_phone,
            "insurance_name": p_ins,
            "date": a.date.isoformat() if a.date else "",
            "start_time": a.start_time.strftime("%I:%M %p") if a.start_time else "Por Definir",
            "reason": a.reason or "Consulta General",
            "status": a.status or "Pendiente",
            "whatsapp_reminder_sent": bool(a.whatsapp_reminder_sent),
            "whatsapp_reminder_sent_at": a.whatsapp_reminder_sent_at.isoformat() if a.whatsapp_reminder_sent_at else None,
            "notes": a.notes or ""
        })

    return {
        "success": True,
        "range": range,
        "count": len(items),
        "tomorrow_count": tomorrow_count,
        "unconfirmed_count": unconfirmed_count,
        "appointments": items
    }

@router.post("/appointments/{appointment_id}/whatsapp-sent")
def mark_appointment_whatsapp_sent(
    appointment_id: int,
    current_user: User = Depends(require_permission("appointments")),
    db: Session = Depends(get_db)
):
    from app.routers.patients import resolve_current_doctor_id

    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    doc_id = resolve_current_doctor_id(db, current_user)
    if doc_id and appt.doctor_id is not None and appt.doctor_id != doc_id:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    now = datetime.utcnow()
    appt.whatsapp_reminder_sent = True
    appt.whatsapp_reminder_sent_at = now
    appt.updated_at = now
    db.commit()
    _notify_supabase()
    return {
        "success": True,
        "id": appt.id,
        "appointment_id": appt.id,
        "whatsapp_reminder_sent": True,
        "whatsapp_reminder_sent_at": now.isoformat(),
    }

@router.post("/appointments/{appointment_id}/reschedule")
def reschedule_appointment(
    appointment_id: int,
    payload: dict,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    new_date_str = payload.get("new_date")
    new_time_str = payload.get("new_time")
    if not new_date_str:
        raise HTTPException(status_code=422, detail="Debe especificar la nueva fecha")

    from datetime import datetime as dt
    from app.routers.appointments import find_same_day_appointment
    target_new_date = dt.strptime(new_date_str, "%Y-%m-%d").date()

    existing_same_day = find_same_day_appointment(db, appt.patient_id, target_new_date, exclude_appt_id=appt.id)
    if existing_same_day:
        time_disp = existing_same_day.start_time.strftime("%I:%M %p") if existing_same_day.start_time else ""
        raise HTTPException(
            status_code=409,
            detail=f"El paciente ya tiene otra cita activa para el {target_new_date.strftime('%d/%m/%Y')}{(' a las ' + time_disp) if time_disp else ''}. No se permiten duplicados el mismo día."
        )

    appt.date = target_new_date
    if new_time_str:
        try:
            appt.start_time = dt.strptime(new_time_str, "%H:%M").time()
        except Exception:
            pass
    appt.status = "Reagendada"
    appt.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True, "appointment_id": appt.id, "new_date": str(appt.date), "status": appt.status}

# --- Quick Appointment Create ---
@router.post("/appointments/quick-create")
def quick_create_appointment(
    payload: QuickAppointmentRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    prev_appt_id = _lookup_mobile_sync_key(db, payload.client_uuid, "appointment")
    if prev_appt_id:
        prev_appt = db.query(Appointment).filter(Appointment.id == prev_appt_id).first()
        if prev_appt:
            return {
                "success": True,
                "deduplicated": True,
                "appointment_id": prev_appt.id,
                "patient_id": prev_appt.patient_id,
                "date": str(prev_appt.date),
                "start_time": prev_appt.start_time.strftime("%H:%M") if prev_appt.start_time else "",
                "status": prev_appt.status,
                "payment": None,
                "message": "Cita ya sincronizada previamente."
            }

    def _resolve_id(entity_type: str, raw_val: Any) -> Optional[int]:
        if raw_val is None or isinstance(raw_val, bool):
            return None
        s = str(raw_val).strip()
        if not s:
            return None
        if s.isdigit():
            return int(s)
        return _lookup_mobile_sync_key(db, s, entity_type)

    patient_id = _resolve_id("patient", payload.patient_id)
    resolved_service_id = _resolve_id("service", payload.service_id)

    # Si no se pasó patient_id explícito, buscar primero si ya existe para evitar duplicados
    if not patient_id and payload.patient_name:
        name_clean = payload.patient_name.strip()
        last_clean = (payload.patient_last_name or "").strip()
        phone_clean = (payload.patient_phone or "").strip()
        doc_clean = (payload.patient_document_id or "").strip()

        existing = None
        # 1. Buscar coincidencia por cédula / DNI
        if doc_clean:
            existing = db.query(Patient).filter(Patient.document_id == doc_clean, Patient.is_active == True).first()

        # 2. Buscar coincidencia por teléfono
        if not existing and phone_clean:
            existing = db.query(Patient).filter(Patient.phone == phone_clean, Patient.is_active == True).first()

        # 3. Si no coincide por cédula o teléfono, buscar coincidencia por nombre y apellido
        if not existing and name_clean:
            fname = name_clean
            lname = last_clean
            if not lname and " " in fname:
                parts = fname.split(" ", 1)
                fname = parts[0]
                lname = parts[1]
            if lname:
                existing = db.query(Patient).filter(
                    Patient.first_name.ilike(fname),
                    Patient.last_name.ilike(lname),
                    Patient.is_active == True
                ).first()

        if existing:
            patient_id = existing.id
            req_ins = (payload.insurance_name or "").strip()
            if req_ins and req_ins.lower() not in ("privado", "privado / particular", ""):
                if (not existing.insurance_name) or existing.insurance_name.strip().lower() in ("privado", "privado / particular"):
                    existing.insurance_name = req_ins
                    if payload.insurance_number:
                        existing.insurance_number = payload.insurance_number.strip()
                    db.commit()
        else:
            fname = name_clean
            lname = last_clean
            if not lname and " " in fname:
                parts = fname.split(" ", 1)
                fname = parts[0]
                lname = parts[1]
            ins_name = (payload.insurance_name or "").strip() or "Privado / Particular"
            ins_num = (payload.insurance_number or "").strip() or None
            new_patient = Patient(
                first_name=fname,
                last_name=lname or "S/A",
                phone=phone_clean or None,
                document_id=doc_clean or None,
                insurance_name=ins_name,
                insurance_number=ins_num,
                allergies=(payload.patient_allergies or "").strip() or None,
                is_active=True
            )
            db.add(new_patient)
            db.commit()
            db.refresh(new_patient)
            patient_id = new_patient.id

    if not patient_id:
        raise HTTPException(status_code=400, detail="Debe especificar o registrar un paciente válido")

    from app.routers.patients import resolve_current_doctor_id
    from app.routers.appointments import assign_next_queue_number, find_same_day_appointment
    from datetime import timedelta
    doc_id = resolve_current_doctor_id(db, current_user)

    appt_date = date.today()
    if payload.date and payload.date.strip():
        try:
            appt_date = datetime.strptime(payload.date.strip()[:10], "%Y-%m-%d").date()
        except Exception:
            appt_date = date.today()

    # Filtro anti-duplicidad: no crear otra cita si el paciente ya tiene una activa ese día
    existing_same_day = find_same_day_appointment(db, patient_id, appt_date)
    if existing_same_day:
        time_disp = existing_same_day.start_time.strftime("%I:%M %p") if existing_same_day.start_time else ""
        raise HTTPException(
            status_code=409,
            detail=f"Este paciente ya tiene una cita activa para el {appt_date.strftime('%d/%m/%Y')}{(' a las ' + time_disp) if time_disp else ''} ({existing_same_day.status}). Si se creó por error, sácala de la fila o anúlala primero."
        )

    now_dt = datetime.now()
    start_t = now_dt.time().replace(microsecond=0)
    end_t = (now_dt + timedelta(hours=1)).time().replace(microsecond=0)
    if payload.start_time and payload.start_time.strip() and ":" in payload.start_time:
        try:
            time_parts = payload.start_time.strip().split(":")
            st_h, st_m = int(time_parts[0]), int(time_parts[1])
            start_t = time(st_h, st_m)
            end_t = time((st_h + 1) % 24, st_m)
        except Exception:
            pass

    target_status = payload.status if payload.status else ("En Espera" if appt_date == date.today() else "Pendiente")
    queue_num = assign_next_queue_number(db, appt_date) if target_status == "En Espera" else None

    new_appt = Appointment(
        patient_id=patient_id,
        doctor_id=doc_id,
        date=appt_date,
        start_time=start_t,
        end_time=end_t,
        reason=payload.reason or "Consulta General",
        service_id=resolved_service_id,
        price=payload.price or 0.0,
        status=target_status,
        queue_number=queue_num
    )
    db.add(new_appt)
    db.commit()
    db.refresh(new_appt)
    _record_mobile_sync_key(db, payload.client_uuid, "appointment", new_appt.id)

    payment_record = None
    if payload.collect_now and payload.payment_amount and payload.payment_amount > 0:
        svc_name = payload.reason or "Consulta Médica General"
        if resolved_service_id:
            svc = db.query(Service).filter(Service.id == resolved_service_id).first()
            if svc:
                svc_name = svc.name
        
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        ins_name = payload.insurance_name or (p.insurance_name if p else "Privado / Particular")
        receipt_no = generate_mobile_receipt_number()
        
        note_text = payload.payment_notes or f"Cobro inmediato al agendar cita #{new_appt.id} (por {current_user.name})"
        payment_record = Payment(
            patient_id=patient_id,
            appointment_id=new_appt.id,
            service_id=resolved_service_id,
            service_name=svc_name,
            insurance_name=ins_name or "Privado / Particular",
            amount=payload.payment_amount,
            total=payload.payment_amount,
            payment_method=payload.payment_method or "Efectivo",
            notes=note_text,
            receipt_number=receipt_no,
            created_by_id=current_user.id,
            status="paid",
            created_at=datetime.now()
        )
        db.add(payment_record)
        db.commit()
        db.refresh(payment_record)

    _notify_supabase()
    return {
        "success": True,
        "appointment_id": new_appt.id,
        "patient_id": patient_id,
        "date": str(new_appt.date),
        "start_time": new_appt.start_time.strftime("%H:%M"),
        "status": new_appt.status,
        "payment": {
            "id": payment_record.id,
            "receipt_number": payment_record.receipt_number,
            "amount": payment_record.total,
            "method": payment_record.payment_method
        } if payment_record else None
    }

# --- Listado Completo de Pacientes para Selectores y Agendar Citas Rápidas ---
@router.get("/patients/options")
def get_patient_options(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    from app.routers.patients import resolve_current_doctor_id
    doc_id = resolve_current_doctor_id(db, current_user)

    query = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None))
    if doc_id:
        query = query.filter(or_(Patient.doctor_id == doc_id, Patient.doctor_id == None))

    patients = (
        query
        .order_by(func.coalesce(Patient.last_name, ''), Patient.first_name)
        .all()
    )
    results = []
    for p in patients:
        ln = (p.last_name or "").strip()
        fn = (p.first_name or "").strip()
        doc = (p.document_id or "").strip()
        phone = (p.phone or "").strip()

        display_name = f"{ln}, {fn}".strip(", ")
        display_doc = f" ({doc})" if doc else " (Sin DNI)"
        display_phone = f" - Tel: {phone}" if phone else ""

        results.append({
            "id": p.id,
            "first_name": fn,
            "last_name": ln,
            "name": f"{fn} {ln}".strip(),
            "document_id": doc,
            "phone": phone,
            "email": p.email or "",
            "date_of_birth": str(p.date_of_birth) if p.date_of_birth else "",
            "gender": p.gender or "",
            "address": p.address or "",
            "emergency_contact_name": p.emergency_contact_name or "",
            "emergency_contact_phone": p.emergency_contact_phone or "",
            "allergies": p.allergies or "",
            "blood_type": p.blood_type or "",
            "insurance_name": p.insurance_name or "Privado / Particular",
            "insurance_number": p.insurance_number or "",
            "display": f"{display_name}{display_doc}{display_phone}"
        })
    return {"patients": results, "total": len(results)}

def _filter_active_patients(db: Session, q: Optional[str] = None, doc_id: Optional[int] = None):
    """Helper unificado para filtrado y búsqueda de pacientes activos en la API móvil con soporte completo de acentos, cédula y teléfono."""
    query = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None))
    if doc_id:
        query = query.filter(or_(Patient.doctor_id == doc_id, Patient.doctor_id == None))
    if not q or not q.strip():
        return query

    import unicodedata
    import re

    raw_q = q.strip()
    nfkd = unicodedata.normalize('NFKD', raw_q)
    unaccented_q = "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()
    raw_lower = raw_q.lower()
    digits = re.sub(r'[^0-9]', '', raw_q)

    conditions = [
        func.unaccent(Patient.first_name).like(f"%{unaccented_q}%"),
        func.unaccent(Patient.last_name).like(f"%{unaccented_q}%"),
        func.unaccent(Patient.first_name + " " + Patient.last_name).like(f"%{unaccented_q}%"),
        func.unaccent(Patient.last_name + " " + Patient.first_name).like(f"%{unaccented_q}%"),
        Patient.email.ilike(f"%{raw_lower}%"),
        Patient.phone.ilike(f"%{raw_lower}%"),
        Patient.document_id.ilike(f"%{raw_lower}%"),
    ]

    if len(digits) >= 3:
        clean_doc = func.replace(func.replace(Patient.document_id, "-", ""), " ", "")
        clean_phone = func.replace(func.replace(func.replace(func.replace(Patient.phone, "-", ""), " ", ""), "(", ""), ")", "")
        conditions.append(clean_doc.like(f"%{digits}%"))
        conditions.append(clean_phone.like(f"%{digits}%"))

    if unaccented_q != raw_lower:
        conditions.append(Patient.first_name.ilike(f"%{raw_lower}%"))
        conditions.append(Patient.last_name.ilike(f"%{raw_lower}%"))

    return query.filter(or_(*conditions))

# --- Directorio de Pacientes Móvil con Paginación y Búsqueda ---
@router.get("/patients")
def list_mobile_patients(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Listado del directorio de pacientes para la versión móvil."""
    from app.routers.patients import resolve_current_doctor_id
    doc_id = resolve_current_doctor_id(db, current_user)
    query = _filter_active_patients(db, q, doc_id)
    total = query.count()
    patients = query.order_by(Patient.id.desc()).offset((page - 1) * limit).limit(limit).all()

    results = []
    for p in patients:
        v_cons = db.query(func.count(Consultation.id)).filter(Consultation.patient_id == p.id).scalar() or 0
        v_appts = db.query(func.count(Appointment.id)).filter(
            Appointment.patient_id == p.id,
            Appointment.status.in_(["Atendida", "Completada"])
        ).scalar() or 0
        visit_count = max(v_cons, v_appts)
        results.append({
            "id": p.id,
            "name": f"{p.first_name} {p.last_name}",
            "first_name": p.first_name,
            "last_name": p.last_name,
            "document_id": p.document_id or "",
            "phone": p.phone or "",
            "email": p.email or "",
            "date_of_birth": str(p.date_of_birth) if p.date_of_birth else "",
            "gender": p.gender or "",
            "address": p.address or "",
            "blood_type": p.blood_type or "",
            "allergies": p.allergies or "",
            "insurance_name": p.insurance_name or "Privado / Particular",
            "insurance_number": p.insurance_number or "",
            "emergency_contact": f"{p.emergency_contact_name or ''} {p.emergency_contact_phone or ''}".strip(),
            "created_at": p.created_at.strftime("%d/%m/%Y") if p.created_at else "",
            "visit_count": visit_count
        })

    return {
        "patients": results,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if total > 0 else 1
    }

# --- Verificador Anti-Duplicados en Tiempo Real ---
@router.get("/patients/check-duplicate")
def check_patient_duplicate(
    document_id: Optional[str] = None,
    phone: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    exclude_id: Optional[int] = None,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Verifica si ya existe un paciente registrado con la misma cédula, teléfono o nombre completo para prevenir duplicidad."""
    query = db.query(Patient).filter(Patient.is_active == True)
    if exclude_id:
        query = query.filter(Patient.id != exclude_id)

    # 1. Cédula / DNI
    if document_id and document_id.strip():
        clean_doc = document_id.strip()
        match = query.filter(Patient.document_id == clean_doc).first()
        if match:
            return {
                "is_duplicate": True,
                "field": "cédula",
                "patient": {
                    "id": match.id,
                    "name": f"{match.first_name} {match.last_name}",
                    "document_id": match.document_id or "",
                    "phone": match.phone or "",
                    "email": match.email or ""
                },
                "message": f"Ya existe un paciente con la cédula '{clean_doc}': {match.first_name} {match.last_name}"
            }

    # 2. Teléfono
    if phone and phone.strip():
        clean_phone = phone.strip()
        match = query.filter(Patient.phone == clean_phone).first()
        if match:
            return {
                "is_duplicate": True,
                "field": "teléfono",
                "patient": {
                    "id": match.id,
                    "name": f"{match.first_name} {match.last_name}",
                    "document_id": match.document_id or "",
                    "phone": match.phone or "",
                    "email": match.email or ""
                },
                "message": f"Ya existe un paciente con este teléfono '{clean_phone}': {match.first_name} {match.last_name}"
            }

    # 3. Nombre y Apellido idénticos
    if first_name and last_name and first_name.strip() and last_name.strip():
        fn = first_name.strip()
        ln = last_name.strip()
        match = query.filter(Patient.first_name.ilike(fn), Patient.last_name.ilike(ln)).first()
        if match:
            return {
                "is_duplicate": True,
                "field": "nombre",
                "patient": {
                    "id": match.id,
                    "name": f"{match.first_name} {match.last_name}",
                    "document_id": match.document_id or "",
                    "phone": match.phone or "",
                    "email": match.email or ""
                },
                "message": f"Existe un paciente con el mismo nombre y apellido: {match.first_name} {match.last_name} (Cédula: {match.document_id or 'S/N'}, Tel: {match.phone or 'S/T'})"
            }

    return {"is_duplicate": False, "message": "No se encontraron duplicados"}

# --- Registro de Nuevo Paciente desde Móvil (Secretaria) con Anti-Duplicados ---
def _format_mobile_patient_dict(p: Patient) -> dict:
    return {
        "id": p.id,
        "name": f"{p.first_name} {p.last_name}",
        "first_name": p.first_name,
        "last_name": p.last_name,
        "document_id": p.document_id or "",
        "phone": p.phone or "",
        "email": p.email or "",
        "date_of_birth": str(p.date_of_birth) if p.date_of_birth else "",
        "gender": p.gender or "",
        "address": p.address or "",
        "insurance_name": p.insurance_name or "Privado / Particular",
        "insurance_number": p.insurance_number or ""
    }


@router.post("/patients")
def create_mobile_patient(
    payload: MobilePatientCreateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Alta oficial de paciente desde la aplicación móvil de secretaría."""
    prev_patient_id = _lookup_mobile_sync_key(db, payload.client_uuid, "patient")
    if prev_patient_id:
        prev_p = db.query(Patient).filter(Patient.id == prev_patient_id, Patient.is_active == True).first()
        if prev_p:
            return {
                "success": True,
                "deduplicated": True,
                "patient": _format_mobile_patient_dict(prev_p),
                "message": f"Paciente {prev_p.first_name} {prev_p.last_name} ya estaba sincronizado."
            }

    fn = payload.first_name.strip()
    ln = payload.last_name.strip()
    patient_document_id = payload.document_id.strip() if payload.document_id and payload.document_id.strip() else None
    phone = payload.phone.strip() if payload.phone and payload.phone.strip() else None

    if not fn or not ln:
        raise HTTPException(status_code=400, detail="El nombre y apellido del paciente son obligatorios")

    # Validación anti-duplicados por cédula
    if patient_document_id:
        dup_doc = db.query(Patient).filter(Patient.document_id == patient_document_id, Patient.is_active == True).first()
        if dup_doc:
            if payload.client_uuid:
                _record_mobile_sync_key(db, payload.client_uuid, "patient", dup_doc.id)
                return {
                    "success": True,
                    "deduplicated": True,
                    "patient": _format_mobile_patient_dict(dup_doc),
                    "message": f"Paciente {dup_doc.first_name} {dup_doc.last_name} conciliado con registro existente."
                }
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un paciente con la cédula '{patient_document_id}': {dup_doc.first_name} {dup_doc.last_name}. Utilice el paciente existente para evitar duplicidad."
            )

    # En reintentos offline (client_uuid presente) sin cédula, evitar duplicar por nombre+apellido+teléfono
    if payload.client_uuid and phone:
        dup_offline = db.query(Patient).filter(
            Patient.first_name.ilike(fn),
            Patient.last_name.ilike(ln),
            Patient.phone == phone,
            Patient.is_active == True
        ).first()
        if dup_offline:
            _record_mobile_sync_key(db, payload.client_uuid, "patient", dup_offline.id)
            return {
                "success": True,
                "deduplicated": True,
                "patient": _format_mobile_patient_dict(dup_offline),
                "message": f"Paciente {dup_offline.first_name} {dup_offline.last_name} conciliado sin duplicar."
            }

    dob = None
    if payload.date_of_birth:
        try:
            dob = datetime.strptime(payload.date_of_birth, "%Y-%m-%d").date()
        except Exception:
            pass

    from app.routers.patients import resolve_current_doctor_id
    doctor_id = resolve_current_doctor_id(db, current_user)

    new_patient = Patient(
        doctor_id=doctor_id,
        first_name=fn,
        last_name=ln,
        document_id=patient_document_id,
        phone=phone,
        date_of_birth=dob,
        gender=payload.gender,
        email=payload.email.strip().lower() if payload.email and payload.email.strip() else None,
        address=payload.address.strip() if payload.address and payload.address.strip() else None,
        blood_type=payload.blood_type,
        allergies=payload.allergies.strip() if payload.allergies and payload.allergies.strip() else None,
        emergency_contact_name=payload.emergency_contact_name.strip() if payload.emergency_contact_name and payload.emergency_contact_name.strip() else None,
        emergency_contact_phone=payload.emergency_contact_phone.strip() if payload.emergency_contact_phone and payload.emergency_contact_phone.strip() else None,
        insurance_name=payload.insurance_name or "Privado / Particular",
        insurance_number=payload.insurance_number or None,
        is_active=True
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    _record_mobile_sync_key(db, payload.client_uuid, "patient", new_patient.id)
    _notify_supabase()

    return {
        "success": True,
        "patient": _format_mobile_patient_dict(new_patient),
        "message": f"Paciente {new_patient.first_name} {new_patient.last_name} registrado exitosamente en la base de datos central."
    }

# --- Actualización / Edición de Paciente desde Móvil ---
@router.put("/patients/{patient_id}")
@router.post("/patients/{patient_id}")
@router.post("/patients/{patient_id}/update")
def update_mobile_patient(
    patient_id: Union[int, str],
    payload: MobilePatientUpdateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    pid_int = None
    try:
        pid_int = int(patient_id)
    except (ValueError, TypeError):
        pass

    query = db.query(Patient)
    if pid_int is not None:
        patient = query.filter(Patient.id == pid_int).first()
    else:
        patient = query.filter(Patient.document_id == str(patient_id).strip()).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    if payload.first_name is not None and payload.first_name.strip():
        patient.first_name = payload.first_name.strip()
    if payload.last_name is not None and payload.last_name.strip():
        patient.last_name = payload.last_name.strip()
    if payload.document_id is not None:
        doc_clean = payload.document_id.strip() or None
        if doc_clean:
            dup = db.query(Patient).filter(
                Patient.document_id == doc_clean,
                Patient.id != patient.id,
                Patient.is_active == True
            ).first()
            if dup:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ya existe otro paciente con la cédula '{doc_clean}': {dup.first_name} {dup.last_name}"
                )
        patient.document_id = doc_clean
    if payload.phone is not None:
        patient.phone = payload.phone.strip() or None
    if payload.date_of_birth is not None:
        if payload.date_of_birth.strip():
            try:
                patient.date_of_birth = datetime.strptime(payload.date_of_birth.strip(), "%Y-%m-%d").date()
            except Exception:
                pass
        else:
            patient.date_of_birth = None
    if payload.gender is not None:
        patient.gender = payload.gender.strip() or None
    if payload.email is not None:
        patient.email = payload.email.strip().lower() or None
    if payload.address is not None:
        patient.address = payload.address.strip() or None
    if payload.blood_type is not None:
        patient.blood_type = payload.blood_type.strip() or None
    if payload.allergies is not None:
        patient.allergies = payload.allergies.strip() or None
    if payload.emergency_contact_name is not None:
        patient.emergency_contact_name = payload.emergency_contact_name.strip() or None
    if payload.emergency_contact_phone is not None:
        patient.emergency_contact_phone = payload.emergency_contact_phone.strip() or None
    if payload.insurance_name is not None:
        patient.insurance_name = payload.insurance_name.strip() or "Privado / Particular"
    if payload.insurance_number is not None:
        patient.insurance_number = payload.insurance_number.strip() or None

    patient.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(patient)

    return {
        "success": True,
        "patient": {
            "id": patient.id,
            "name": f"{patient.first_name} {patient.last_name}",
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "document_id": patient.document_id or "",
            "phone": patient.phone or "",
            "email": patient.email or "",
            "date_of_birth": str(patient.date_of_birth) if patient.date_of_birth else "",
            "gender": patient.gender or "",
            "blood_type": patient.blood_type or "",
            "allergies": patient.allergies or "",
            "insurance_name": patient.insurance_name or "Privado / Particular",
            "insurance_number": patient.insurance_number or "",
            "address": patient.address or "",
            "emergency_contact": f"{patient.emergency_contact_name or ''} {patient.emergency_contact_phone or ''}".strip()
        },
        "message": f"Datos del paciente {patient.first_name} {patient.last_name} actualizados exitosamente"
    }

# --- Ficha Detallada del Paciente para la Secretaria / Doctor ---
@router.get("/patients/{patient_id}/details")
def get_mobile_patient_details(
    patient_id: Union[int, str],
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    pid_int = None
    try:
        pid_int = int(patient_id)
    except (ValueError, TypeError):
        pass

    query = db.query(Patient).filter(Patient.is_active == True)
    doc_id = resolve_current_doctor_id(db, current_user)
    if doc_id:
        query = query.filter(or_(Patient.doctor_id == doc_id, Patient.doctor_id.is_(None)))
    if pid_int is not None:
        patient = query.filter(Patient.id == pid_int).first()
    else:
        patient = query.filter(Patient.document_id == str(patient_id).strip()).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    resolved_patient_id = patient.id

    # Citas del paciente
    appts = db.query(Appointment).filter(Appointment.patient_id == resolved_patient_id).order_by(Appointment.date.desc(), Appointment.start_time.desc()).limit(10).all()
    appts_data = []
    for a in appts:
        appts_data.append({
            "id": a.id,
            "date": a.date.strftime("%d/%m/%Y") if a.date else "",
            "start_time": a.start_time.strftime("%H:%M") if a.start_time else "",
            "reason": a.reason or "Consulta General",
            "status": a.status
        })

    # Pagos registrados
    payments = db.query(Payment).filter(Payment.patient_id == resolved_patient_id).order_by(Payment.created_at.desc()).limit(5).all()
    payments_data = []
    total_paid = 0.0
    for py in payments:
        val = float(py.total if py.total is not None and py.total > 0 else (py.amount or 0.0))
        total_paid += val
        payments_data.append({
            "id": py.id,
            "amount": val,
            "method": py.payment_method or "Efectivo",
            "date": py.created_at.strftime("%d/%m/%Y %H:%M") if py.created_at else "",
            "receipt": py.receipt_number or f"REC-{py.id:04d}"
        })

    # Consultas clínicas / Historia del paciente realizada por el doctor (solo rol con permiso consultations)
    can_view_clinical = current_user.has_permission("consultations")
    consultations_q = db.query(Consultation).filter(
        Consultation.patient_id == resolved_patient_id
    )
    if doc_id:
        consultations_q = consultations_q.filter(or_(Consultation.doctor_id == doc_id, Consultation.doctor_id.is_(None)))
    consultations = consultations_q.order_by(Consultation.created_at.desc()).limit(20).all()
    consultations_data = []
    if can_view_clinical:
        for c in consultations:
            c_dt = c.created_at or c.updated_at
            c_date_str = c_dt.strftime("%d/%m/%Y %H:%M") if c_dt else "Fecha no registrada"
            c_hist = getattr(c, 'display_clinical_history', '') or c.clinical_history or ""
            consultations_data.append({
                "id": c.id,
                "date": c_date_str,
                "reason": c.reason or "Consulta Médica",
                "diagnosis": c.diagnosis or "Sin diagnóstico",
                "treatment": c.treatment or "",
                "prescription": c.prescription or "",
                "clinical_history": c_hist,
                "notes": c.notes or ""
            })

    return {
        "patient": {
            "id": patient.id,
            "name": f"{patient.first_name} {patient.last_name}",
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "document_id": patient.document_id or "No registrada",
            "phone": patient.phone or "No registrado",
            "email": patient.email or "No registrado",
            "date_of_birth": str(patient.date_of_birth) if patient.date_of_birth else "No especificada",
            "gender": patient.gender or "No especificado",
            "address": patient.address or "No especificada",
            "blood_type": patient.blood_type or "No especificado",
            "allergies": patient.allergies or "Ninguna conocida",
            "emergency_contact_name": patient.emergency_contact_name or "",
            "emergency_contact_phone": patient.emergency_contact_phone or "",
            "emergency_contact": f"{patient.emergency_contact_name or ''} {patient.emergency_contact_phone or ''}".strip() or "No registrado",
            "insurance_name": patient.insurance_name or "Privado / Particular",
            "insurance_number": patient.insurance_number or "",
            "created_at": patient.created_at.strftime("%d/%m/%Y") if patient.created_at else "",
            "visit_count": max(len(consultations), len([a for a in appts_data if a.get("status") in ("Atendida", "Completada")]))
        },
        "appointments": appts_data,
        "consultations": consultations_data,
        "payments": {
            "total_paid": round(total_paid, 2),
            "recent": payments_data
        }
    }

# --- Search Patients ---
@router.get("/patients/search")
def search_patients(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    doc_id = resolve_current_doctor_id(db, current_user)
    patients = _filter_active_patients(db, q, doc_id=doc_id).limit(20).all()

    results = []
    for p in patients:
        results.append({
            "id": p.id,
            "name": f"{p.first_name} {p.last_name}",
            "phone": p.phone or "",
            "document_id": p.document_id or "",
            "email": p.email or "",
            "allergies": getattr(p, "allergies", "") or "",
            "insurance_name": p.insurance_name or "Privado / Particular",
            "insurance_number": p.insurance_number or "",
        })

    return {"results": results, "count": len(results)}

# --- Doctor Quick Clinical Card ---
@router.get("/patients/{patient_id}/quick-card")
def get_patient_quick_card(
    patient_id: int,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    doc_id = resolve_current_doctor_id(db, current_user)
    patient_q = db.query(Patient).filter(Patient.id == patient_id)
    if doc_id:
        patient_q = patient_q.filter(or_(Patient.doctor_id == doc_id, Patient.doctor_id.is_(None)))
    patient = patient_q.first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    past_records = []
    if current_user.has_permission("consultations"):
        consultations = (
            db.query(Consultation)
            .filter(Consultation.patient_id == patient_id)
            .order_by(desc(Consultation.created_at))
            .limit(3)
            .all()
        )
        for c in consultations:
            past_records.append({
                "id": c.id,
                "date": c.created_at.strftime("%d/%m/%Y") if c.created_at else "",
                "diagnosis": c.diagnosis or "Sin diagnóstico",
                "treatment": c.treatment or "",
                "notes": c.notes or ""
            })

    return {
        "id": patient.id,
        "name": f"{patient.first_name} {patient.last_name}",
        "phone": patient.phone or "No registrado",
        "document_id": patient.document_id or "N/A",
        "blood_type": getattr(patient, "blood_type", "No especificado") or "No especificado",
        "allergies": getattr(patient, "allergies", "Ninguna conocida") or "Ninguna conocida",
        "chronic_conditions": getattr(patient, "chronic_conditions", "Ninguna") or "Ninguna",
        "recent_consultations": past_records
    }

# --- Doctor Quick Consultation Notes ---
@router.post("/consultations/quick")
def quick_save_consultation(
    payload: QuickConsultationRequest,
    current_user: User = Depends(require_permission("consultations")),
    db: Session = Depends(get_db)
):
    if current_user.role not in ("doctor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido: Solo el personal médico o administradores pueden diagnosticar y registrar consultas."
        )
    if payload.client_uuid:
        prev_cid = _lookup_mobile_sync_key(db, payload.client_uuid, "consultation")
        if prev_cid:
            prev_c = db.query(Consultation).filter(Consultation.id == prev_cid).first()
            if prev_c:
                return {
                    "success": True,
                    "deduplicated": True,
                    "consultation_id": prev_c.id,
                    "patient_id": prev_c.patient_id,
                    "message": "Consulta médica ya sincronizada previamente"
                }
    resolved_pat_id = int(payload.patient_id) if str(payload.patient_id).strip().isdigit() else _lookup_mobile_sync_key(db, str(payload.patient_id).strip(), "patient")
    patient_obj = db.query(Patient).filter(Patient.id == resolved_pat_id).first() if resolved_pat_id else None
    if not patient_obj:
        raise HTTPException(status_code=404, detail="Paciente no encontrado para registrar consulta.")

    rx_text = (payload.prescription or payload.treatment or "").strip()
    if rx_text and not payload.force_allergy_override:
        from app.routers.quick_prescriptions import check_allergy_conflict
        conflicts = check_allergy_conflict(patient_obj.allergies, rx_text)
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail=f"Alerta de Alergia (F6): Paciente alérgico a {', '.join(conflicts)}. Confirme anulación bajo criterio médico para continuar."
            )

    resolved_appt_id = None
    if payload.appointment_id is not None and str(payload.appointment_id).strip():
        s_aid = str(payload.appointment_id).strip()
        resolved_appt_id = int(s_aid) if s_aid.isdigit() else _lookup_mobile_sync_key(db, s_aid, "appointment")

    new_cons = Consultation(
        patient_id=resolved_pat_id,
        doctor_id=current_user.id,
        appointment_id=resolved_appt_id,
        reason=payload.reason or "Consulta médica",
        clinical_history=(payload.clinical_history or "").strip() or None,
        symptoms=payload.symptoms or "",
        diagnosis=payload.diagnosis,
        treatment=payload.treatment or "",
        prescription=(payload.prescription or "").strip() or None,
        notes=payload.notes or "",
        created_at=datetime.utcnow()
    )
    db.add(new_cons)

    # Marcar como Completada la cita vinculada y cualquier cita activa del paciente en el día
    from app.services.appointment_reconciliation import reconcile_completed_appointments
    reconcile_completed_appointments(
        db,
        patient_id=resolved_pat_id,
        appointment_id=resolved_appt_id,
        consultation=new_cons,
    )

    db.commit()
    db.refresh(new_cons)

    if any(
        getattr(payload, fld, None) is not None
        for fld in ("weight_kg", "systolic_bp", "diastolic_bp", "heart_rate", "temperature_c", "oxygen_saturation")
    ):
        from app.models.vital_sign import VitalSign
        vital = VitalSign(
            patient_id=resolved_pat_id,
            consultation_id=new_cons.id,
            recorded_by_id=current_user.id,
            weight_kg=payload.weight_kg,
            systolic_bp=payload.systolic_bp,
            diastolic_bp=payload.diastolic_bp,
            heart_rate=payload.heart_rate,
            temperature_c=payload.temperature_c,
            oxygen_saturation=payload.oxygen_saturation,
            recorded_at=datetime.now(),
        )
        db.add(vital)
        db.commit()

    _record_mobile_sync_key(db, payload.client_uuid, "consultation", new_cons.id)

    try:
        from app.services.audit_service import AuditService
        AuditService.log_change(
            db=db,
            entity_type="consultation",
            entity_id=new_cons.id,
            action="create",
            summary=f"Consulta rápida registrada desde móvil por {current_user.name}",
            patient_id=new_cons.patient_id,
            user_id=current_user.id,
            new_data={"reason": new_cons.reason, "diagnosis": new_cons.diagnosis},
        )
    except Exception:
        pass

    _notify_supabase()

    return {
        "success": True,
        "consultation_id": new_cons.id,
        "patient_id": new_cons.patient_id,
        "message": "Consulta médica registrada con éxito"
    }

def generate_mobile_receipt_number():
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"REC-{random_chars}"

# --- Secretary Quick Payment ---
@router.post("/payments/quick")
def quick_register_payment(
    payload: QuickPaymentRequest,
    current_user: User = Depends(require_permission("payments")),
    db: Session = Depends(get_db)
):
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="El monto del cobro debe ser mayor a 0.")
    prev_payment_id = _lookup_mobile_sync_key(db, payload.client_uuid, "payment")
    if prev_payment_id:
        prev_pay = db.query(Payment).filter(Payment.id == prev_payment_id).first()
        if prev_pay:
            return {
                "success": True,
                "deduplicated": True,
                "payment_id": prev_pay.id,
                "receipt_number": prev_pay.receipt_number,
                "service_name": prev_pay.service_name,
                "insurance_name": prev_pay.insurance_name,
                "amount": prev_pay.amount,
                "total": prev_pay.total,
                "payment_method": prev_pay.payment_method,
                "message": f"Pago ya sincronizado previamente ({prev_pay.receipt_number})"
            }

    resolved_pat_id = int(payload.patient_id) if str(payload.patient_id).strip().isdigit() else _lookup_mobile_sync_key(db, str(payload.patient_id).strip(), "patient")
    if not resolved_pat_id:
        raise HTTPException(status_code=404, detail="Paciente no encontrado para registrar el cobro.")

    resolved_svc_id = None
    if payload.service_id is not None and str(payload.service_id).strip():
        s_sid = str(payload.service_id).strip()
        resolved_svc_id = int(s_sid) if s_sid.isdigit() else _lookup_mobile_sync_key(db, s_sid, "service")

    service_name = payload.service_name or "Consulta Médica General"
    if payload.item_type == "articulo" and payload.service_name:
        clean_item = payload.service_name.strip()
        if not clean_item.startswith("[Artículo]") and not clean_item.startswith("[Insumo]"):
            service_name = f"[Artículo] {clean_item}"
        else:
            service_name = clean_item
    elif resolved_svc_id:
        svc = db.query(Service).filter(Service.id == resolved_svc_id).first()
        if svc and (not payload.service_name or payload.service_name == "Consulta Médica General"):
            service_name = svc.name

    ins_name = payload.insurance_name
    if not ins_name:
        p = db.query(Patient).filter(Patient.id == resolved_pat_id).first()
        if p and p.insurance_name:
            ins_name = p.insurance_name

    notes_clean = f"{payload.notes} (por {current_user.name})" if payload.notes else f"Cobro registrado por {current_user.name}"
    receipt_no = generate_mobile_receipt_number()

    appt_id = None
    if payload.appointment_id is not None and str(payload.appointment_id).strip():
        s_aid = str(payload.appointment_id).strip()
        appt_id = int(s_aid) if s_aid.isdigit() else _lookup_mobile_sync_key(db, s_aid, "appointment")
    if not appt_id:
        today = date.today()
        today_appt = db.query(Appointment).filter(
            Appointment.patient_id == resolved_pat_id,
            Appointment.date == today
        ).first()
        if today_appt:
            appt_id = today_appt.id

    payment = Payment(
        patient_id=resolved_pat_id,
        appointment_id=appt_id,
        service_id=resolved_svc_id if payload.item_type != "articulo" else None,
        service_name=service_name,
        insurance_name=ins_name or "Privado / Particular",
        amount=payload.amount,
        total=payload.amount,
        payment_method=payload.payment_method,
        notes=notes_clean,
        receipt_number=receipt_no,
        created_by_id=current_user.id,
        status="paid",
        created_at=datetime.now()
    )
    db.add(payment)
    if payload.item_type == "articulo":
        try:
            from app.models.inventory import InventoryItem, InventoryMovement
            inv_item = None
            if resolved_svc_id:
                inv_item = db.query(InventoryItem).filter(InventoryItem.id == resolved_svc_id).first()
            if not inv_item and service_name:
                inv_item = db.query(InventoryItem).filter(InventoryItem.name.ilike(service_name.strip())).first()
            if inv_item and inv_item.stock and inv_item.stock > 0:
                inv_item.stock -= 1
                db.add(InventoryMovement(
                    inventory_item_id=inv_item.id,
                    user_id=current_user.id,
                    type="out",
                    quantity=1,
                    notes=f"Cobro móvil {receipt_no}"
                ))
        except Exception:
            pass
    db.commit()
    db.refresh(payment)
    _record_mobile_sync_key(db, payload.client_uuid, "payment", payment.id)
    _notify_supabase()

    return {
        "success": True,
        "payment_id": payment.id,
        "receipt_number": payment.receipt_number,
        "service_name": payment.service_name,
        "insurance_name": payment.insurance_name,
        "amount": payment.amount,
        "total": payment.total,
        "payment_method": payment.payment_method,
        "message": f"Pago de RD$ {payment.total:,.2f} registrado exitosamente ({payment.receipt_number})"
    }

# --- Modificar Método de Pago o Monto de Cobro (Efectivo <-> Transferencia <-> Tarjeta) ---
@router.put("/payments/{payment_id}")
@router.post("/payments/{payment_id}")
@router.post("/payments/{payment_id}/update")
def update_payment_details(
    payment_id: int,
    payload: MobilePaymentUpdateRequest,
    current_user: User = Depends(require_permission("payments")),
    db: Session = Depends(get_db)
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Registro de pago no encontrado")

    clean_method = payload.payment_method.strip()
    pm_lower = clean_method.lower()
    if "copago" in pm_lower or "copay" in pm_lower:
        canonical_method = "Copago ARS"
    elif "trans" in pm_lower:
        canonical_method = "Transferencia"
    elif "tarjeta" in pm_lower or "card" in pm_lower:
        canonical_method = "Tarjeta"
    elif "seguro" in pm_lower or "insur" in pm_lower:
        canonical_method = "Seguro Médico"
    else:
        canonical_method = "Efectivo"

    old_method = payment.payment_method
    payment.payment_method = canonical_method
    if payload.amount is not None:
        if payload.amount <= 0:
            raise HTTPException(status_code=400, detail="El monto modificado debe ser mayor a 0.")
        payment.amount = payload.amount
        payment.total = payload.amount

    notes_addition = f"[Modificado por {current_user.name}: método '{old_method}' -> '{canonical_method}']"
    if payload.notes:
        payment.notes = f"{payload.notes} | {notes_addition}"
    else:
        payment.notes = f"{(payment.notes or '').strip()} | {notes_addition}".strip(" | ")

    payment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(payment)
    _notify_supabase()

    return {
        "success": True,
        "payment_id": payment.id,
        "payment_method": canonical_method,
        "amount": payment.total or payment.amount,
        "payment": {
            "id": payment.id,
            "method": canonical_method,
            "amount": payment.total or payment.amount
        },
        "notes": payment.notes,
        "message": f"Método de pago modificado exitosamente a '{canonical_method}'"
    }

@router.post("/appointments/{appointment_id}/payment/update")
@router.put("/appointments/{appointment_id}/payment")
def update_appointment_payment(
    appointment_id: int,
    payload: MobilePaymentUpdateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    pay = None
    if appt.payments:
        pay = next((p for p in appt.payments if p.status == "paid"), None)
    if not pay and appt.patient_id:
        pay = db.query(Payment).filter(
            Payment.patient_id == appt.patient_id,
            Payment.status == "paid",
            func.date(Payment.created_at) == appt.date
        ).first()

    if pay:
        return update_payment_details(pay.id, payload, current_user, db)
    else:
        clean_method = payload.payment_method.strip()
        pm_lower = clean_method.lower()
        if "copago" in pm_lower or "copay" in pm_lower:
            canonical_method = "Copago ARS"
        elif "trans" in pm_lower:
            canonical_method = "Transferencia"
        elif "tarjeta" in pm_lower or "card" in pm_lower:
            canonical_method = "Tarjeta"
        elif "seguro" in pm_lower or "insur" in pm_lower:
            canonical_method = "Seguro Médico"
        else:
            canonical_method = "Efectivo"

        amt = payload.amount if payload.amount is not None and payload.amount > 0 else (appt.price or 0.0)
        new_pay = Payment(
            patient_id=appt.patient_id,
            appointment_id=appt.id,
            service_id=appt.service_id,
            service_name=appt.service.name if appt.service else "Consulta Médica General",
            insurance_name=appt.patient.insurance_name if appt.patient else "Privado",
            amount=amt,
            total=amt,
            payment_method=canonical_method,
            notes=payload.notes or f"Cobro registrado desde móvil por {current_user.name}",
            receipt_number=generate_mobile_receipt_number(),
            created_by_id=current_user.id,
            status="paid",
            created_at=datetime.now()
        )
        db.add(new_pay)
        db.commit()
        db.refresh(new_pay)
        _notify_supabase()
        return {
            "success": True,
            "payment_id": new_pay.id,
            "payment_method": canonical_method,
            "amount": new_pay.total or new_pay.amount,
            "message": f"Cobro en '{canonical_method}' registrado correctamente"
        }

# --- Catálogo de Servicios y Administración Móvil (Talonario) ---
@router.get("/services")
def get_mobile_services(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Retorna la lista completa de servicios activos del talonario para citas y cobros."""
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.name.asc()).all()
    return {
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "price": s.price,
                "category": s.category or "General",
                "color": s.color or "#0d9488",
                "is_active": s.is_active
            }
            for s in services
        ]
    }

@router.post("/services")
def create_mobile_service(
    payload: MobileServiceCreateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Crea un nuevo servicio en el talonario oficial desde la app móvil."""
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre del servicio es obligatorio")
    
    existing = db.query(Service).filter(func.lower(Service.name) == clean_name.lower()).first()
    if existing:
        existing.is_active = True
        existing.price = max(0.0, float(payload.price))
        existing.category = payload.category or "General"
        db.commit()
        db.refresh(existing)
        svc = existing
    else:
        svc = Service(
            name=clean_name,
            price=max(0.0, float(payload.price)),
            category=payload.category or "General",
            color=payload.color or "#0d9488",
            is_active=True
        )
        db.add(svc)
        db.commit()
        db.refresh(svc)
    return {
        "success": True,
        "service": {
            "id": svc.id,
            "name": svc.name,
            "price": svc.price,
            "category": svc.category
        },
        "message": f"Servicio '{svc.name}' guardado correctamente en el talonario"
    }

@router.put("/services/{service_id}")
def update_mobile_service(
    service_id: int,
    payload: MobileServiceUpdateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Modifica un servicio existente (nombre, precio o categoría) desde la app móvil."""
    svc = db.query(Service).filter(Service.id == service_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    if payload.name is not None and payload.name.strip():
        svc.name = payload.name.strip()
    if payload.price is not None:
        svc.price = max(0.0, float(payload.price))
    if payload.category is not None:
        svc.category = payload.category.strip()
    if payload.is_active is not None:
        svc.is_active = payload.is_active
    db.commit()
    db.refresh(svc)
    return {
        "success": True,
        "service": {
            "id": svc.id,
            "name": svc.name,
            "price": svc.price,
            "category": svc.category,
            "is_active": svc.is_active
        },
        "message": f"Servicio '{svc.name}' actualizado exitosamente"
    }

# --- Catálogo Oficial de ARS para la App Móvil ---
@router.get("/ars")
def get_mobile_ars(
    current_user: User = Depends(require_current_user)
):
    """Retorna la lista oficial de ARS (República Dominicana) con metadatos y logos."""
    from app.services.ars_service import get_all_ars
    return {"ars": get_all_ars()}

@router.post("/ars")
def save_mobile_ars(
    payload: MobileArsSaveRequest,
    current_user: User = Depends(require_current_user)
):
    """Crea o actualiza un seguro/ARS en el catálogo oficial desde la app móvil."""
    from app.services.ars_service import save_or_update_ars, get_all_ars
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre del seguro o ARS es obligatorio")
    try:
        item = save_or_update_ars(payload.dict())
        return {
            "success": True,
            "ars": item,
            "ars_list": get_all_ars(),
            "message": f"Seguro '{item['name']}' guardado correctamente"
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@router.put("/ars/{ars_id}")
@router.post("/ars/{ars_id}")
def update_mobile_ars(
    ars_id: str,
    payload: MobileArsSaveRequest,
    current_user: User = Depends(require_current_user)
):
    """Actualiza un seguro existente en el catálogo oficial desde la app móvil."""
    from app.services.ars_service import save_or_update_ars, get_all_ars
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre del seguro o ARS es obligatorio")
    data = payload.dict()
    data["id"] = ars_id
    try:
        item = save_or_update_ars(data)
        return {
            "success": True,
            "ars": item,
            "ars_list": get_all_ars(),
            "message": f"Seguro '{item['name']}' actualizado correctamente"
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

# --- Catálogo de Artículos / Insumos de Inventario para Cobros ---
@router.get("/inventory")
def get_mobile_inventory_items(
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Retorna artículos del inventario o insumos disponibles para cobro directo."""
    from app.models.inventory import InventoryItem
    items = db.query(InventoryItem).order_by(InventoryItem.name).all()
    return {
        "items": [
            {
                "id": it.id,
                "name": it.name,
                "price": it.price,
                "category": it.category or "Insumo",
                "stock": it.stock
            }
            for it in items
        ]
    }

# --- Mobile Consolidated Reports (Pagos, Vistos, Citas Previas y PDF) ---
@router.get("/reports/summary")
def get_mobile_reports_summary(
    report_date: Optional[str] = Query(None),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """
    Reporte consolidado móvil: Cuadre de Pagos, Pacientes Vistos y Citas Previas/Historial.
    Accesible para Doctor y Secretaría.
    """
    if report_date:
        try:
            target_date = datetime.strptime(report_date, "%Y-%m-%d").date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = datetime.combine(target_date, datetime.max.time())
    setting = db.query(Setting).first()
    currency = getattr(setting, "currency", "RD$") if setting else "RD$"

    # 1. Pagos del día (Cuadre de caja)
    payments = (
        db.query(Payment)
        .filter(Payment.created_at >= start_dt, Payment.created_at <= end_dt)
        .order_by(Payment.created_at.desc())
        .all()
    )

    total_collected = 0.0
    total_pending = 0.0
    by_method = {}
    payments_list = []

    for p in payments:
        p_val = float(p.total if p.total is not None and p.total > 0 else (p.amount or 0.0))
        st = p.status or "paid"
        meth = p.payment_method or "Efectivo"
        p_name = f"{p.patient.first_name} {p.patient.last_name}" if p.patient else "Paciente"

        if st in ["paid", "Completado"]:
            total_collected += p_val
            by_method[meth] = by_method.get(meth, 0.0) + p_val
        elif st == "pending":
            total_pending += p_val

        payments_list.append({
            "id": p.id,
            "patient_id": p.patient_id,
            "patient_name": p_name,
            "amount": p_val,
            "payment_method": meth,
            "status": "Pagado" if st in ["paid", "Completado"] else "Pendiente",
            "receipt_number": p.receipt_number or f"REC-{p.id:04d}",
            "time": p.created_at.strftime("%H:%M") if p.created_at else "",
            "notes": p.notes or ""
        })

    # 2. Pacientes Vistos / Consultas Realizadas (diagnóstico y notas protegidos para secretaría)
    doc_id = resolve_current_doctor_id(db, current_user)
    can_view_clinical = current_user.has_permission("consultations")
    c_q = db.query(Consultation).filter(
        Consultation.created_at >= start_dt,
        Consultation.created_at <= end_dt
    )
    if doc_id:
        c_q = c_q.filter(or_(Consultation.doctor_id == doc_id, Consultation.doctor_id.is_(None)))
    consultations = c_q.order_by(Consultation.created_at.desc()).all()

    attended_list = []
    for c in consultations:
        p_name = f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Paciente"
        doc_name = c.doctor.name if c.doctor else "Médico"
        attended_list.append({
            "id": c.id,
            "patient_id": c.patient_id,
            "patient_name": p_name,
            "doctor_name": doc_name,
            "time": c.created_at.strftime("%H:%M") if c.created_at else "",
            "reason": c.reason or "Consulta Médica",
            "diagnosis": (c.diagnosis or "Sin diagnóstico") if can_view_clinical else "Atendido en consulta (protegido)",
            "treatment": (c.treatment or "") if can_view_clinical else "",
            "notes": (c.notes or "") if can_view_clinical else ""
        })

    # 3. Citas del día (Histórico / Citas previas)
    appointments = (
        db.query(Appointment)
        .filter(Appointment.date == target_date)
        .order_by(Appointment.start_time.asc())
        .all()
    )

    appts_list = []
    appts_stats = {
        "total": len(appointments),
        "attended": 0,
        "waiting": 0,
        "in_consultation": 0,
        "cancelled": 0,
        "pending": 0
    }

    for a in appointments:
        p_name = f"{a.patient.first_name} {a.patient.last_name}" if a.patient else "Paciente no registrado"
        p_phone = a.patient.phone if a.patient else ""
        st = a.status or "Pendiente"

        if st in ["Atendida", "Completada"]:
            appts_stats["attended"] += 1
        elif st == "En Espera":
            appts_stats["waiting"] += 1
        elif st == "En Consulta":
            appts_stats["in_consultation"] += 1
        elif st in ["Cancelada", "No Asistió"]:
            appts_stats["cancelled"] += 1
        else:
            appts_stats["pending"] += 1

        appts_list.append({
            "id": a.id,
            "patient_id": a.patient_id,
            "patient_name": p_name,
            "patient_phone": p_phone,
            "start_time": a.start_time.strftime("%H:%M") if a.start_time else "",
            "reason": a.reason or "Consulta General",
            "status": st
        })

    effective_attended_count = max(len(attended_list), appts_stats["attended"])

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "date_formatted": target_date.strftime("%d/%m/%Y"),
        "currency": currency,
        "payments": {
            "total_collected": round(total_collected, 2),
            "total_pending": round(total_pending, 2),
            "count": len(payments_list),
            "by_method": {k: round(v, 2) for k, v in by_method.items()},
            "items": payments_list
        },
        "attended": {
            "count": effective_attended_count,
            "consultations_count": len(attended_list),
            "items": attended_list
        },
        "appointments": {
            "stats": appts_stats,
            "items": appts_list
        },
        "pdf_export_url": f"/reports/export/secretary-daily-pdf?report_date={target_date.strftime('%Y-%m-%d')}"
    }


# --- Mobile Consolidated Monthly Reports & Weekly Analysis ---
@router.get("/reports/monthly")
def get_mobile_reports_monthly(
    month: Optional[str] = Query(None),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """
    Informe Mensual de Actividad Médica & Análisis Semanal para la App Móvil:
    - Tipos de citas con conteo y % exacto.
    - Gráfica interactiva de distribución por tipo de cita.
    - Análisis semanal: qué día fue más fuerte (pico) y cuál más flojo.
    - Gráfica de barras semanal por días (Lunes a Domingo).
    """
    import calendar
    import re
    from collections import Counter

    MONTH_NAMES_ES = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }
    PALETTE = [
        "#4f46e5", "#06b6d4", "#10b981", "#f59e0b", "#ec4899",
        "#8b5cf6", "#3b82f6", "#14b8a6", "#f97316", "#64748b"
    ]

    appt_dates = db.query(Appointment.date).filter(Appointment.date != None).distinct().all()
    months_set = set()
    for (d,) in appt_dates:
        if d:
            months_set.add(d.strftime('%Y-%m'))

    cons_dates = db.query(Consultation.created_at).filter(Consultation.created_at != None).distinct().all()
    for (dt,) in cons_dates:
        if dt:
            months_set.add(dt.strftime('%Y-%m'))

    available_months = sorted(list(months_set), reverse=True)
    today = date.today()
    current_month_str = today.strftime("%Y-%m")
    if current_month_str not in available_months:
        available_months.insert(0, current_month_str)

    selected_month_str = (month or "").strip()
    if not selected_month_str or not re.match(r"^\d{4}-\d{2}$", selected_month_str):
        selected_month_str = current_month_str

    try:
        y_int, m_int = [int(p) for p in selected_month_str.split("-")]
        if not (1 <= m_int <= 12):
            y_int, m_int = today.year, today.month
            selected_month_str = f"{y_int:04d}-{m_int:02d}"
    except Exception:
        y_int, m_int = today.year, today.month
        selected_month_str = f"{y_int:04d}-{m_int:02d}"

    month_name_es = f"{MONTH_NAMES_ES[m_int]} {y_int}"

    if m_int == 1:
        prev_month_str = f"{y_int - 1:04d}-12"
    else:
        prev_month_str = f"{y_int:04d}-{m_int - 1:02d}"

    if m_int == 12:
        next_month_str = f"{y_int + 1:04d}-01"
    else:
        next_month_str = f"{y_int:04d}-{m_int + 1:02d}"

    _, last_day = calendar.monthrange(y_int, m_int)
    start_dt = datetime(y_int, m_int, 1, 0, 0, 0)
    end_dt = datetime(y_int, m_int, last_day, 23, 59, 59)
    start_d = date(y_int, m_int, 1)
    end_d = date(y_int, m_int, last_day)

    setting = db.query(Setting).first()
    currency = getattr(setting, "currency", "RD$") if setting else "RD$"

    appts = db.query(Appointment).filter(
        ((Appointment.date >= start_d) & (Appointment.date <= end_d)) |
        ((Appointment.date == None) & (Appointment.created_at >= start_dt) & (Appointment.created_at <= end_dt))
    ).all()
    total_appointments = len(appts)

    conss = db.query(Consultation).filter(
        Consultation.created_at >= start_dt,
        Consultation.created_at <= end_dt
    ).all()
    total_consultations = len(conss)

    p_ids = {a.patient_id for a in appts if a.patient_id} | {c.patient_id for c in conss if c.patient_id}
    unique_patients_count = len(p_ids)

    payments = db.query(Payment).filter(
        Payment.created_at >= start_dt,
        Payment.created_at <= end_dt
    ).all()
    total_revenue = sum(float(p.total or 0.0) for p in payments if (p.status in ['paid', 'Completado'] or p.status is None))

    type_counter = Counter()
    for a in appts:
        t = (a.reason or (a.service.name if a.service else "Consulta General")).strip()
        type_counter[t] += 1

    for c in conss:
        if not c.appointment_id:
            t = (c.reason or "Consulta Médica General").strip()
            type_counter[t] += 1

    total_activity = sum(type_counter.values())
    types_breakdown = []
    for idx, (t_name, count) in enumerate(type_counter.most_common()):
        pct = round((count / max(total_activity, 1)) * 100, 1)
        color = PALETTE[idx % len(PALETTE)]
        types_breakdown.append({
            "name": t_name,
            "count": count,
            "percentage": pct,
            "color": color
        })

    types_chart_labels = [item["name"] for item in types_breakdown]
    types_chart_data = [item["count"] for item in types_breakdown]
    types_chart_colors = [item["color"] for item in types_breakdown]

    day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    day_names_short = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    weekday_counts = [0] * 7

    for a in appts:
        d = a.date or (a.created_at.date() if a.created_at else None)
        if d:
            weekday_counts[d.weekday()] += 1

    for c in conss:
        if not c.appointment_id and c.created_at:
            d = c.created_at.date()
            weekday_counts[d.weekday()] += 1

    total_week_events = sum(weekday_counts)

    strongest_day = None
    weakest_day = None
    if total_week_events > 0:
        max_c = max(weekday_counts)
        max_idx = weekday_counts.index(max_c)
        strongest_day = {
            "name": day_names[max_idx],
            "short_name": day_names_short[max_idx],
            "count": max_c,
            "percentage": round((max_c / total_week_events) * 100, 1)
        }

        min_c = min(weekday_counts)
        min_idx = weekday_counts.index(min_c)
        weakest_day = {
            "name": day_names[min_idx],
            "short_name": day_names_short[min_idx],
            "count": min_c,
            "percentage": round((min_c / total_week_events) * 100, 1)
        }

    weekly_breakdown = []
    for i in range(7):
        c_count = weekday_counts[i]
        weekly_breakdown.append({
            "name": day_names[i],
            "short_name": day_names_short[i],
            "count": c_count,
            "percentage": round((c_count / max(total_week_events, 1)) * 100, 1),
            "is_strongest": bool(strongest_day and day_names[i] == strongest_day["name"] and c_count > 0),
            "is_weakest": bool(weakest_day and day_names[i] == weakest_day["name"])
        })

    return {
        "selected_month": selected_month_str,
        "month_name": month_name_es,
        "available_months": available_months,
        "prev_month": prev_month_str,
        "next_month": next_month_str,
        "currency": currency,
        "summary": {
            "total_appointments": total_appointments,
            "total_consultations": total_consultations,
            "unique_patients_count": unique_patients_count,
            "total_revenue": round(total_revenue, 2),
            "total_activity": total_activity
        },
        "types_breakdown": types_breakdown,
        "types_chart": {
            "labels": types_chart_labels,
            "data": types_chart_data,
            "colors": types_chart_colors
        },
        "weekly_analysis": {
            "total_events": total_week_events,
            "strongest_day": strongest_day,
            "weakest_day": weakest_day,
            "weekly_breakdown": weekly_breakdown,
            "chart": {
                "labels": day_names_short,
                "data": weekday_counts
            }
        }
    }


# ==============================================================================
# MOTOR DE SINCRONIZACIÓN OFFLINE-FIRST (ALMACENAR EN MÓVIL Y TRANSFERIR A PC)
# ==============================================================================

@router.post("/sync/batch")
def mobile_sync_batch(
    payload: MobileBatchSyncRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """
    Recibe un lote de citas, pacientes y actualizaciones creados en modo offline por la APK/Móvil.
    Reconcilia registros existentes, previene duplicados por cédula/teléfono/horario
    y devuelve el mapeo de IDs asignados en SQLite para que el móvil actualice su caché.
    """
    patient_id_map = {}
    processed_patients = 0
    processed_appointments = 0
    processed_updates = 0
    doc_id = resolve_current_doctor_id(db, current_user)

    # 1. Procesar Pacientes Offline
    for p_item in payload.patients:
        doc_clean = (p_item.document_id or "").strip() or None
        phone_clean = (p_item.phone or "").strip() or None
        fn = (p_item.first_name or "").strip()
        ln = (p_item.last_name or "").strip()
        if not fn and p_item.name:
            parts = p_item.name.strip().split()
            fn = parts[0] if parts else "Paciente"
            ln = " ".join(parts[1:]) if len(parts) > 1 else "S/A"
        if not fn:
            fn = "Paciente"
        if not ln:
            ln = "S/A"

        existing = None
        if p_item.client_uuid:
            prev_pid = _lookup_mobile_sync_key(db, p_item.client_uuid, "patient")
            if prev_pid:
                existing = db.query(Patient).filter(Patient.id == prev_pid, Patient.is_active == True).first()
        pat_base = db.query(Patient).filter(Patient.is_active == True)
        if doc_id:
            pat_base = pat_base.filter(Patient.doctor_id == doc_id)
        if not existing and doc_clean:
            existing = pat_base.filter(Patient.document_id == doc_clean).first()
        if not existing and phone_clean:
            existing = pat_base.filter(Patient.phone == phone_clean).first()
        if not existing and fn and ln:
            existing = pat_base.filter(
                Patient.first_name.ilike(fn),
                Patient.last_name.ilike(ln)
            ).first()

        if existing:
            if not existing.phone and phone_clean:
                existing.phone = phone_clean
            if not existing.allergies and p_item.allergies:
                existing.allergies = p_item.allergies.strip()
            if not existing.insurance_name and p_item.insurance_name:
                existing.insurance_name = p_item.insurance_name
            db.commit()
            assigned_id = existing.id
            processed_patients += 1
        else:
            dob_val = None
            if p_item.date_of_birth:
                try:
                    dob_val = datetime.strptime(p_item.date_of_birth.strip()[:10], "%Y-%m-%d").date()
                except Exception:
                    pass

            new_p = Patient(
                doctor_id=doc_id,
                first_name=fn,
                last_name=ln,
                document_id=doc_clean,
                phone=phone_clean,
                date_of_birth=dob_val,
                gender=p_item.gender or None,
                email=p_item.email or None,
                address=p_item.address or None,
                blood_type=p_item.blood_type or None,
                allergies=p_item.allergies or None,
                emergency_contact_name=p_item.emergency_contact_name or None,
                emergency_contact_phone=p_item.emergency_contact_phone or None,
                insurance_name=p_item.insurance_name or "Privado / Particular",
                insurance_number=p_item.insurance_number or None,
                is_active=True
            )
            db.add(new_p)
            db.commit()
            db.refresh(new_p)
            assigned_id = new_p.id
            processed_patients += 1

        if p_item.client_uuid:
            _record_mobile_sync_key(db, p_item.client_uuid, "patient", assigned_id)
            patient_id_map[p_item.client_uuid] = assigned_id

    # 2. Procesar Citas Offline
    appointment_id_map = {}
    for a_item in payload.appointments:
        target_pid = None
        if a_item.patient_id is not None:
            try:
                target_pid = int(a_item.patient_id)
            except (ValueError, TypeError):
                target_pid = patient_id_map.get(str(a_item.patient_id))
        if not target_pid and a_item.patient_client_uuid:
            target_pid = patient_id_map.get(str(a_item.patient_client_uuid))

        p_full_name = (a_item.patient_name or a_item.patient_display_name or "").strip()
        if not target_pid and p_full_name:
            # Resolver paciente al vuelo
            doc_c = (a_item.patient_document_id or "").strip() or None
            ph_c = (a_item.patient_phone or "").strip() or None
            parts = p_full_name.split()
            fn_c = parts[0] if parts else "Paciente"
            ln_c = " ".join(parts[1:]) if len(parts) > 1 else ((a_item.patient_last_name or "").strip() or "S/A")

            p_match = None
            if doc_c:
                p_match = db.query(Patient).filter(Patient.document_id == doc_c, Patient.is_active == True).first()
            if not p_match and ph_c:
                p_match = db.query(Patient).filter(Patient.phone == ph_c, Patient.is_active == True).first()
            if not p_match:
                p_match = db.query(Patient).filter(
                    Patient.first_name.ilike(fn_c),
                    Patient.last_name.ilike(ln_c) if ln_c else True,
                    Patient.is_active == True
                ).first()

            if p_match:
                target_pid = p_match.id
                req_ins = (a_item.insurance_name or "").strip()
                if req_ins and req_ins.lower() not in ("privado", "privado / particular", ""):
                    if (not p_match.insurance_name) or p_match.insurance_name.strip().lower() in ("privado", "privado / particular"):
                        p_match.insurance_name = req_ins
                        if getattr(a_item, "insurance_number", None):
                            p_match.insurance_number = a_item.insurance_number.strip()
                        db.commit()
            else:
                p_new = Patient(
                    doctor_id=doc_id,
                    first_name=fn_c,
                    last_name=ln_c or "S/A",
                    document_id=doc_c,
                    phone=ph_c,
                    insurance_name=(a_item.insurance_name or "").strip() or "Privado / Particular",
                    insurance_number=(getattr(a_item, "insurance_number", None) or "").strip() or None,
                    allergies=a_item.patient_allergies or None,
                    is_active=True
                )
                db.add(p_new)
                db.commit()
                db.refresh(p_new)
                target_pid = p_new.id

        if not target_pid:
            continue

        from app.routers.appointments import assign_next_queue_number
        from datetime import timedelta

        # Manejo seguro y flexible de fecha y hora
        appt_date = date.today()
        if a_item.date and a_item.date.strip():
            try:
                appt_date = datetime.strptime(a_item.date.strip()[:10], "%Y-%m-%d").date()
            except Exception:
                appt_date = date.today()

        now_dt = datetime.now()
        start_t = now_dt.time().replace(microsecond=0)
        end_t = (now_dt + timedelta(hours=1)).time().replace(microsecond=0)
        if a_item.start_time and a_item.start_time.strip() and ":" in a_item.start_time:
            try:
                time_parts = a_item.start_time.strip().split(":")
                st_h, st_m = int(time_parts[0]), int(time_parts[1])
                start_t = time(st_h, st_m)
                end_t = time((st_h + 1) % 24, st_m)
            except Exception:
                pass

        target_status = a_item.status if getattr(a_item, "status", None) else ("En Espera" if appt_date == date.today() else "Pendiente")
        queue_num = assign_next_queue_number(db, appt_date) if target_status == "En Espera" else None

        # Idempotencia y anti-duplicidad: Verificar si ya existe cita activa para este paciente en la misma fecha
        from app.routers.appointments import find_same_day_appointment
        existing_appt = find_same_day_appointment(db, target_pid, appt_date)

        if existing_appt:
            if doc_id and not existing_appt.doctor_id:
                existing_appt.doctor_id = doc_id
                db.commit()
            if a_item.client_uuid:
                appointment_id_map[a_item.client_uuid] = existing_appt.id
            processed_appointments += 1
            continue

        parsed_price = 0.0
        if a_item.price is not None:
            try:
                parsed_price = float(a_item.price)
            except Exception:
                parsed_price = 0.0

        parsed_svc_id = None
        if a_item.service_id is not None:
            try:
                parsed_svc_id = int(a_item.service_id)
            except Exception:
                parsed_svc_id = None

        new_appt = Appointment(
            patient_id=target_pid,
            doctor_id=doc_id,
            date=appt_date,
            start_time=start_t,
            end_time=end_t,
            reason=a_item.reason or "Consulta General",
            service_id=parsed_svc_id,
            price=parsed_price,
            status=target_status,
            queue_number=queue_num
        )
        db.add(new_appt)
        db.commit()
        db.refresh(new_appt)
        processed_appointments += 1

        if a_item.client_uuid:
            _record_mobile_sync_key(db, a_item.client_uuid, "appointment", new_appt.id)
            appointment_id_map[a_item.client_uuid] = new_appt.id

        # Procesar cobro si se recolectó en la tablet offline
        pay_amt = 0.0
        if getattr(a_item, "payment_amount", None) is not None:
            try:
                pay_amt = float(a_item.payment_amount)
            except Exception:
                pay_amt = 0.0

        if getattr(a_item, "collect_now", False) and pay_amt > 0:
            try:
                svc_name = a_item.reason or "Consulta Médica General"
                if parsed_svc_id:
                    svc = db.query(Service).filter(Service.id == parsed_svc_id).first()
                    if svc:
                        svc_name = svc.name
                
                p_obj = db.query(Patient).filter(Patient.id == target_pid).first()
                ins_name = a_item.insurance_name or (p_obj.insurance_name if p_obj else "Privado / Particular")
                receipt_no = generate_mobile_receipt_number()
                
                pay_rec = Payment(
                    patient_id=target_pid,
                    appointment_id=new_appt.id,
                    service_id=parsed_svc_id,
                    service_name=svc_name,
                    insurance_name=ins_name or "Privado / Particular",
                    amount=pay_amt,
                    total=pay_amt,
                    payment_method=a_item.payment_method or "Efectivo",
                    notes=a_item.payment_notes or f"Cobro offline transferido para cita #{new_appt.id}",
                    receipt_number=receipt_no,
                    created_by_id=current_user.id if current_user else 1,
                    status="paid",
                    created_at=datetime.utcnow()
                )
                db.add(pay_rec)
                db.commit()
            except Exception:
                pass

    # 3. Procesar Actualizaciones de Pacientes Offline
    for u_item in getattr(payload, "patient_updates", []):
        p_target = None
        target_uid = u_item.id or u_item.client_uuid
        if target_uid is not None:
            try:
                int_id = int(target_uid)
                p_target = db.query(Patient).filter(Patient.id == int_id).first()
            except (ValueError, TypeError):
                if str(target_uid) in patient_id_map:
                    p_target = db.query(Patient).filter(Patient.id == patient_id_map[str(target_uid)]).first()

        if not p_target and u_item.document_id and u_item.document_id.strip():
            p_target = db.query(Patient).filter(
                Patient.document_id == u_item.document_id.strip(),
                Patient.is_active == True
            ).first()

        if not p_target and u_item.phone and u_item.phone.strip():
            p_target = db.query(Patient).filter(
                Patient.phone == u_item.phone.strip(),
                Patient.is_active == True
            ).first()

        if not p_target and u_item.name and u_item.name.strip():
            parts = u_item.name.strip().split()
            if len(parts) >= 2:
                p_target = db.query(Patient).filter(
                    Patient.first_name.ilike(parts[0]),
                    Patient.last_name.ilike(" ".join(parts[1:])),
                    Patient.is_active == True
                ).first()

        if p_target:
            if u_item.first_name and u_item.first_name.strip():
                p_target.first_name = u_item.first_name.strip()
            if u_item.last_name and u_item.last_name.strip():
                p_target.last_name = u_item.last_name.strip()
            if u_item.document_id is not None:
                p_target.document_id = u_item.document_id.strip() or None
            if u_item.phone is not None:
                p_target.phone = u_item.phone.strip() or None
            if u_item.date_of_birth is not None:
                if u_item.date_of_birth.strip():
                    try:
                        p_target.date_of_birth = datetime.strptime(u_item.date_of_birth.strip()[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass
                else:
                    p_target.date_of_birth = None
            if u_item.gender is not None:
                p_target.gender = u_item.gender.strip() or None
            if u_item.email is not None:
                p_target.email = u_item.email.strip().lower() or None
            if u_item.address is not None:
                p_target.address = u_item.address.strip() or None
            if u_item.blood_type is not None:
                p_target.blood_type = u_item.blood_type.strip() or None
            if u_item.allergies is not None:
                p_target.allergies = u_item.allergies.strip() or None
            if u_item.emergency_contact_name is not None:
                p_target.emergency_contact_name = u_item.emergency_contact_name.strip() or None
            if u_item.emergency_contact_phone is not None:
                p_target.emergency_contact_phone = u_item.emergency_contact_phone.strip() or None
            if u_item.insurance_name is not None:
                p_target.insurance_name = u_item.insurance_name.strip() or "Privado / Particular"
            if u_item.insurance_number is not None:
                p_target.insurance_number = u_item.insurance_number.strip() or None
            p_target.updated_at = datetime.utcnow()
            db.commit()
            processed_updates += 1

    return {
        "success": True,
        "processed_patients": processed_patients,
        "processed_appointments": processed_appointments,
        "processed_updates": processed_updates,
        "patient_id_map": patient_id_map,
        "appointment_id_map": appointment_id_map,
        "server_time": datetime.utcnow().isoformat(),
        "message": f"Sincronización por lote completada: {processed_patients} pacientes, {processed_appointments} citas y {processed_updates} actualizaciones procesadas."
    }


@router.get("/sync/delta")
def mobile_sync_delta(
    since: Optional[str] = Query(None),
    target_date: Optional[str] = Query(None),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna la lista completa de datos actualizados para hidratar el almacenamiento local de la APK.
    """
    # Pacientes aislados por médico
    doc_id = resolve_current_doctor_id(db, current_user)
    pat_q = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None))
    if doc_id:
        pat_q = pat_q.filter(or_(Patient.doctor_id == doc_id, Patient.doctor_id.is_(None)))
    patients = pat_q.order_by(func.coalesce(Patient.last_name, ''), Patient.first_name).all()
    patients_list = []
    for p in patients:
        ln = (p.last_name or "").strip()
        fn = (p.first_name or "").strip()
        doc = (p.document_id or "").strip()
        phone = (p.phone or "").strip()
        patients_list.append({
            "id": p.id,
            "first_name": fn,
            "last_name": ln,
            "name": f"{fn} {ln}".strip(),
            "document_id": doc,
            "phone": phone,
            "email": p.email or "",
            "date_of_birth": str(p.date_of_birth) if p.date_of_birth else "",
            "gender": p.gender or "",
            "address": p.address or "",
            "emergency_contact_name": p.emergency_contact_name or "",
            "emergency_contact_phone": p.emergency_contact_phone or "",
            "allergies": p.allergies or "",
            "blood_type": p.blood_type or "",
            "insurance_name": p.insurance_name or "Privado / Particular",
            "insurance_number": p.insurance_number or "",
            "display": f"{ln}, {fn}".strip(", ") + (f" ({doc})" if doc else "") + (f" - Tel: {phone}" if phone else "")
        })

    # Citas
    appt_date = date.today()
    if target_date:
        try:
            appt_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        except Exception:
            pass

    appt_q = db.query(Appointment).filter(Appointment.date >= appt_date)
    if doc_id:
        appt_q = appt_q.filter(or_(Appointment.doctor_id == doc_id, Appointment.doctor_id.is_(None)))
    appts = appt_q.order_by(Appointment.date.asc(), Appointment.start_time.asc()).limit(150).all()
    appts_list = []
    for a in appts:
        p_name = "Paciente no encontrado"
        p_phone = ""
        p_doc = ""
        if a.patient:
            p_name = f"{a.patient.first_name} {a.patient.last_name}".strip()
            p_phone = a.patient.phone or ""
            p_doc = a.patient.document_id or ""
        appts_list.append({
            "id": a.id,
            "patient_id": a.patient_id,
            "patient_name": p_name,
            "patient_phone": p_phone,
            "patient_document_id": p_doc,
            "date": a.date.strftime("%Y-%m-%d") if a.date else "",
            "start_time": a.start_time.strftime("%H:%M") if a.start_time else "",
            "reason": a.reason or "Consulta General",
            "status": a.status or "Pendiente",
            "service_id": a.service_id,
            "price": a.price or 0.0
        })

    from app.models.service import Service
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.name.asc()).all()
    from app.services.ars_service import get_all_ars

    return {
        "server_time": datetime.utcnow().isoformat(),
        "total_patients": len(patients_list),
        "total_appointments": len(appts_list),
        "patients": patients_list,
        "appointments": appts_list,
        "services": [
            {"id": s.id, "name": s.name, "price": s.price, "color": s.color, "category": s.category}
            for s in services
        ],
        "ars": get_all_ars()
    }


# --- Cierre de Jornada Móvil (Cerrar Día / Reinicio de Sala de Espera) ---
@router.post("/close-day")
def mobile_close_day(
    request: Request,
    current_user: User = Depends(require_permission("appointments")),
    db: Session = Depends(get_db)
):
    """
    Cierre de jornada desde la aplicación móvil/tablet:
    Marca todas las citas en espera, pendientes o confirmadas de hoy y días anteriores del doctor actual como 'Completada',
    libera la sala de espera para reiniciar turnos y sincroniza de inmediato al Cloud Relay.
    """
    from app.services.relay_service import RelayService
    from app.routers.patients import resolve_current_doctor_id

    doc_id = resolve_current_doctor_id(db, current_user)
    today = date.today()
    q = db.query(Appointment).filter(
        Appointment.date <= today,
        Appointment.status.notin_(["Completada", "Cancelada", "Atendida"])
    )
    if doc_id:
        q = q.filter(Appointment.doctor_id == doc_id)
    pending_appts = q.all()

    closed_count = 0
    for a in pending_appts:
        a.status = "Completada"
        a.queue_number = None
        a.updated_at = datetime.utcnow()
        closed_count += 1

    db.commit()
    _notify_supabase()

    # Publicar inmediatamente el snapshot actualizado a la nube
    try:
        RelayService.push_snapshot_to_cloud(db)
    except Exception:
        pass

    return {
        "success": True,
        "closed_count": closed_count,
        "message": f"Jornada cerrada correctamente. Se completaron {closed_count} turnos pendientes."
    }


@router.get("/cie10/search")
def mobile_search_cie10(
    q: str = Query("", min_length=0),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    from app.models.cie10 import Cie10Code
    from app.data.cie10_catalog import OFFICIAL_CIE10_CATALOG

    term = (q or "").strip()
    query = db.query(Cie10Code)
    if term:
        query = query.filter(
            or_(
                Cie10Code.code.ilike(f"%{term}%"),
                Cie10Code.description.ilike(f"%{term}%"),
            )
        )
    rows = query.order_by(Cie10Code.code.asc()).limit(25).all()
    if rows:
        return {"items": [{"code": r.code, "description": r.description} for r in rows]}
    fallback = OFFICIAL_CIE10_CATALOG
    if term:
        tl = term.lower()
        fallback = [c for c in OFFICIAL_CIE10_CATALOG if tl in c["code"].lower() or tl in c["description"].lower()]
    return {"items": [{"code": c["code"], "description": c["description"]} for c in fallback[:25]]}


@router.post("/preauthorizations")
def mobile_create_preauthorization(
    payload: MobilePreauthCreateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    import json
    from app.models.insurance_preauthorization import InsurancePreauthorization

    doc_id = resolve_current_doctor_id(db, current_user) or current_user.id
    resolved_pat_id = None
    if payload.patient_id is not None and str(payload.patient_id).strip():
        s_pid = str(payload.patient_id).strip()
        resolved_pat_id = int(s_pid) if s_pid.isdigit() else _lookup_mobile_sync_key(db, s_pid, "patient")
    if not resolved_pat_id and payload.patient_doc:
        pat = db.query(Patient).filter(Patient.document_id == payload.patient_doc.strip(), Patient.is_active == True).first()
        if pat:
            resolved_pat_id = pat.id
    if not resolved_pat_id and payload.patient_name:
        parts = payload.patient_name.strip().split(" ", 1)
        fn = parts[0]
        ln = parts[1] if len(parts) > 1 else ""
        pat_q = db.query(Patient).filter(Patient.first_name.ilike(fn), Patient.is_active == True)
        if ln:
            pat_q = pat_q.filter(Patient.last_name.ilike(ln))
        pat = pat_q.first()
        if pat:
            resolved_pat_id = pat.id
    if not resolved_pat_id:
        raise HTTPException(status_code=404, detail="Paciente no encontrado para guardar pre-autorización.")

    preauth = InsurancePreauthorization(
        patient_id=resolved_pat_id,
        doctor_id=doc_id,
        ars_name=payload.ars_name.strip() or "SeNaSa",
        request_type=payload.service_type.strip(),
        request_date=date.today(),
        affiliate_card_number=(payload.card_number or "").strip() or None,
        presumptive_diagnosis=(payload.cie10_code or "").strip() or None,
        definitive_diagnosis=(payload.cie10_code or "").strip() or None,
        procedures_json=json.dumps([{"code": "", "procedure": payload.service_type.strip()}], ensure_ascii=False),
        treatment_plan=(payload.clinical_indication or "").strip() or None,
        notes=f"Pre-autorización registrada desde móvil por {current_user.name}",
        sede_origen="mobile_apk",
    )
    db.add(preauth)
    db.commit()
    db.refresh(preauth)

    try:
        from app.services.audit_service import AuditService
        AuditService.log_change(
            db=db,
            entity_type="insurance_preauthorization",
            entity_id=preauth.id,
            action="create",
            summary=f"Pre-autorización ARS ({preauth.ars_name}) creada desde móvil",
            patient_id=resolved_pat_id,
            user_id=current_user.id,
            new_data={"ars_name": preauth.ars_name, "service": preauth.request_type},
        )
    except Exception:
        pass

    return {"success": True, "preauthorization_id": preauth.id}



