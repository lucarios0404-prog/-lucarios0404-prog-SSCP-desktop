from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc
from datetime import datetime, date, time
from typing import Optional, List
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
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    reason: str
    service_id: Optional[int] = None
    price: Optional[float] = None
    insurance_name: Optional[str] = None
    insurance_number: Optional[str] = None
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

# --- Schemas de Sincronización Diferida / Offline-First (Tailscale / LAN) ---
class BatchSyncPatientItem(BaseModel):
    client_uuid: Optional[str] = None
    first_name: str
    last_name: str
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
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    patient_last_name: Optional[str] = None
    patient_document_id: Optional[str] = None
    patient_phone: Optional[str] = None
    patient_allergies: Optional[str] = None
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    reason: Optional[str] = "Consulta General"
    service_id: Optional[int] = None
    price: Optional[float] = None
    insurance_name: Optional[str] = None
    insurance_number: Optional[str] = None
    collect_now: Optional[bool] = False
    payment_amount: Optional[float] = None
    payment_method: Optional[str] = "Efectivo"
    payment_notes: Optional[str] = None
    created_at: Optional[str] = None

class MobileBatchSyncRequest(BaseModel):
    patients: List[BatchSyncPatientItem] = []
    appointments: List[BatchSyncAppointmentItem] = []
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

    # Query today's appointments
    appointments = (
        db.query(Appointment)
        .filter(Appointment.date == target_date)
        .order_by(Appointment.start_time.asc())
        .all()
    )

    stats = {
        "total": len(appointments),
        "waiting": sum(1 for a in appointments if a.status == "En Espera"),
        "in_consultation": sum(1 for a in appointments if a.status == "En Consulta"),
        "completed": sum(1 for a in appointments if a.status == "Atendida"),
        "pending": sum(1 for a in appointments if a.status in ["Pendiente", "Confirmada"]),
    }

    appts_data = []
    for a in appointments:
        p = a.patient
        p_name = f"{p.first_name} {p.last_name}" if p else "Paciente no registrado"
        p_phone = p.phone if p else ""
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
            "notes": a.notes or "",
        })

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

    try:
        appt_date = datetime.strptime(payload.date, "%Y-%m-%d").date()
        time_parts = payload.start_time.split(":")
        start_t = time(int(time_parts[0]), int(time_parts[1]))
        end_t = time((int(time_parts[0]) + 1) % 24, int(time_parts[1]))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Formato de fecha u hora inválido: {e}")

    new_appt = Appointment(
        patient_id=patient_id,
        date=appt_date,
        start_time=start_t,
        end_time=end_t,
        reason=payload.reason or "Consulta General",
        service_id=payload.service_id,
        price=payload.price or 0.0,
        status="Pendiente"
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
    """Retorna la lista completa de pacientes activos ordenada alfabéticamente (como en pagos/citas del doctor) para selects y buscadores."""
    patients = (
        db.query(Patient)
        .filter(or_(Patient.is_active == True, Patient.is_active == None))
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

def _filter_active_patients(db: Session, q: Optional[str] = None):
    """Helper unificado para filtrado y búsqueda de pacientes activos en la API móvil."""
    query = db.query(Patient).filter(Patient.is_active == True)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Patient.phone.ilike(term),
                Patient.document_id.ilike(term),
                Patient.email.ilike(term)
            )
        )
    return query

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
    query = _filter_active_patients(db, q)
    total = query.count()
    patients = query.order_by(Patient.id.desc()).offset((page - 1) * limit).limit(limit).all()

    results = []
    for p in patients:
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
            "created_at": p.created_at.strftime("%d/%m/%Y") if p.created_at else ""
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
    doc_id = payload.document_id.strip() if payload.document_id and payload.document_id.strip() else None
    phone = payload.phone.strip() if payload.phone and payload.phone.strip() else None

    if not fn or not ln:
        raise HTTPException(status_code=400, detail="El nombre y apellido del paciente son obligatorios")

    # Validación anti-duplicados por cédula
    if doc_id:
        dup_doc = db.query(Patient).filter(Patient.document_id == doc_id, Patient.is_active == True).first()
        if dup_doc:
            raise HTTPException(
                status_code=400,
                detail=f"Ya existe un paciente con la cédula '{doc_id}': {dup_doc.first_name} {dup_doc.last_name}. Utilice el paciente existente para evitar duplicidad."
            )

    dob = None
    if payload.date_of_birth:
        try:
            dob = datetime.strptime(payload.date_of_birth, "%Y-%m-%d").date()
        except Exception:
            pass

    new_patient = Patient(
        first_name=fn,
        last_name=ln,
        document_id=doc_id,
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

# --- Ficha Detallada del Paciente para la Secretaria / Doctor ---
@router.get("/patients/{patient_id}/details")
def get_mobile_patient_details(
    patient_id: int,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.is_active == True).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    # Citas del paciente
    appts = db.query(Appointment).filter(Appointment.patient_id == patient_id).order_by(Appointment.date.desc(), Appointment.start_time.desc()).limit(10).all()
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
    payments = db.query(Payment).filter(Payment.patient_id == patient_id).order_by(Payment.created_at.desc()).limit(5).all()
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
            "created_at": patient.created_at.strftime("%d/%m/%Y") if patient.created_at else ""
        },
        "appointments": appts_data,
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

    # If associated appointment, mark as Atendida
    if payload.appointment_id:
        appt = db.query(Appointment).filter(Appointment.id == payload.appointment_id).first()
        if appt:
            appt.status = "Atendida"

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

    payment = Payment(
        patient_id=payload.patient_id,
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

        if st == "Atendida":
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
    Recibe un lote de citas y pacientes creados en modo offline por la APK/Móvil.
    Reconcilia registros existentes, previene duplicados por cédula/teléfono/horario
    y devuelve el mapeo de IDs asignados en SQLite para que el móvil actualice su caché.
    """
    patient_id_map = {}
    processed_patients = 0
    processed_appointments = 0

    # 1. Procesar Pacientes Offline
    for p_item in payload.patients:
        doc_clean = (p_item.document_id or "").strip() or None
        phone_clean = (p_item.phone or "").strip() or None
        fn = p_item.first_name.strip()
        ln = p_item.last_name.strip()

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
                    dob_val = datetime.strptime(p_item.date_of_birth, "%Y-%m-%d").date()
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
        target_pid = a_item.patient_id
        if not target_pid and a_item.patient_client_uuid:
            target_pid = patient_id_map.get(a_item.patient_client_uuid)

        if not target_pid and a_item.patient_name:
            # Resolver paciente al vuelo
            doc_c = (a_item.patient_document_id or "").strip() or None
            ph_c = (a_item.patient_phone or "").strip() or None
            fn_c = a_item.patient_name.strip()
            ln_c = (a_item.patient_last_name or "").strip()

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

        try:
            appt_date = datetime.strptime(a_item.date, "%Y-%m-%d").date()
            time_parts = a_item.start_time.split(":")
            st_h, st_m = int(time_parts[0]), int(time_parts[1])
            start_t = time(st_h, st_m)
            end_t = time((st_h + 1) % 24, st_m)
        except Exception:
            continue

        # Idempotencia: Verificar si ya existe cita para este paciente en misma fecha y hora
        existing_appt = db.query(Appointment).filter(
            Appointment.patient_id == target_pid,
            Appointment.date == appt_date,
            Appointment.start_time == start_t
        ).first()

        if existing_appt:
            if a_item.client_uuid:
                appointment_id_map[a_item.client_uuid] = existing_appt.id
            processed_appointments += 1
            continue

        new_appt = Appointment(
            patient_id=target_pid,
            date=appt_date,
            start_time=start_t,
            end_time=end_t,
            reason=a_item.reason or "Consulta General",
            service_id=a_item.service_id,
            price=a_item.price or 0.0,
            status="Pendiente"
        )
        db.add(new_appt)
        db.commit()
        db.refresh(new_appt)
        processed_appointments += 1

        if a_item.client_uuid:
            appointment_id_map[a_item.client_uuid] = new_appt.id

    return {
        "success": True,
        "processed_patients": processed_patients,
        "processed_appointments": processed_appointments,
        "patient_id_map": patient_id_map,
        "appointment_id_map": appointment_id_map,
        "server_time": datetime.utcnow().isoformat(),
        "message": f"Sincronización por lote completada: {processed_patients} pacientes y {processed_appointments} citas procesadas."
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


