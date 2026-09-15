import re
from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pathlib import Path

from app.database import get_db
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.template import ClinicalTemplate
from app.models.setting import Setting
from app.core.deps import require_current_user, require_permission
from app.services.pdf_service import generate_quick_prescription_pdf

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

def check_allergy_conflict(patient_allergies: str, prescription_text: str) -> list:
    """
    Compara las alergias conocidas del paciente contra el texto de la prescripción.
    Retorna lista de sustancias en conflicto detectadas.
    """
    if not patient_allergies or not prescription_text:
        return []
        
    conflicts = []
    # Separar alergias por comas, barras o saltos de línea
    allergy_items = [a.strip().lower() for a in re.split(r'[,;/\n]', patient_allergies) if a.strip()]
    rx_lower = prescription_text.lower()
    
    for item in allergy_items:
        if len(item) >= 3 and item in rx_lower:
            conflicts.append(item.capitalize())
            
    return conflicts

@router.get("/quick")
def quick_prescription_view(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('prescriptions'))
):
    patients = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).order_by(Patient.first_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None
    rx_templates = db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "prescription").all()
    
    return templates.TemplateResponse(
        request=request,
        name="prescriptions/quick.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "templates": rx_templates,
        }
    )

@router.post("/check-allergy")
def check_allergy_api(
    patient_id: int = Form(...),
    prescription_text: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return JSONResponse({"conflict": False, "allergies": []})
        
    conflicts = check_allergy_conflict(patient.allergies, prescription_text)
    return JSONResponse({
        "conflict": len(conflicts) > 0,
        "conflicts": conflicts,
        "patient_allergies": patient.allergies or "Ninguna",
        "warning": f"¡ALERTA DE SEGURIDAD (F6)! El paciente tiene registrada alergia a: {', '.join(conflicts)}." if conflicts else ""
    })

@router.post("/quick")
def submit_quick_prescription(
    patient_id: int = Form(...),
    prescription: str = Form(...),
    diagnosis: str = Form("Emisión de Receta Directa"),
    force_override: bool = Form(False),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('prescriptions'))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
        
    # Cruce de alergias si no está forzada la anulación por el médico
    conflicts = check_allergy_conflict(patient.allergies, prescription)
    if conflicts and not force_override:
        raise HTTPException(
            status_code=400,
            detail=f"Bloqueo de Seguridad por Alergias (F6): El paciente es alérgico a {', '.join(conflicts)}. Active 'Confirmar prescripción bajo criterio médico' para continuar."
        )

    # Registrar como consulta ligera para mantener trazabilidad histórica
    consultation = Consultation(
        patient_id=patient.id,
        doctor_id=current_user.id,
        reason="Receta Rápida (Sin Consulta General)",
        diagnosis=diagnosis,
        prescription=prescription,
        notes=f"Receta Rápida emitida directamente. Alergias paciente: {patient.allergies or 'Ninguna'}.",
        sede_origen="local"
    )
    db.add(consultation)
    db.commit()
    db.refresh(consultation)

    # Generar PDF directo
    setting = db.query(Setting).first()
    pdf_buffer = generate_quick_prescription_pdf(
        patient=patient,
        prescription_text=prescription,
        diagnosis=diagnosis,
        setting=setting,
        doctor_name=current_user.name
    )
    
    filename = f"Receta_Rapida_{patient.document_id or patient.id}_{consultation.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )
