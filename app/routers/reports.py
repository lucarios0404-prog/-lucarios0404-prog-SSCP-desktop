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
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

def calculate_age(dob: date) -> int:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

@router.get("/")
def reports_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Panel de Inteligencia Clínica y Estadísticas Médicas (F14).
    """
    total_patients = db.query(Patient).count()
    total_consultations = db.query(Consultation).count()
    total_payments = db.query(Payment).count()
    total_vitals = db.query(VitalSign).count()

    # 1. Top Diagnósticos Médicos (Morbilidad)
    consultations = db.query(Consultation).all()
    diag_counter = Counter()
    for c in consultations:
        if c.diagnosis and c.diagnosis.strip():
            # Extraer diagnósticos limpios
            lines = [d.strip() for d in c.diagnosis.split("\n") if d.strip()]
            for line in lines:
                diag_counter[line[:60]] += 1

    top_diagnoses = [
        {"name": name, "count": count, "percent": round((count / max(total_consultations, 1)) * 100, 1)}
        for name, count in diag_counter.most_common(6)
    ]

    # 2. Distribución de Pacientes por Género
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

    # 3. Finanzas y Pagos
    payments = db.query(Payment).all()
    total_collected = sum(p.total for p in payments if p.status == "paid")
    total_pending = sum(p.total for p in payments if p.status == "pending")

    return templates.TemplateResponse(
        request=request,
        name="reports/index.html",
        context={
            "user": current_user,
            "total_patients": total_patients,
            "total_consultations": total_consultations,
            "total_payments": total_payments,
            "total_vitals": total_vitals,
            "top_diagnoses": top_diagnoses,
            "gender_counts": gender_counts,
            "age_groups": age_groups,
            "total_collected": total_collected,
            "total_pending": total_pending,
            "today_str": date.today().strftime("%Y-%m-%d"),
        }
    )

@router.get("/export/pdf")
def export_executive_pdf(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Exportación del Reporte Ejecutivo Clínico completo a PDF con membrete y logo del doctor.
    """
    setting = get_or_create_settings(db)
    total_patients = db.query(Patient).count()
    total_consultations = db.query(Consultation).count()
    total_payments = db.query(Payment).count()
    total_vitals = db.query(VitalSign).count()

    consultations = db.query(Consultation).all()
    diag_counter = Counter()
    for c in consultations:
        if c.diagnosis and c.diagnosis.strip():
            for line in [d.strip() for d in c.diagnosis.split("\n") if d.strip()]:
                diag_counter[line[:60]] += 1
    top_diagnoses = [
        {"name": name, "count": count, "percent": round((count / max(total_consultations, 1)) * 100, 1)}
        for name, count in diag_counter.most_common(8)
    ]

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

    payments = db.query(Payment).all()
    total_collected = sum(p.total for p in payments if p.status == "paid")
    total_pending = sum(p.total for p in payments if p.status == "pending")

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
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/patients")
def export_patients_csv(
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('reports'))
):
    """
    Exportación de base de datos de pacientes a CSV compatible con Excel.
    """
    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")
    
    # Encabezados
    writer.writerow([
        "ID", "Nombre", "Apellidos", "Cédula / Documento", "Teléfono", "Email",
        "Fecha de Nacimiento", "Género", "Tipo de Sangre", "Alergias Conocidas",
        "Contacto de Emergencia", "Tel. Emergencia", "Fecha Registro"
    ])

    for p in db.query(Patient).order_by(Patient.id).all():
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
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('reports'))
):
    """
    Exportación de consultas e historias clínicas a CSV compatible con Excel.
    """
    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")
    
    writer.writerow([
        "ID", "Fecha / Hora", "Paciente", "Cédula", "Motivo de Consulta",
        "Diagnóstico", "Tratamiento / Prescripción", "Sede de Origen"
    ])

    for c in db.query(Consultation).order_by(Consultation.created_at.desc()).all():
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
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('reports'))
):
    """
    Exportación de ingresos y estado de facturación a CSV compatible con Excel.
    """
    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")
    
    writer.writerow([
        "ID", "No. Recibo", "Fecha", "Paciente", "Concepto / Servicio",
        "Monto (DOP)", "Descuento", "Total (DOP)", "Estado", "Método de Pago"
    ])

    for pay in db.query(Payment).order_by(Payment.created_at.desc()).all():
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
