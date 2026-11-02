import calendar
import json
import re
import csv
import io
from datetime import datetime, date
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response, Query
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.payment import Payment
from app.models.vital_sign import VitalSign
from app.models.appointment import Appointment
from app.models.template import ClinicalTemplate
from app.models.setting import Setting
from app.routers.settings import get_or_create_settings
from app.core.deps import require_current_user, require_permission
from app.services.pdf_service import generate_executive_report_pdf, generate_secretary_daily_report_pdf

router = APIRouter(prefix="/reports", tags=["reports"])
from app.core.templates import templates

def calculate_age(dob: date) -> int:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def parse_date_range(start_date: str = None, end_date: str = None):
    start_dt = None
    end_dt = None
    s_clean = (start_date or "").strip()
    e_clean = (end_date or "").strip()
    if s_clean:
        try:
            d = datetime.strptime(s_clean, "%Y-%m-%d").date()
            start_dt = datetime.combine(d, datetime.min.time())
        except ValueError:
            s_clean = ""
    if e_clean:
        try:
            d = datetime.strptime(e_clean, "%Y-%m-%d").date()
            end_dt = datetime.combine(d, datetime.max.time())
        except ValueError:
            e_clean = ""
    return start_dt, end_dt, s_clean, e_clean

@router.get("/")
def reports_dashboard(
    request: Request,
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Panel de Inteligencia Clínica y Estadísticas Médicas (F14) con filtro dinámico por rango de fechas.
    """
    start_dt, end_dt, s_str, e_str = parse_date_range(start_date, end_date)
    is_filtered = bool(start_dt or end_dt)

    # 1. Consultas y Morbilidad (Filtradas por fecha)
    c_query = db.query(Consultation)
    if start_dt:
        c_query = c_query.filter(Consultation.created_at >= start_dt)
    if end_dt:
        c_query = c_query.filter(Consultation.created_at <= end_dt)
    consultations = c_query.all()
    total_consultations = len(consultations)

    # 2. Signos Vitales
    v_query = db.query(VitalSign)
    if start_dt:
        v_query = v_query.filter(VitalSign.recorded_at >= start_dt)
    if end_dt:
        v_query = v_query.filter(VitalSign.recorded_at <= end_dt)
    total_vitals = v_query.count()

    # 3. Finanzas y Pagos
    p_query = db.query(Payment)
    if start_dt:
        p_query = p_query.filter(Payment.created_at >= start_dt)
    if end_dt:
        p_query = p_query.filter(Payment.created_at <= end_dt)
    payments = p_query.all()
    total_payments = len(payments)
    total_collected = sum(p.total for p in payments if p.status == "paid")
    total_pending = sum(p.total for p in payments if p.status == "pending")

    # 4. Pacientes
    total_patients = db.query(Patient).count()
    if is_filtered:
        pat_query = db.query(Patient)
        if start_dt:
            pat_query = pat_query.filter(Patient.created_at >= start_dt)
        if end_dt:
            pat_query = pat_query.filter(Patient.created_at <= end_dt)
        period_patients = pat_query.count()
    else:
        period_patients = total_patients

    # 5. Top Diagnósticos Médicos (Morbilidad en el período)
    diag_counter = Counter()
    for c in consultations:
        if c.diagnosis and c.diagnosis.strip():
            lines = [d.strip() for d in c.diagnosis.split("\n") if d.strip()]
            for line in lines:
                diag_counter[line[:60]] += 1

    top_diagnoses = [
        {"name": name, "count": count, "percent": round((count / max(total_consultations, 1)) * 100, 1)}
        for name, count in diag_counter.most_common(6)
    ]

    # 6. Distribución de Pacientes por Género y Edad
    if is_filtered and consultations:
        patient_ids = {c.patient_id for c in consultations if c.patient_id}
        patients = db.query(Patient).filter(Patient.id.in_(patient_ids)).all() if patient_ids else []
    else:
        patients = db.query(Patient).all()

    gender_counts = {"male": 0, "female": 0, "other": 0}
    age_groups = {"pediatric": 0, "young_adult": 0, "middle_adult": 0, "senior": 0, "unknown": 0}

    for p in patients:
        g = (p.gender or "").lower()
        if g in ["m", "male", "masculino"]:
            gender_counts["male"] += 1
        elif g in ["f", "female", "femenino"]:
            gender_counts["female"] += 1
        else:
            gender_counts["other"] += 1

        age = calculate_age(p.date_of_birth)
        if age is None:
            age_groups["unknown"] += 1
        elif age < 18:
            age_groups["pediatric"] += 1
        elif age <= 35:
            age_groups["young_adult"] += 1
        elif age <= 60:
            age_groups["middle_adult"] += 1
        else:
            age_groups["senior"] += 1

    return templates.TemplateResponse(
        request=request,
        name="reports/index.html",
        context={
            "user": current_user,
            "total_patients": total_patients,
            "period_patients": period_patients,
            "total_consultations": total_consultations,
            "total_payments": total_payments,
            "total_vitals": total_vitals,
            "top_diagnoses": top_diagnoses,
            "gender_counts": gender_counts,
            "age_groups": age_groups,
            "total_collected": total_collected,
            "total_pending": total_pending,
            "today_str": date.today().strftime("%Y-%m-%d"),
            "start_date": s_str,
            "end_date": e_str,
            "is_filtered": is_filtered,
        }
    )

@router.get("/export/pdf")
def export_executive_pdf(
    request: Request,
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Exportación del Reporte Ejecutivo Clínico completo a PDF con membrete y logo del doctor, respetando el filtro de fechas.
    """
    setting = get_or_create_settings(db)
    start_dt, end_dt, s_str, e_str = parse_date_range(start_date, end_date)
    is_filtered = bool(start_dt or end_dt)

    c_query = db.query(Consultation)
    if start_dt: c_query = c_query.filter(Consultation.created_at >= start_dt)
    if end_dt: c_query = c_query.filter(Consultation.created_at <= end_dt)
    consultations = c_query.all()
    total_consultations = len(consultations)

    v_query = db.query(VitalSign)
    if start_dt: v_query = v_query.filter(VitalSign.recorded_at >= start_dt)
    if end_dt: v_query = v_query.filter(VitalSign.recorded_at <= end_dt)
    total_vitals = v_query.count()

    p_query = db.query(Payment)
    if start_dt: p_query = p_query.filter(Payment.created_at >= start_dt)
    if end_dt: p_query = p_query.filter(Payment.created_at <= end_dt)
    payments = p_query.all()
    total_payments = len(payments)
    total_collected = sum(p.total for p in payments if p.status == "paid")
    total_pending = sum(p.total for p in payments if p.status == "pending")

    total_patients = db.query(Patient).count()

    diag_counter = Counter()
    for c in consultations:
        if c.diagnosis and c.diagnosis.strip():
            for line in [d.strip() for d in c.diagnosis.split("\n") if d.strip()]:
                diag_counter[line[:60]] += 1
    top_diagnoses = [
        {"name": name, "count": count, "percent": round((count / max(total_consultations, 1)) * 100, 1)}
        for name, count in diag_counter.most_common(8)
    ]

    if is_filtered and consultations:
        patient_ids = {c.patient_id for c in consultations if c.patient_id}
        patients = db.query(Patient).filter(Patient.id.in_(patient_ids)).all() if patient_ids else []
    else:
        patients = db.query(Patient).all()

    gender_counts = {"male": 0, "female": 0, "other": 0}
    age_groups = {"pediatric": 0, "young_adult": 0, "middle_adult": 0, "senior": 0, "unknown": 0}
    for p in patients:
        g = (p.gender or "").lower()
        if g in ["m", "male", "masculino"]: gender_counts["male"] += 1
        elif g in ["f", "female", "femenino"]: gender_counts["female"] += 1
        else: gender_counts["other"] += 1
        age = calculate_age(p.date_of_birth)
        if age is None: age_groups["unknown"] += 1
        elif age < 18: age_groups["pediatric"] += 1
        elif age <= 35: age_groups["young_adult"] += 1
        elif age <= 60: age_groups["middle_adult"] += 1
        else: age_groups["senior"] += 1

    period_str = ""
    if s_str and e_str:
        period_str = f"Desde {s_str} hasta {e_str}"
    elif s_str:
        period_str = f"A partir de {s_str}"
    elif e_str:
        period_str = f"Hasta {e_str}"

    pdf_buffer = generate_executive_report_pdf(
        setting=setting,
        total_patients=total_patients,
        total_consultations=total_consultations,
        total_payments=total_payments,
        total_vitals=total_vitals,
        total_collected=total_collected,
        total_pending=total_pending,
        top_diagnoses=top_diagnoses,
        gender_counts=gender_counts,
        age_groups=age_groups,
        period_str=period_str,
    )

    filename = f"reporte_clinico_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/export/secretary-daily-pdf")
def export_secretary_daily_pdf(
    report_date: str = Query(None),
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Exporta el Reporte de Entrada y Recepción Diaria de la Secretaría a PDF con membrete y logo del doctor.
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
    date_str = target_date.strftime("%d/%m/%Y")

    setting = get_or_create_settings(db)
    currency = getattr(setting, "currency", "RD$") if setting else "RD$"

    # 1. Citas del día
    appointments = db.query(Appointment).filter(
        Appointment.date == target_date
    ).order_by(Appointment.start_time.asc()).all()

    # 2. Pacientes registrados en la fecha
    new_patients = db.query(Patient).filter(
        Patient.created_at >= start_dt,
        Patient.created_at <= end_dt
    ).all()

    # 3. Signos vitales tomados en la fecha
    vitals_records = db.query(VitalSign).filter(
        VitalSign.recorded_at >= start_dt,
        VitalSign.recorded_at <= end_dt
    ).all()
    vitals_by_patient = {}
    for v in vitals_records:
        if v.patient_id not in vitals_by_patient:
            vitals_by_patient[v.patient_id] = v

    # 4. Pagos registrados en la fecha
    payments_records = db.query(Payment).filter(
        Payment.created_at >= start_dt,
        Payment.created_at <= end_dt
    ).all()

    total_collected = sum(p.total for p in payments_records if p.status == "paid")
    total_pending = sum(p.total for p in payments_records if p.status == "pending")

    pm_breakdown = {}
    payments_by_patient = {}
    for p in payments_records:
        if p.patient_id not in payments_by_patient:
            payments_by_patient[p.patient_id] = []
        payments_by_patient[p.patient_id].append(p)

        if p.status == "paid":
            meth = p.payment_method or "Efectivo"
            pm_breakdown[meth] = pm_breakdown.get(meth, 0.0) + p.total

    # 5. Construir registros del día cronológicamente
    entries = []
    processed_patient_ids = set()

    for appt in appointments:
        p = appt.patient
        p_id = appt.patient_id
        processed_patient_ids.add(p_id)

        v = vitals_by_patient.get(p_id)
        vitals_txt = "Sin registro"
        if v:
            parts = []
            if v.systolic_bp and v.diastolic_bp:
                parts.append(f"PA: {v.systolic_bp}/{v.diastolic_bp}")
            if v.heart_rate:
                parts.append(f"FC: {v.heart_rate} bpm")
            if v.temperature_c:
                parts.append(f"T: {v.temperature_c}°C")
            if v.weight_kg:
                parts.append(f"P: {v.weight_kg}kg")
            vitals_txt = " • ".join(parts) if parts else "Registrado"

        p_pays = payments_by_patient.get(p_id, [])
        pay_txt = "Sin cobro"
        if p_pays:
            pay_items = []
            for pay in p_pays:
                rec = pay.receipt_number or f"REC-{pay.id:04d}"
                st = "PAGADO" if pay.status == "paid" else "PENDIENTE"
                pay_items.append(f"{rec}: {currency} {pay.total:,.2f} ({pay.payment_method or 'Efectivo'} - {st})")
            pay_txt = "<br/>".join(pay_items)

        entry_type = "Cita Programada"
        r_lower = (appt.reason or "").lower()
        if "walk-in" in r_lower or "espontánea" in r_lower or "sin cita" in r_lower:
            entry_type = "Llegada Espontánea"
        elif "control" in r_lower or "recurrente" in r_lower:
            entry_type = "Control / Recurrente"

        time_str = appt.start_time.strftime("%H:%M") if appt.start_time else "-"

        entries.append({
            "time": time_str,
            "patient_name": f"{p.first_name} {p.last_name}" if p else "Paciente no registrado",
            "document_id": p.document_id if p else "",
            "phone": p.phone if p else "",
            "entry_type": entry_type,
            "reason": appt.reason or "",
            "status": appt.status or "Programada",
            "vitals": vitals_txt,
            "payment": pay_txt,
        })

    # Pacientes con cobros registrados en la fecha sin cita
    for p_id, p_pays in payments_by_patient.items():
        if p_id not in processed_patient_ids:
            processed_patient_ids.add(p_id)
            patient_obj = p_pays[0].patient if p_pays[0].patient else db.query(Patient).filter(Patient.id == p_id).first()
            time_str = p_pays[0].created_at.strftime("%H:%M") if p_pays[0].created_at else "-"
            
            pay_items = []
            for pay in p_pays:
                rec = pay.receipt_number or f"REC-{pay.id:04d}"
                st = "PAGADO" if pay.status == "paid" else "PENDIENTE"
                pay_items.append(f"{rec}: {currency} {pay.total:,.2f} ({pay.payment_method or 'Efectivo'} - {st})")
            pay_txt = "<br/>".join(pay_items)

            v = vitals_by_patient.get(p_id)
            vitals_txt = "Sin registro"
            if v:
                parts = []
                if v.systolic_bp and v.diastolic_bp: parts.append(f"PA: {v.systolic_bp}/{v.diastolic_bp}")
                if v.heart_rate: parts.append(f"FC: {v.heart_rate} bpm")
                if v.temperature_c: parts.append(f"T: {v.temperature_c}°C")
                vitals_txt = " • ".join(parts) if parts else "Registrado"

            entries.append({
                "time": time_str,
                "patient_name": f"{patient_obj.first_name} {patient_obj.last_name}" if patient_obj else "Paciente",
                "document_id": patient_obj.document_id if patient_obj else "",
                "phone": patient_obj.phone if patient_obj else "",
                "entry_type": "Cobro en Caja",
                "reason": p_pays[0].service_name or "Servicio / Factura",
                "status": "Cobrado",
                "vitals": vitals_txt,
                "payment": pay_txt,
            })

    # Pacientes nuevos registrados en la fecha sin cita ni cobro
    for p in new_patients:
        if p.id not in processed_patient_ids:
            processed_patient_ids.add(p.id)
            time_str = p.created_at.strftime("%H:%M") if p.created_at else "-"
            v = vitals_by_patient.get(p.id)
            vitals_txt = "Sin registro"
            if v:
                parts = []
                if v.systolic_bp and v.diastolic_bp: parts.append(f"PA: {v.systolic_bp}/{v.diastolic_bp}")
                if v.heart_rate: parts.append(f"FC: {v.heart_rate} bpm")
                if v.temperature_c: parts.append(f"T: {v.temperature_c}°C")
                vitals_txt = " • ".join(parts) if parts else "Registrado"

            entries.append({
                "time": time_str,
                "patient_name": f"{p.first_name} {p.last_name}",
                "document_id": p.document_id or "",
                "phone": p.phone or "",
                "entry_type": "Nuevo Ingreso",
                "reason": "Apertura de Expediente",
                "status": "Registrado",
                "vitals": vitals_txt,
                "payment": "Sin cobro",
            })

    waiting_count = sum(1 for a in appointments if a.status == "En Espera")
    attended_count = sum(1 for a in appointments if a.status == "Atendida")

    kpis = {
        "total_patients_admitted": len(processed_patient_ids),
        "total_appointments": len(appointments),
        "waiting_count": waiting_count,
        "attended_count": attended_count,
        "total_vitals": len(vitals_records),
        "total_collected": total_collected,
        "total_pending": total_pending,
        "currency": currency,
    }

    pdf_buffer = generate_secretary_daily_report_pdf(
        setting=setting,
        report_date_str=date_str,
        user_name=current_user.name or current_user.email,
        kpis=kpis,
        payment_methods_breakdown=pm_breakdown,
        entries=entries,
    )

    filename = f"reporte_recepcion_{target_date.strftime('%Y%m%d')}.pdf"
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"{disposition}; filename={filename}"}
    )


