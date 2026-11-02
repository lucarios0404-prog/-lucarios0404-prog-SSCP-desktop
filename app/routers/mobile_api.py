from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc
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

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

# --- Pydantic Schemas for Mobile ---
class MobileLoginRequest(BaseModel):
    email: str
    password: str

class StatusUpdateRequest(BaseModel):
    status: str  # Pendiente, En Espera, En Consulta, Atendida, Cancelada

class QuickAppointmentRequest(BaseModel):
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    patient_last_name: Optional[str] = None
    patient_document_id: Optional[str] = None
    patient_phone: Optional[str] = None
    patient_allergies: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD
    start_time: Optional[str] = None  # HH:MM
    reason: str
    service_id: Optional[int] = None
    price: Optional[float] = None
    insurance_name: Optional[str] = None
    insurance_number: Optional[str] = None
    status: Optional[str] = "En Espera"
    # Lógica de Cobro Inmediato vs Cobrar Más Tarde
    collect_now: Optional[bool] = False
    payment_amount: Optional[float] = None
    payment_method: Optional[str] = "Efectivo"
    payment_notes: Optional[str] = None

class MobilePatientCreateRequest(BaseModel):
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
    patient_id: int
    appointment_id: Optional[int] = None
    reason: Optional[str] = "Consulta General"
    symptoms: Optional[str] = ""
    diagnosis: str
    treatment: Optional[str] = ""
    notes: Optional[str] = ""

class QuickPaymentRequest(BaseModel):
    patient_id: int
    amount: float
    payment_method: str = "Efectivo"
    appointment_id: Optional[int] = None
    service_id: Optional[int] = None
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
    setting = db.query(Setting).first()
    return {
        "status": "online",
        "app": "SSCP Desktop & Mobile Gateway",
        "clinic_name": setting.clinic_name if setting else "Centro Médico SSCP",
        "doctor_name": setting.doctor_name if setting else "Dr. Especialista",
        "timestamp": datetime.now().isoformat()
    }

# --- Mobile Login ---
@router.post("/login")
def mobile_login(payload: MobileLoginRequest, db: Session = Depends(get_db)):
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

    token = security.create_access_token(data={"email": user.email, "role": user.role})
    setting = db.query(Setting).first()

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
        }
    }

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

    # Query today's appointments (aislado estrictamente por médico)
    from app.routers.patients import resolve_current_doctor_id
    doc_id = resolve_current_doctor_id(db, current_user)
    appts_q = db.query(Appointment).filter(Appointment.date == target_date)
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

    old_status = appt.status
    if payload.status == "En Espera" and not appt.queue_number:
        from app.routers.appointments import assign_next_queue_number
        appt.queue_number = assign_next_queue_number(db, appt.date)

    appt.status = payload.status
    appt.updated_at = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "appointment_id": appt.id,
        "queue_number": appt.queue_number,
        "old_status": old_status,
        "new_status": appt.status,
        "message": f"Estado actualizado a '{appt.status}' por {current_user.name}"
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

    p_name = f"{appt.patient.first_name} {appt.patient.last_name}" if appt.patient else "Paciente"
    return {
        "success": True,
        "appointment_id": appt.id,
        "queue_number": appt.queue_number,
        "status": appt.status,
        "message": f"Turno #{appt.queue_number} asignado a {p_name}"
    }

