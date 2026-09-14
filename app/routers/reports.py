import csv
import io
from datetime import datetime, date
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.payment import Payment
from app.models.vital_sign import VitalSign
from app.models.template import ClinicalTemplate
from app.core.deps import require_current_user

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
        }
    )

@router.get("/export/patients")
def export_patients_csv(
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
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
    current_user = Depends(require_current_user)
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
    current_user = Depends(require_current_user)
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