@router.get("/export/patients")
def export_patients_csv(
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('reports'))
):
    """
    Exportación de base de datos de pacientes a CSV compatible con Excel.
    """
    start_dt, end_dt, _, _ = parse_date_range(start_date, end_date)
    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")
    
    # Encabezados
    writer.writerow([
        "ID", "Nombre", "Apellidos", "Cédula / Documento", "Teléfono", "Email",
        "Fecha de Nacimiento", "Género", "Tipo de Sangre", "Alergias Conocidas",
        "ARS / Seguro", "No. Póliza", "Contacto de Emergencia", "Tel. Emergencia", "Fecha Registro"
    ])

    q = db.query(Patient)
    if start_dt:
        q = q.filter(Patient.created_at >= start_dt)
    if end_dt:
        q = q.filter(Patient.created_at <= end_dt)

    for p in q.order_by(Patient.id).all():
        writer.writerow([
            p.id,
            p.first_name,
            p.last_name,
            p.document_id or "",
            p.phone or "",
            p.email or "",
            p.date_of_birth.strftime("%Y-%m-%d") if p.date_of_birth else "",
            p.gender or "",
            p.blood_type or "",
            p.allergies or "Ninguna",
            getattr(p, "insurance_name", "") or "Privado",
            getattr(p, "insurance_number", "") or "",
            p.emergency_contact_name or "",
            p.emergency_contact_phone or "",
            p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else ""
        ])

    csv_data = "\ufeff" + output.getvalue()
    filename = f"pacientes_sscp_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=csv_data.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/export/consultations")