# --- Quick Appointment Create ---
@router.post("/appointments/quick-create")
def quick_create_appointment(
    payload: QuickAppointmentRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    patient_id = payload.patient_id

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
    from app.routers.appointments import assign_next_queue_number
    from datetime import timedelta
    doc_id = resolve_current_doctor_id(db, current_user)

    appt_date = date.today()
    if payload.date and payload.date.strip():
        try:
            appt_date = datetime.strptime(payload.date.strip()[:10], "%Y-%m-%d").date()
        except Exception:
            appt_date = date.today()

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
        service_id=payload.service_id,
        price=payload.price or 0.0,
        status=target_status,
        queue_number=queue_num
    )
    db.add(new_appt)
    db.commit()
    db.refresh(new_appt)

    payment_record = None
    if payload.collect_now and payload.payment_amount and payload.payment_amount > 0:
        svc_name = payload.reason or "Consulta Médica General"
        if payload.service_id:
            svc = db.query(Service).filter(Service.id == payload.service_id).first()
            if svc:
                svc_name = svc.name
        
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        ins_name = payload.insurance_name or (p.insurance_name if p else "Privado / Particular")
        receipt_no = generate_mobile_receipt_number()
        
        note_text = payload.payment_notes or f"Cobro inmediato al agendar cita #{new_appt.id} (por {current_user.name})"
        payment_record = Payment(
            patient_id=patient_id,
            appointment_id=new_appt.id,
            service_id=payload.service_id,
            service_name=svc_name,
            insurance_name=ins_name or "Privado / Particular",
            amount=payload.payment_amount,
            total=payload.payment_amount,
            payment_method=payload.payment_method or "Efectivo",
            notes=note_text,
            receipt_number=receipt_no,
            created_by_id=current_user.id,
            status="paid",
            created_at=datetime.utcnow()
        )
        db.add(payment_record)
        db.commit()
        db.refresh(payment_record)

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
        has_doc_patients = db.query(Patient.id).filter(
            or_(Patient.is_active == True, Patient.is_active == None),
            Patient.doctor_id == doc_id
        ).first() is not None
        if has_doc_patients:
            query = query.filter(Patient.doctor_id == doc_id)

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
        has_doc_patients = db.query(Patient.id).filter(
            or_(Patient.is_active == True, Patient.is_active == None),
            Patient.doctor_id == doc_id
        ).first() is not None
        if has_doc_patients:
            query = query.filter(Patient.doctor_id == doc_id)
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
@router.post("/patients")
def create_mobile_patient(
    payload: MobilePatientCreateRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    """Alta oficial de paciente desde la aplicación móvil de secretaría."""
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
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un paciente con la cédula '{patient_document_id}': {dup_doc.first_name} {dup_doc.last_name}. Utilice el paciente existente para evitar duplicidad."
            )

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

    return {
        "success": True,
        "patient": {
            "id": new_patient.id,
            "name": f"{new_patient.first_name} {new_patient.last_name}",
            "first_name": new_patient.first_name,
            "last_name": new_patient.last_name,
            "document_id": new_patient.document_id or "",
            "phone": new_patient.phone or "",
            "email": new_patient.email or "",
            "date_of_birth": str(new_patient.date_of_birth) if new_patient.date_of_birth else "",
            "gender": new_patient.gender or "",
            "address": new_patient.address or "",
            "insurance_name": new_patient.insurance_name or "Privado / Particular",
            "insurance_number": new_patient.insurance_number or ""
        },
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

    # Consultas clínicas / Historia del paciente realizada por el doctor
    consultations = db.query(Consultation).filter(
        Consultation.patient_id == resolved_patient_id
    ).order_by(Consultation.created_at.desc()).limit(20).all()
    consultations_data = []
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
            "emergency_contact": f"{patient.emergency_contact_name or ''} {patient.emergency_contact_phone or ''}".strip() or "No registrado",
            "insurance_name": patient.insurance_name or "Privado / Particular",
            "insurance_number": patient.insurance_number or "",
            "created_at": patient.created_at.strftime("%d/%m/%Y") if patient.created_at else "",
            "visit_count": max(len(consultations_data), len([a for a in appts_data if a.get("status") in ("Atendida", "Completada")]))
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
    patients = _filter_active_patients(db, q).limit(20).all()

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
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    # Recent consultations
    consultations = (
        db.query(Consultation)
        .filter(Consultation.patient_id == patient_id)
        .order_by(desc(Consultation.created_at))
        .limit(3)
        .all()
    )

    past_records = []
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
    new_cons = Consultation(
        patient_id=payload.patient_id,
        doctor_id=current_user.id,
        reason=payload.reason or "Consulta médica",
        symptoms=payload.symptoms or "",
        diagnosis=payload.diagnosis,
        treatment=payload.treatment or "",
        notes=payload.notes or "",
        created_at=datetime.utcnow()
    )
    db.add(new_cons)

    # If associated appointment, mark as Completada
    if payload.appointment_id:
        appt = db.query(Appointment).filter(Appointment.id == payload.appointment_id).first()
        if appt:
            appt.status = "Completada"

    db.commit()
    db.refresh(new_cons)

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
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    service_name = payload.service_name or "Consulta Médica General"
    if payload.item_type == "articulo" and payload.service_name:
        clean_item = payload.service_name.strip()
        if not clean_item.startswith("[Artículo]") and not clean_item.startswith("[Insumo]"):
            service_name = f"[Artículo] {clean_item}"
        else:
            service_name = clean_item
    elif payload.service_id:
        svc = db.query(Service).filter(Service.id == payload.service_id).first()
        if svc and (not payload.service_name or payload.service_name == "Consulta Médica General"):
            service_name = svc.name

    ins_name = payload.insurance_name
    if not ins_name:
        p = db.query(Patient).filter(Patient.id == payload.patient_id).first()
        if p and p.insurance_name:
            ins_name = p.insurance_name

    notes_clean = f"{payload.notes} (por {current_user.name})" if payload.notes else f"Cobro registrado por {current_user.name}"
    receipt_no = generate_mobile_receipt_number()

    appt_id = payload.appointment_id if payload.appointment_id and payload.appointment_id > 0 else None
    if not appt_id:
        today = date.today()
        today_appt = db.query(Appointment).filter(
            Appointment.patient_id == payload.patient_id,
            Appointment.date == today
        ).first()
        if today_appt:
            appt_id = today_appt.id

    payment = Payment(
        patient_id=payload.patient_id,
        appointment_id=appt_id,
        service_id=payload.service_id if payload.item_type != "articulo" else None,
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
    db.commit()
    db.refresh(payment)

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
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Registro de pago no encontrado")

    clean_method = payload.payment_method.strip()
    pm_lower = clean_method.lower()
    if "trans" in pm_lower:
        canonical_method = "Transferencia"
    elif "tarjeta" in pm_lower or "card" in pm_lower:
        canonical_method = "Tarjeta"
    elif "seguro" in pm_lower or "insur" in pm_lower:
        canonical_method = "Seguro Médico"
    else:
        canonical_method = "Efectivo"

    old_method = payment.payment_method
    payment.payment_method = canonical_method
    if payload.amount is not None and payload.amount >= 0:
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
        if "trans" in pm_lower:
            canonical_method = "Transferencia"
        elif "tarjeta" in pm_lower or "card" in pm_lower:
            canonical_method = "Tarjeta"
        elif "seguro" in pm_lower or "insur" in pm_lower:
            canonical_method = "Seguro Médico"
        else:
            canonical_method = "Efectivo"

        amt = payload.amount if payload.amount is not None and payload.amount >= 0 else (appt.price or 0.0)
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
            created_at=datetime.utcnow()
        )
        db.add(new_pay)
        db.commit()
        db.refresh(new_pay)
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
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category, Service.name).all()
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

    # 2. Pacientes Vistos / Consultas Realizadas
    consultations = (
        db.query(Consultation)
        .filter(Consultation.created_at >= start_dt, Consultation.created_at <= end_dt)
        .order_by(Consultation.created_at.desc())
        .all()
    )

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
            "diagnosis": c.diagnosis or "Sin diagnóstico",
            "treatment": c.treatment or "",
            "notes": c.notes or ""
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

