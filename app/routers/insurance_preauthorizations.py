from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from datetime import datetime, date
import json

from app.database import get_db
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.user import User
from app.models.setting import Setting
from app.models.insurance_preauthorization import InsurancePreauthorization
from app.core.deps import require_current_user, get_current_user
from app.core.templates import templates
from app.services.pdf_service import generate_insurance_preauthorization_pdf

router = APIRouter(prefix="/insurance-forms", tags=["insurance_forms"])

ARS_OPTIONS = [
    "SeNaSa (Régimen Contributivo)",
    "SeNaSa (Régimen Subsidiado)",
    "Primera ARS de Humano",
    "ARS Universal",
    "Mapfre Salud ARS",
    "ARS Monumental",
    "ARS Renacer",
    "ARS Simag",
    "ARS Futuro",
    "ARS Yunen",
    "ARS Reservas (Banreservas)",
    "ARS GMA (Grupo Médico Asociado)",
    "ARS Plan Salud",
    "ARS SEMMA (Maestros)",
    "ARS CMD (Colegio Médico)",
    "ARS Fuerzas Armadas y Policía",
    "ARS ASEMAP",
    "ARS Meta Salud",
    "Privado / Particular / Seguro Internacional",
]

@router.get("/")
def list_insurance_forms(
    request: Request,
    patient_id: int = Query(None),
    q: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Listado histórico de historias clínicas y solicitudes de pre-autorización para ARS."""
    query = db.query(InsurancePreauthorization).order_by(InsurancePreauthorization.created_at.desc())

    if patient_id:
        query = query.filter(InsurancePreauthorization.patient_id == patient_id)

    if q and q.strip():
        search = f"%{q.strip()}%"
        query = query.join(Patient).filter(
            or_(
                Patient.first_name.ilike(search),
                Patient.last_name.ilike(search),
                Patient.document_id.ilike(search),
                InsurancePreauthorization.ars_name.ilike(search),
                InsurancePreauthorization.definitive_diagnosis.ilike(search)
            )
        )

    forms = query.all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="insurance_forms/index.html",
        context={
            "user": current_user,
            "forms": forms,
            "selected_patient": selected_patient,
            "q": q or "",
            "active_menu": "insurance_forms",
        }
    )

@router.get("/new")
def new_insurance_form(
    request: Request,
    patient_id: int = Query(None),
    consultation_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Formulario para emitir una nueva Historia Clínica y Solicitud de Pre-Autorización."""
    patients = db.query(Patient).filter(or_(Patient.is_active == True, Patient.is_active == None)).order_by(Patient.first_name).all()
    setting = db.query(Setting).first()

    selected_patient = None
    consultation = None

    if consultation_id:
        consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
        if consultation:
            selected_patient = consultation.patient

    if not selected_patient and patient_id:
        selected_patient = db.query(Patient).filter(Patient.id == patient_id).first()

    default_center = getattr(setting, "clinic_name", "Centro Médico") if setting else "Centro Médico"
    doctor_code = getattr(current_user, "exequatur", "") or (getattr(setting, "exequatur", "") if setting else "")

    return templates.TemplateResponse(
        request=request,
        name="insurance_forms/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "consultation": consultation,
            "setting": setting,
            "ars_options": ARS_OPTIONS,
            "default_center": default_center,
            "doctor_code": doctor_code,
            "today_str": date.today().isoformat(),
            "active_menu": "insurance_forms",
        }
    )

@router.post("/new")
def submit_insurance_form(
    patient_id: int = Form(...),
    consultation_id: int = Form(None),
    ars_name: str = Form(...),
    request_type: str = Form("Cirugía Electiva / Procedimiento"),
    request_date: str = Form(None),
    health_center: str = Form(None),
    is_traffic_accident: bool = Form(False),
    affiliate_nss: str = Form(None),
    affiliate_card_number: str = Form(None),
    contract_number: str = Form(None),
    plan_type: str = Form(None),
    symptoms_onset_date: str = Form(None),
    current_illness_history: str = Form(None),
    personal_family_history: str = Form(None),
    diagnostic_tests: str = Form(None),
    presumptive_diagnosis: str = Form(None),
    definitive_diagnosis: str = Form(None),
    secondary_diagnoses: str = Form(None),
    procedures_codes: list[str] = Form([]),
    procedures_names: list[str] = Form([]),
    treatment_plan: str = Form(None),
    doctor_code: str = Form(None),
    custom_ars_name: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Guarda la Historia Clínica de Pre-Autorización y redirige a la vista de impresión en Hoja Carta."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    final_ars_name = custom_ars_name.strip() if custom_ars_name and custom_ars_name.strip() else ars_name

    # Procesar fecha de solicitud
    r_date = date.today()
    if request_date:
        try:
            r_date = datetime.strptime(request_date[:10], "%Y-%m-%d").date()
        except Exception:
            r_date = date.today()

    # Construir lista JSON de procedimientos con códigos SIMON
    procedures_list = []
    for c, n in zip(procedures_codes, procedures_names):
        if (c and c.strip()) or (n and n.strip()):
            procedures_list.append({
                "code": c.strip() if c else "",
                "procedure": n.strip() if n else ""
            })

    # Si se cargó carnet o NSS, actualizar los datos del paciente si estaban vacíos
    if affiliate_card_number and not patient.insurance_number:
        patient.insurance_number = affiliate_card_number.strip()

    new_form = InsurancePreauthorization(
        patient_id=patient.id,
        doctor_id=current_user.id,
        consultation_id=consultation_id if consultation_id and consultation_id > 0 else None,
        ars_name=final_ars_name.strip(),
        request_type=request_type.strip() if request_type else "Cirugía Electiva",
        request_date=r_date,
        health_center=health_center.strip() if health_center else None,
        is_traffic_accident=is_traffic_accident,
        affiliate_nss=affiliate_nss.strip() if affiliate_nss else None,
        affiliate_card_number=affiliate_card_number.strip() if affiliate_card_number else None,
        contract_number=contract_number.strip() if contract_number else None,
        plan_type=plan_type.strip() if plan_type else None,
        symptoms_onset_date=symptoms_onset_date.strip() if symptoms_onset_date else None,
        current_illness_history=current_illness_history.strip() if current_illness_history else None,
        personal_family_history=personal_family_history.strip() if personal_family_history else None,
        diagnostic_tests=diagnostic_tests.strip() if diagnostic_tests else None,
        presumptive_diagnosis=presumptive_diagnosis.strip() if presumptive_diagnosis else None,
        definitive_diagnosis=definitive_diagnosis.strip() if definitive_diagnosis else None,
        secondary_diagnoses=secondary_diagnoses.strip() if secondary_diagnoses else None,
        procedures_json=json.dumps(procedures_list) if procedures_list else None,
        treatment_plan=treatment_plan.strip() if treatment_plan else None,
        doctor_code=doctor_code.strip() if doctor_code else None,
        notes=notes.strip() if notes else None,
        sede_origen="local"
    )

    db.add(new_form)
    db.commit()
    db.refresh(new_form)

    return RedirectResponse(url=f"/insurance-forms/{new_form.id}?autoprint=1", status_code=303)

@router.get("/{form_id}")
def view_insurance_form(
    form_id: int,
    request: Request,
    autoprint: int = Query(0),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Ver ficha de la solicitud emitida."""
    form_obj = db.query(InsurancePreauthorization).filter(InsurancePreauthorization.id == form_id).first()
    if not form_obj:
        raise HTTPException(status_code=404, detail="Solicitud de pre-autorización no encontrada")

    proc_list = []
    if form_obj.procedures_json:
        try:
            proc_list = json.loads(form_obj.procedures_json)
        except Exception:
            pass

    return templates.TemplateResponse(
        request=request,
        name="insurance_forms/view.html",
        context={
            "user": current_user,
            "form": form_obj,
            "procedures": proc_list,
            "autoprint": autoprint,
            "active_menu": "insurance_forms",
        }
    )

@router.get("/{form_id}/pdf")
def download_insurance_form_pdf(
    form_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Genera e imprime el PDF en Hoja Carta (Letter) para el Seguro."""
    form_obj = db.query(InsurancePreauthorization).filter(InsurancePreauthorization.id == form_id).first()
    if not form_obj:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    setting = db.query(Setting).first()
    pdf_buffer = generate_insurance_preauthorization_pdf(form_obj, setting)

    safe_ars = "".join(c for c in form_obj.ars_name[:10] if c.isascii() and (c.isalnum() or c in ('_', '-')))
    filename = f"Preautorizacion_{safe_ars}_{form_obj.id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )

@router.post("/{form_id}/delete")
def delete_insurance_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Elimina una solicitud de pre-autorización."""
    form_obj = db.query(InsurancePreauthorization).filter(InsurancePreauthorization.id == form_id).first()
    if not form_obj:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    db.delete(form_obj)
    db.commit()
    return RedirectResponse(url="/insurance-forms", status_code=303)