def export_consultations_csv(
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('reports'))
):
    """
    Exportación de consultas e historias clínicas a CSV compatible con Excel.
    """
    start_dt, end_dt, _, _ = parse_date_range(start_date, end_date)
    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")
    
    writer.writerow([
        "ID", "Fecha / Hora", "Paciente", "Cédula", "Motivo de Consulta",
        "Diagnóstico", "Tratamiento / Prescripción", "Primera Vez", "Sede de Origen"
    ])

    q = db.query(Consultation)
    if start_dt:
        q = q.filter(Consultation.created_at >= start_dt)
    if end_dt:
        q = q.filter(Consultation.created_at <= end_dt)

    for c in q.order_by(Consultation.created_at.desc()).all():
        p_name = f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "N/D"
        doc_id = c.patient.document_id if c.patient else "N/D"
        writer.writerow([
            c.id,
            c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
            p_name,
            doc_id,
            c.reason or "",
            c.diagnosis or "",
            (c.prescription or c.treatment or "").replace("\n", " | "),
            "SÍ" if getattr(c, "is_first_visit", False) else "NO",
            c.sede_origen or "local"
        ])

    csv_data = "\ufeff" + output.getvalue()
    filename = f"consultas_sscp_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=csv_data.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/export/financial")
def export_financial_csv(
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('reports'))
):
    """
    Exportación de ingresos y estado de facturación a CSV compatible con Excel.
    """
    start_dt, end_dt, _, _ = parse_date_range(start_date, end_date)
    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")
    
    writer.writerow([
        "ID", "No. Recibo", "Fecha", "Paciente", "Concepto / Servicio",
        "Monto (DOP)", "Descuento", "Total (DOP)", "Estado", "Método de Pago"
    ])

    q = db.query(Payment)
    if start_dt:
        q = q.filter(Payment.created_at >= start_dt)
    if end_dt:
        q = q.filter(Payment.created_at <= end_dt)

    for pay in q.order_by(Payment.created_at.desc()).all():
        p_name = f"{pay.patient.first_name} {pay.patient.last_name}" if pay.patient else "N/D"
        writer.writerow([
            pay.id,
            pay.receipt_number or f"REC-{pay.id:04d}",
            pay.created_at.strftime("%Y-%m-%d %H:%M") if pay.created_at else "",
            p_name,
            pay.service_name or "Consulta Médica",
            pay.amount,
            pay.discount,
            pay.total,
            "PAGADO" if pay.status == "paid" else "PENDIENTE",
            pay.payment_method or "Efectivo"
        ])

    csv_data = "\ufeff" + output.getvalue()
    filename = f"reporte_financiero_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=csv_data.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# -----------------------------------------------------------------------------