# --- Catálogo de Servicios para la App Móvil (Talonario 1-Clic) ---
@router.get("/services")
def list_mobile_services(
    db: Session = Depends(get_db)
):
    from app.models.service import Service
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category.asc(), Service.name.asc()).all()
    return {
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "price": s.price,
                "color": s.color,
                "category": s.category,
                "is_active": s.is_active
            }
            for s in services
        ],
        "total": len(services)
    }

# --- Catálogo de ARS con Logos para la App Móvil ---
@router.get("/ars")
def list_mobile_ars():
    from app.services.ars_service import get_all_ars
    return {
        "ars": get_all_ars()
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
        if doc_clean:
            existing = db.query(Patient).filter(Patient.document_id == doc_clean, Patient.is_active == True).first()
        if not existing and phone_clean:
            existing = db.query(Patient).filter(Patient.phone == phone_clean, Patient.is_active == True).first()
        if not existing and fn and ln:
            existing = db.query(Patient).filter(
                Patient.first_name.ilike(fn),
                Patient.last_name.ilike(ln),
                Patient.is_active == True
            ).first()

        if existing:
            # Actualizar datos complementarios si faltaban
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

        from app.routers.patients import resolve_current_doctor_id
        from app.routers.appointments import assign_next_queue_number
        from datetime import timedelta
        doc_id = resolve_current_doctor_id(db, current_user)

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

        # Idempotencia: Verificar si ya existe cita para este paciente en misma fecha y hora
        existing_appt = db.query(Appointment).filter(
            Appointment.patient_id == target_pid,
            Appointment.date == appt_date,
            Appointment.start_time == start_t
        ).first()

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
    # Pacientes
    patients = (
        db.query(Patient)
        .filter(or_(Patient.is_active == True, Patient.is_active == None))
        .order_by(func.coalesce(Patient.last_name, ''), Patient.first_name)
        .all()
    )
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

    appts = (
        db.query(Appointment)
        .filter(Appointment.date >= appt_date)
        .order_by(Appointment.date.asc(), Appointment.start_time.asc())
        .limit(150)
        .all()
    )
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
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category.asc(), Service.name.asc()).all()
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
    db: Session = Depends(get_db)
):
    """
    Cierre de jornada desde la aplicación móvil/tablet:
    Marca todas las citas en espera, pendientes o confirmadas de hoy y días anteriores como 'Completada',
    libera la sala de espera para reiniciar turnos y sincroniza de inmediato al Cloud Relay.
    """
    from app.services.relay_service import RelayService
    today = date.today()
    pending_appts = db.query(Appointment).filter(
        Appointment.date <= today,
        Appointment.status.notin_(["Completada", "Cancelada", "Atendida"])
    ).all()

    closed_count = 0
    for a in pending_appts:
        a.status = "Completada"
        a.updated_at = datetime.utcnow()
        closed_count += 1

    db.commit()

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



