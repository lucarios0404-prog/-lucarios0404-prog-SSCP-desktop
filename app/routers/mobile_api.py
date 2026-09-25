from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc
from datetime import datetime, date, time
from typing import Optional, List
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.payment import Payment
from app.models.setting import Setting
from app.core import security
from app.core.deps import require_current_user

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
    patient_phone: Optional[str] = None
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    reason: str

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
    notes: Optional[str] = "Pago registrado desde aplicación móvil"

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
    appt.status = payload.status
    db.commit()

    return {
        "success": True,
        "appointment_id": appt.id,
        "old_status": old_status,
        "new_status": appt.status,
        "message": f"Estado actualizado a '{appt.status}' por {current_user.name}"
    }

# --- Quick Appointment Create ---
@router.post("/appointments/quick-create")
def quick_create_appointment(
    payload: QuickAppointmentRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    patient_id = payload.patient_id

    # If no patient_id but name given, find or create patient
    if not patient_id and payload.patient_name:
        parts = payload.patient_name.strip().split(" ", 1)
        fname = parts[0]
        lname = parts[1] if len(parts) > 1 else ""
        new_patient = Patient(
            first_name=fname,
            last_name=lname,
            phone=payload.patient_phone or "",
            document_id=f"TEMP-{int(datetime.now().timestamp())}",
            is_active=True
        )
        db.add(new_patient)
        db.commit()
        db.refresh(new_patient)
        patient_id = new_patient.id

    if not patient_id:
        raise HTTPException(status_code=400, detail="Debe especificar un paciente válido")

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
        status="Pendiente"
    )
    db.add(new_appt)
    db.commit()
    db.refresh(new_appt)

    return {
        "success": True,
        "appointment_id": new_appt.id,
        "patient_id": patient_id,
        "date": str(new_appt.date),
        "start_time": new_appt.start_time.strftime("%H:%M"),
        "status": new_appt.status
    }

# --- Search Patients ---
@router.get("/patients/search")
def search_patients(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    term = f"%{q.strip()}%"
    patients = (
        db.query(Patient)
        .filter(
            or_(
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Patient.phone.ilike(term),
                Patient.document_id.ilike(term)
            )
        )
        .filter(Patient.is_active == True)
        .limit(20)
        .all()
    )

    results = []
    for p in patients:
        results.append({
            "id": p.id,
            "name": f"{p.first_name} {p.last_name}",
            "phone": p.phone or "",
            "document_id": p.document_id or "",
            "email": p.email or "",
            "allergies": getattr(p, "allergies", "") or "",
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
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
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

# --- Secretary Quick Payment ---
@router.post("/payments/quick")
def quick_register_payment(
    payload: QuickPaymentRequest,
    current_user: User = Depends(require_current_user),
    db: Session = Depends(get_db)
):
    payment = Payment(
        patient_id=payload.patient_id,
        amount=payload.amount,
        total=payload.amount,
        payment_method=payload.payment_method,
        notes=f"{payload.notes} (por {current_user.name})",
        status="paid",
        created_at=datetime.utcnow()
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return {
        "success": True,
        "payment_id": payment.id,
        "amount": payment.amount,
        "total": payment.total,
        "payment_method": payment.payment_method,
        "message": f"Pago de {payment.amount} registrado exitosamente"
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