# INFORME MENSUAL DE ACTIVIDAD MÉDICA & ANÁLISIS SEMANAL (DÍA FUERTE / FLOJO)
# -----------------------------------------------------------------------------
MONTH_NAMES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

PALETTE = [
    "#3b82f6", # Blue
    "#10b981", # Emerald
    "#8b5cf6", # Violet
    "#f59e0b", # Amber
    "#ec4899", # Pink
    "#06b6d4", # Cyan
    "#6366f1", # Indigo
    "#14b8a6", # Teal
    "#f97316", # Orange
    "#64748b", # Slate
]

@router.get("/monthly")
def reports_monthly(
    request: Request,
    month: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('reports'))
):
    """
    Informe Mensual de Actividad Médica & Análisis Semanal:
    - Tipos de citas y consultas con cantidad y porcentaje (%).
    - Gráfica interactiva de distribución por tipo de cita.
    - Análisis semanal: qué día fue más fuerte y cuál fue más flojo.
    - Gráfica de afluencia por día de la semana.
    """
    # 1. Determinar meses disponibles en la base de datos
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

    # 2. Mes seleccionado
    selected_month_str = (month or "").strip()
    if not selected_month_str or not re.match(r"^\d{4}-\d{2}$", selected_month_str):
        # Si no se pasó mes, elegir el mes actual o el último con actividad si el actual está vacío
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

    # Calcular mes previo y siguiente para flechas de navegación
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

    # 3. Citas del mes
    appts = db.query(Appointment).filter(
        ((Appointment.date >= start_d) & (Appointment.date <= end_d)) |
        ((Appointment.date == None) & (Appointment.created_at >= start_dt) & (Appointment.created_at <= end_dt))
    ).all()
    total_appointments = len(appts)

    # 4. Consultas del mes
    conss = db.query(Consultation).filter(
        Consultation.created_at >= start_dt,
        Consultation.created_at <= end_dt
    ).all()
    total_consultations = len(conss)

    # 5. Pacientes únicos atendidos
    p_ids = {a.patient_id for a in appts if a.patient_id} | {c.patient_id for c in conss if c.patient_id}
    unique_patients_count = len(p_ids)

    # 6. Recaudación del mes
    payments = db.query(Payment).filter(
        Payment.created_at >= start_dt,
        Payment.created_at <= end_dt
    ).all()
    total_revenue = sum(p.total for p in payments if p.status == 'paid')

    # 7. Desglose de TIPOS DE CITAS CON %
    type_counter = Counter()
    for a in appts:
        t = (a.reason or (a.service.name if a.service else "Consulta General")).strip()
        type_counter[t] += 1

    # También consultas registradas directamente
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

    # Datos serializados para Chart.js de Tipos de Citas
    types_chart_labels = [item["name"] for item in types_breakdown]
    types_chart_data = [item["count"] for item in types_breakdown]
    types_chart_colors = [item["color"] for item in types_breakdown]

    # 8. ANÁLISIS DE LA SEMANA (Día más fuerte y Día más flojo)
    day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
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
            "count": max_c,
            "percentage": round((max_c / total_week_events) * 100, 1)
        }

        min_c = min(weekday_counts)
        min_idx = weekday_counts.index(min_c)
        weakest_day = {
            "name": day_names[min_idx],
            "count": min_c,
            "percentage": round((min_c / total_week_events) * 100, 1)
        }

    # Desglose de cada día de la semana para la vista
    weekly_breakdown = []
    for i in range(7):
        c_count = weekday_counts[i]
        weekly_breakdown.append({
            "name": day_names[i],
            "count": c_count,
            "percentage": round((c_count / max(total_week_events, 1)) * 100, 1),
            "is_strongest": bool(strongest_day and day_names[i] == strongest_day["name"] and c_count > 0),
            "is_weakest": bool(weakest_day and day_names[i] == weakest_day["name"])
        })

    return templates.TemplateResponse(
        request=request,
        name="reports/monthly.html",
        context={
            "user": current_user,
            "selected_month": selected_month_str,
            "month_name_es": month_name_es,
            "prev_month": prev_month_str,
            "next_month": next_month_str,
            "available_months": available_months,
            "total_appointments": total_appointments,
            "total_consultations": total_consultations,
            "total_activity": total_activity,
            "unique_patients_count": unique_patients_count,
            "total_revenue": total_revenue,
            "types_breakdown": types_breakdown,
            "strongest_day": strongest_day,
            "weakest_day": weakest_day,
            "weekly_breakdown": weekly_breakdown,
            "types_chart_labels": json.dumps(types_chart_labels),
            "types_chart_data": json.dumps(types_chart_data),
            "types_chart_colors": json.dumps(types_chart_colors),
            "weekly_chart_labels": json.dumps(day_names),
            "weekly_chart_data": json.dumps(weekday_counts),
            "active_menu": "reports",
            "active_tab": "monthly"
        }
    )
