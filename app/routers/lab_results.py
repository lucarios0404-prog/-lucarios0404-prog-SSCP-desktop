from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, date
import json

from app.database import get_db
from app.models.lab_result import LabResult
from app.models.lab_order import LabOrder
from app.models.patient import Patient
from app.models.setting import Setting
from app.models.consultation import Consultation
from app.core.deps import require_current_user
from app.services.pdf_service import generate_lab_order_pdf, generate_lab_order_talonario_pdf

router = APIRouter(prefix="/lab-results", tags=["lab_results"])
from app.core.templates import templates

COMMON_TESTS = [
    {"name": "Hemograma Completo", "category": "Hematología"},
    {"name": "Perfil Lipídico (Colesterol, Triglicéridos, HDL, LDL)", "category": "Bioquímica"},
    {"name": "Glucemia en Ayunas", "category": "Bioquímica"},
    {"name": "Hemoglobina Glicosilada (HbA1c)", "category": "Bioquímica"},
    {"name": "Examen General de Orina (EGO)", "category": "Uroanálisis"},
    {"name": "Perfil Tiroideo (TSH, T3, T4 Libre)", "category": "Endocrinología"},
    {"name": "Creatinina y Urea en Sangre", "category": "Función Renal"},
    {"name": "Coprológico y Coproparasitario", "category": "Parasitología"},
    {"name": "Electrocardiograma (EKG)", "category": "Cardiología"},
]

@router.get("/")
@router.get("/checklist")
def lab_checklist_main(
    request: Request,
    patient_id: int = Query(None),
    consultation_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """
    Vista principal del Módulo de Laboratorio:
    Presenta directamente el checklist interactivo con todos los análisis por paneles clínicos
    para mandar a hacer al paciente seleccionado, con soporte de impresión en formato Talonario Físico (21.7 × 13.6 cm).
    """
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.last_name, Patient.first_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    default_indication = ""
    if consultation_id:
        consult = db.query(Consultation).filter(Consultation.id == consultation_id).first()
        if consult:
            if not selected_patient:
                selected_patient = consult.patient
            default_indication = consult.diagnosis or consult.reason or ""

    return templates.TemplateResponse(
        request=request,
        name="labs/order_create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "consultation_id": consultation_id,
            "panels": LAB_PANELS,
            "default_indication": default_indication,
            "active_tab": "checklist",
        }
    )

