"""Reconciliación compartida entre consultas médicas y citas en espera/pendientes.

Centraliza el cierre automático de citas activas (`Pendiente`, `Confirmada`,
`En Espera`, `En Consulta`) cuando existe una consulta médica asociada o
compatible en fecha, evitando desfases entre hora local y UTC y asegurando
marcas de tiempo compatibles con la sincronización hacia Supabase.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.consultation import Consultation


ACTIVE_APPOINTMENT_STATUSES: Set[str] = {
    "pendiente",
    "confirmada",
    "en espera",
    "waiting",
    "espera",
    "en consulta",
    "en_consulta",
    "in_consultation",
    "in-consultation",
    "atendiendo",
    "consulting",
}

WAITING_OR_CONSULTING_STATUSES: Set[str] = {
    "en espera",
    "waiting",
    "espera",
    "en consulta",
    "en_consulta",
    "in_consultation",
    "in-consultation",
    "atendiendo",
    "consulting",
}

COMPLETED_APPOINTMENT_STATUSES: Set[str] = {
    "completada",
    "atendida",
    "listo",
    "completed",
    "finished",
}

CANCELLED_APPOINTMENT_STATUSES: Set[str] = {
    "cancelada",
    "canceled",
    "cancelled",
    "anulada",
    "no_show",
    "no asistió",
}


def normalize_appointment_status(status: Optional[str]) -> str:
    return " ".join(str(status or "").strip().lower().split())


def is_active_appointment_status(status: Optional[str]) -> bool:
    return normalize_appointment_status(status) in ACTIVE_APPOINTMENT_STATUSES


def is_completed_appointment_status(status: Optional[str]) -> bool:
    return normalize_appointment_status(status) in COMPLETED_APPOINTMENT_STATUSES


def is_terminal_appointment_status(status: Optional[str]) -> bool:
    norm = normalize_appointment_status(status)
    return norm in COMPLETED_APPOINTMENT_STATUSES or norm in CANCELLED_APPOINTMENT_STATUSES


def _parse_iso_naive_utc(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        from datetime import timezone
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def compute_monotonic_sync_utc(db: Session) -> datetime:
    """Devuelve UTC naive garantizado >= último timestamp remoto visto + 3s."""
    now_utc = datetime.utcnow()
    try:
        row = db.execute(
            text("SELECT value FROM supabase_sync_meta WHERE key = 'max_remote_ts'")
        ).fetchone()
        if row and row[0]:
            remote_dt = _parse_iso_naive_utc(str(row[0]))
            if remote_dt and remote_dt + timedelta(seconds=3) > now_utc:
                return remote_dt + timedelta(seconds=3)
    except Exception:
        pass
    return now_utc


def _matches_consultation_for_appointment(
    cand: Appointment,
    consult: Consultation,
    local_today: date,
) -> bool:
    if consult.appointment_id and cand.id and int(consult.appointment_id) == int(cand.id):
        return True
    if not consult.patient_id or not cand.patient_id or int(consult.patient_id) != int(cand.patient_id):
        return False
    if getattr(cand, "doctor_id", None) and getattr(consult, "doctor_id", None):
        if int(cand.doctor_id) != int(consult.doctor_id):
            return False

    c_date = consult.created_at.date() if consult.created_at else local_today
    if not cand.date:
        return True

    # Mismo día calendario: siempre concilia aunque created_at de cita sea UTC y consulta local
    if cand.date == c_date:
        return True

    # Cita previa (días anteriores) atendida en consulta posterior
    if cand.date < c_date and cand.date <= local_today:
        if cand.created_at is None or consult.created_at is None:
            return True
        if consult.created_at >= (cand.created_at - timedelta(hours=12)):
            return True

    # Tolerancia por desfase UTC nocturno (ej. celular creó En Espera a las 23:00 local con fecha UTC +1)
    norm_status = normalize_appointment_status(cand.status)
    if cand.date == c_date + timedelta(days=1) and norm_status in WAITING_OR_CONSULTING_STATUSES:
        if cand.created_at is None or consult.created_at is None:
            return True
        if abs((consult.created_at - cand.created_at).total_seconds()) <= 18 * 3600:
            return True

    return False


def has_consultation_for_appointment(db: Session, appt: Appointment) -> bool:
    if not appt or not appt.id:
        return False
    direct = db.query(Consultation.id).filter(Consultation.appointment_id == appt.id).first()
    if direct:
        return True
    if not appt.patient_id:
        return False
    consults = db.query(Consultation).filter(Consultation.patient_id == appt.patient_id).all()
    local_today = date.today()
    return any(_matches_consultation_for_appointment(appt, c, local_today) for c in consults)


def reconcile_completed_appointments(
    db: Session,
    *,
    patient_id: Optional[int] = None,
    appointment_id: Optional[int] = None,
    consultation: Optional[Consultation] = None,
    target_date: Optional[date] = None,
) -> int:
    """Marca como `Completada` las citas activas atendidas por consulta y actualiza `updated_at`.

    Si se pasa `consultation` (al crear o importar una consulta), cierra la cita
    explícita y todas las citas activas del paciente en la ventana del día actual o previa,
    enlazando `consultation.appointment_id` si venía vacío.
    Si se llama sin `consultation`, revisa todas las citas activas (o las del
    `patient_id`) y las cierra si ya existe una consulta compatible.
    """
    sync_now = compute_monotonic_sync_utc(db)
    changed = 0
    local_today = date.today()

    if consultation is not None or (appointment_id is not None and appointment_id > 0):
        eff_pid = patient_id or (consultation.patient_id if consultation else None)
        ref_date = target_date or (
            consultation.created_at.date() if consultation and consultation.created_at else local_today
        )
        matched_appts: List[Appointment] = []

        if appointment_id and appointment_id > 0:
            explicit = db.query(Appointment).filter(Appointment.id == appointment_id).first()
            if explicit and not is_terminal_appointment_status(explicit.status):
                explicit.status = "Completada"
                explicit.updated_at = sync_now
                changed += 1
                matched_appts.append(explicit)

        if eff_pid:
            active_rows = (
                db.query(Appointment)
                .filter(
                    Appointment.patient_id == eff_pid,
                    func.lower(func.trim(Appointment.status)).in_(ACTIVE_APPOINTMENT_STATUSES),
                )
                .order_by(Appointment.date.desc(), Appointment.id.desc())
                .all()
            )
            utc_now = datetime.utcnow()
            for cand in active_rows:
                if appointment_id and cand.id == appointment_id:
                    continue
                if consultation is not None and getattr(cand, "doctor_id", None) and getattr(consultation, "doctor_id", None):
                    if int(cand.doctor_id) != int(consultation.doctor_id):
                        continue
                norm = normalize_appointment_status(cand.status)
                is_same_or_past = cand.date is None or cand.date <= ref_date
                is_utc_shift_wait = (
                    cand.date == ref_date + timedelta(days=1)
                    and norm in WAITING_OR_CONSULTING_STATUSES
                    and (cand.created_at is None or abs((utc_now - cand.created_at).total_seconds()) <= 18 * 3600)
                )
                if is_same_or_past or is_utc_shift_wait:
                    cand.status = "Completada"
                    cand.updated_at = sync_now
                    changed += 1
                    matched_appts.append(cand)

        if consultation is not None and not consultation.appointment_id and matched_appts:
            consultation.appointment_id = matched_appts[0].id

        return changed

    # Conciliación general de lectura (Dashboard, Citas, Ficha Paciente, Pull Incremental)
    q = db.query(Appointment).filter(
        func.lower(func.trim(Appointment.status)).in_(ACTIVE_APPOINTMENT_STATUSES)
    )
    if patient_id is not None:
        q = q.filter(Appointment.patient_id == patient_id)
    pending_candidates = q.all()
    if not pending_candidates:
        return 0

    cand_ids = [c.id for c in pending_candidates if c.id]
    patient_ids = list({c.patient_id for c in pending_candidates if c.patient_id})

    direct_appt_ids: Set[int] = set()
    if cand_ids:
        for row in db.query(Consultation.appointment_id).filter(
            Consultation.appointment_id.in_(cand_ids)
        ).all():
            if row[0]:
                direct_appt_ids.add(int(row[0]))

    consults_by_patient: Dict[int, List[Consultation]] = {}
    if patient_ids:
        for cons in (
            db.query(Consultation)
            .filter(Consultation.patient_id.in_(patient_ids))
            .order_by(Consultation.created_at.desc(), Consultation.id.desc())
            .all()
        ):
            if cons.patient_id:
                consults_by_patient.setdefault(int(cons.patient_id), []).append(cons)

    for cand in pending_candidates:
        matched = bool(cand.id and int(cand.id) in direct_appt_ids)
        if not matched and cand.patient_id:
            for cons in consults_by_patient.get(int(cand.patient_id), []):
                if _matches_consultation_for_appointment(cand, cons, local_today):
                    matched = True
                    break
        if matched:
            cand.status = "Completada"
            cand.updated_at = sync_now
            changed += 1

    return changed