@router.get("/results")
def list_lab_results_history(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Historial y registro analítico de resultados de laboratorio."""
    query = db.query(LabResult).order_by(LabResult.result_date.desc())
    if patient_id:
        query = query.filter(LabResult.patient_id == patient_id)
        
    results = query.all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="labs/index.html",
        context={
            "user": current_user,
            "results": results,
            "selected_patient": selected_patient,
            "active_tab": "results",
        }
    )

@router.get("/create")
def create_lab_result_form(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    patients = db.query(Patient).order_by(Patient.last_name).all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="labs/create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "common_tests": COMMON_TESTS,
            "today": date.today().strftime("%Y-%m-%d"),
        }
    )

@router.post("/create")
def create_lab_result(
    request: Request,
    patient_id: int = Form(...),
    test_name: str = Form(...),
    test_category: str = Form("General"),
    result_date_str: str = Form(..., alias="result_date"),
    summary_findings: str = Form(...),
    is_abnormal: bool = Form(False),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    res_date = datetime.strptime(result_date_str, "%Y-%m-%d").date()

    new_lab = LabResult(
        patient_id=patient_id,
        test_name=test_name,
        test_category=test_category,
        result_date=res_date,
        summary_findings=summary_findings,
        is_abnormal=is_abnormal,
        recorded_by_id=current_user.id,
    )
    db.add(new_lab)
    db.commit()
    return RedirectResponse(url=f"/lab-results?patient_id={patient_id}", status_code=303)


# --- CATÁLOGO OFICIAL DE PANELES CLÍNICOS DEL TALONARIO (Dr. Carlos M. Heredia) ---
LAB_PANELS = [
    {
        "category": "Hematología",
        "icon": "fa-tint",
        "tests": [
            "Hemograma Completo",
            "Tipificación Sanguínea",
            "Eritrosedimentación",
            "TPT",
            "PT",
            "Tiempo de Coagulación",
            "Retracción de Coágulo",
            "Reconteo de Plaquetas",
            "Investigación de Células Falciformes",
            "Electroforesis de Hb",
            "Fibrinógeno",
            "Dímero D",
        ]
    },
    {
        "category": "Uroanálisis",
        "icon": "fa-vial",
        "tests": [
            "Exámen de orina",
            "Albuminuria",
            "Prueba de embarazo de orina",
            "Cetonuria",
            "Glucosuria",
            "Calcio Urinario en 24h",
        ]
    },
    {
        "category": "Microbiología",
        "icon": "fa-bacterium",
        "tests": [
            "Coprológico",
            "Urocultivo",
            "Hemocultivo",
            "Coprocultivo",
            "Cultivo Secreción Vaginal",
            "Baciloscopía",
        ]
    },
    {
        "category": "Inmunología",
        "icon": "fa-shield-virus",
        "tests": [
            "Anticuerpo DNA",
            "Hepatitis A",
            "Hepatitis B",
            "Hepatitis C",
            "HIV",
            "Prueba de Tuberculina",
            "Varicela IgM - IgG",
            "Influenza A H1 N1 IgG - IgM",
            "Chikungunya IgG - IgM",
        ]
    },
    {
        "category": "Serología",
        "icon": "fa-syringe",
        "tests": [
            "V.D.R.L.",
            "Anticuerpos Febriles",
            "Toxoplasmosis IgG - IgM",
            "Dengue IgG - IgM",
            "FTA. ABS",
            "ANA",
            "PCR",
            "ASO",
            "Factor Reumatoide",
            "P.C.R.",
            "Monotest",
            "Test de Coombs Directo",
            "Test de Coombs Indirecto",
            "Test Clamidia IgG - IgM",
            "TORCH IgG - IgM",
            "Herpes tipo 1 IgG - IgM",
            "Herpes Tipo 2 IgG - IgM",
        ]
    },
    {
        "category": "Química Sanguínea",
        "icon": "fa-flask",
        "tests": [
            "Glicemia en ayuna",
            "Glicemia Post Pandrial",
            "Hemoglobina Glicosilada",
            "Curva 3h",
            "Curva 5h",
            "Curva Insulina",
            "Acido Urico",
            "Colesterol Total",
            "HDL",
            "LDL",
            "VLDL",
            "Trigliceridos",
            "SGOT",
            "SGPT",
            "Bilirrubina",
            "Fosfatasa Alcalina",
            "Bun",
            "Creatinina",
            "Proteinas totales",
            "Albumina",
            "Electrolitos",
            "Hierro",
            "Gases Arteriales",
            "Ferretina Serica",
            "Calcio Serico",
            "Vitamina B12",
            "Acido Folico",
            "Fosforo Sérico",
            "Vitamina D",
            "PCR COVID - 19",
            "IGG COVID - 19",
            "IGM COVID - 19",
        ]
    },
    {
        "category": "Pruebas Especiales",
        "icon": "fa-dna",
        "tests": [
            "T3",
            "T3 libre",
            "T4",
            "T4 libre",
            "TSH",
            "LH",
            "FSH",
            "Prolactina",
            "Estrógenos Totales",
            "Estradiol",
            "Estriol",
            "Progesterona",
            "Androstenediona",
            "Testosterona total",
            "Testosterona libre",
            "DHEA - S",
            "BHCG cualitativa",
            "BHCG cuantitativa",
            "Inhibina",
            "Alfa Feto Proteína (AFP)",
            "CA 19-9",
            "CA 125",
            "CA 15-3",
            "CEA",
            "HE4",
            "Osteocalcina",
            "Fosfatasa Alcalina Osea",
            "PTH intacto",
            "C-Telopeptido",
            "N-Telopeptido en Orina",
            "Hormona Antimulleriana",
            "PAPP-A",
        ]
    },
    {
        "category": "Sonografía",
        "icon": "fa-wave-square",
        "tests": [
            "Pélvica",
            "Transvaginal",
            "Sonomamografía",
            "Obstetricia",
            "Abdominal",
            "Genética",
            "Morfológica",
            "Perfil hemodinámico",
        ]
    }
]

@router.get("/orders")
def list_lab_orders(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Listado general de solicitudes / órdenes de laboratorio emitidas."""
    query = db.query(LabOrder).order_by(LabOrder.order_date.desc(), LabOrder.id.desc())
    if patient_id:
        query = query.filter(LabOrder.patient_id == patient_id)

    orders = query.all()
    selected_patient = db.query(Patient).filter(Patient.id == patient_id).first() if patient_id else None

    return templates.TemplateResponse(
        request=request,
        name="labs/orders_list.html",
        context={
            "user": current_user,
            "orders": orders,
            "selected_patient": selected_patient,
        }
    )

@router.get("/orders/new")
def new_lab_order_form(
    request: Request,
    patient_id: int = Query(None),
    consultation_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Redirige o procesa la emisión de órdenes al checklist principal."""
    return lab_checklist_main(
        request=request,
        patient_id=patient_id,
        consultation_id=consultation_id,
        db=db,
        current_user=current_user
    )

@router.post("/orders/new")
def create_lab_order(
    request: Request,
    patient_id: int = Form(...),
    consultation_id: int = Form(None),
    clinical_indication: str = Form(None),
    tests: list[str] = Form([]),
    other_tests: str = Form(None),
    notes: str = Form(None),
    print_format: str = Form("talonario"),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Guarda la orden de laboratorio en la base de datos y redirige a la vista."""
    all_tests = list(tests)
    if other_tests:
        custom_lines = [line.strip() for line in other_tests.splitlines() if line.strip()]
        all_tests.extend(custom_lines)

    tests_json = json.dumps(all_tests)

    new_order = LabOrder(
        patient_id=patient_id,
        consultation_id=consultation_id if consultation_id and consultation_id > 0 else None,
        doctor_id=current_user.id,
        clinical_indication=clinical_indication.strip() if clinical_indication else None,
        tests_requested=tests_json,
        notes=notes.strip() if notes else None,
        status="solicitado"
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    autoprint_param = "talonario" if print_format == "talonario" else ("pdf" if print_format == "letter" else "")
    query_str = f"?autoprint={autoprint_param}" if autoprint_param else ""
    return RedirectResponse(url=f"/lab-results/orders/{new_order.id}{query_str}", status_code=303)


@router.post("/talonario/quick")
def quick_talonario_lab_order(
    patient_id: int = Form(...),
    consultation_id: int = Form(None),
    clinical_indication: str = Form(None),
    tests: list[str] = Form([]),
    other_tests: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Guarda la orden e inmediatamente retorna el PDF del talonario preimpreso (21.7 × 13.6 cm)."""
    all_tests = list(tests)
    if other_tests:
        custom_lines = [line.strip() for line in other_tests.splitlines() if line.strip()]
        all_tests.extend(custom_lines)

    tests_json = json.dumps(all_tests)

    new_order = LabOrder(
        patient_id=patient_id,
        consultation_id=consultation_id if consultation_id and consultation_id > 0 else None,
        doctor_id=current_user.id,
        clinical_indication=clinical_indication.strip() if clinical_indication else None,
        tests_requested=tests_json,
        notes=notes.strip() if notes else None,
        status="solicitado"
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    setting = db.query(Setting).first()
    pdf_buffer = generate_lab_order_talonario_pdf(new_order, setting)

    p = new_order.patient
    doc_id = p.document_id if p and p.document_id else (str(p.id) if p else "")
    filename = f"Talonario_Laboratorio_{doc_id}_{new_order.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@router.get("/orders/{order_id}")
def view_lab_order(
    request: Request,
    order_id: int,
    autoprint: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Muestra el detalle de una orden de laboratorio emitida."""
    order = db.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Orden de laboratorio no encontrada")

    tests_list = []
    if order.tests_requested:
        try:
            tests_list = json.loads(order.tests_requested)
        except Exception:
            tests_list = [t.strip() for t in order.tests_requested.splitlines() if t.strip()]

    return templates.TemplateResponse(
        request=request,
        name="labs/order_view.html",
        context={
            "user": current_user,
            "order": order,
            "tests_list": tests_list,
            "autoprint": autoprint,
            "active_tab": "orders",
        }
    )


@router.get("/orders/{order_id}/talonario/pdf")
def download_lab_order_talonario_pdf(
    order_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Genera y descarga la orden de laboratorio en formato Talonario Físico (21.7 × 13.6 cm)."""
    order = db.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Orden de laboratorio no encontrada")

    setting = db.query(Setting).first()
    pdf_buffer = generate_lab_order_talonario_pdf(order, setting)

    p = order.patient
    doc_id = p.document_id if p and p.document_id else (str(p.id) if p else "")
    filename = f"Talonario_Laboratorio_{doc_id}_{order.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@router.get("/orders/{order_id}/pdf")
def download_lab_order_pdf(
    order_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    """Genera y descarga el volante oficial de orden de laboratorio en PDF con membrete digital (Carta/A4)."""
    order = db.query(LabOrder).filter(LabOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Orden de laboratorio no encontrada")

    setting = db.query(Setting).first()
    pdf_buffer = generate_lab_order_pdf(order, setting)

    filename = f"Orden_Laboratorio_{order.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )
