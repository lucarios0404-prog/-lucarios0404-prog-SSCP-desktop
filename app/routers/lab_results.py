from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
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
from app.models.template import ClinicalTemplate
from app.core.deps import require_permission
from app.services.pdf_service import generate_lab_order_pdf, generate_lab_order_talonario_pdf

router = APIRouter(prefix="/lab-results", tags=["lab_results"])
from app.core.templates import templates

LAB_SEEDED_MARKER_CATEGORY = "lab_seeded_marker"

DEFAULT_LAB_PRESETS = [
    {
        "title": "🩺 Rutina General",
        "tests": [
            "Hemograma Completo",
            "Exámen de orina",
            "Glicemia en ayuna",
            "Creatinina",
            "Colesterol Total",
            "Trigliceridos",
        ],
    },
    {
        "title": "🤰 1er Trimestre",
        "tests": [
            "Hemograma Completo",
            "Tipificación Sanguínea",
            "Exámen de orina",
            "Bun",
            "Creatinina",
            "Acido Urico",
            "Glicemia en ayuna",
            "Hemoglobina Glicosilada",
            "Investigación de Células Falciformes (Falcemia)",
            "TORCH IgG - IgM",
            "Toxoplasmosis IgG - IgM",
            "SGOT",
            "SGPT",
            "Bilirrubina",
            "Fosfatasa Alcalina",
            "Proteinas totales",
            "Albumina",
            "Colesterol Total",
            "Trigliceridos",
            "HDL",
            "LDL",
            "V.D.R.L.",
            "HIV",
            "Hepatitis B",
            "Hepatitis C",
            "Progesterona",
            "T4 libre",
            "TSH",
            "Cultivo Secreción Vaginal",
        ],
    },
    {
        "title": "🤰 2do Trimestre",
        "tests": [
            "Hemograma Completo",
            "Glicemia en ayuna",
            "Exámen de orina",
            "T3",
            "T4",
            "T4 libre",
            "TSH",
            "Cultivo Secreción Vaginal",
            "V.D.R.L.",
            "PT",
            "TPT",
        ],
    },
    {
        "title": "🤰 Prenatal + Falcemia",
        "tests": [
            "Hemograma Completo",
            "Tipificación Sanguínea",
            "Exámen de orina",
            "V.D.R.L.",
            "HIV",
            "Glicemia en ayuna",
            "Toxoplasmosis IgG - IgM",
            "Investigación de Células Falciformes (Falcemia)",
        ],
    },
    {
        "title": "🍬 Control Diabético",
        "tests": [
            "Glicemia en ayuna",
            "Glicemia Post Pandrial",
            "Hemoglobina Glicosilada",
            "Exámen de orina",
            "Creatinina",
            "Albuminuria",
        ],
    },
    {
        "title": "🩸 Perfil Lipídico",
        "tests": [
            "Colesterol Total",
            "HDL",
            "LDL",
            "VLDL",
            "Trigliceridos",
        ],
    },
    {
        "title": "🦋 Perfil Tiroideo",
        "tests": [
            "TSH",
            "T3 libre",
            "T4 libre",
            "T3",
            "T4",
        ],
    },
    {
        "title": "🩹 Pre-Quirúrgico",
        "tests": [
            "Hemograma Completo",
            "PT",
            "TPT",
            "Tipificación Sanguínea",
            "Glicemia en ayuna",
            "Exámen de orina",
            "Creatinina",
        ],
    },
    {
        "title": "🧪 Hepático / Renal",
        "tests": [
            "SGOT",
            "SGPT",
            "Bilirrubina",
            "Fosfatasa Alcalina",
            "Proteinas totales",
            "Albumina",
            "Bun",
            "Creatinina",
            "Acido Urico",
        ],
    },
    {
        "title": "🦴 Reumatológico",
        "tests": [
            "P.C.R.",
            "PCR",
            "Eritrosedimentación",
            "Factor Reumatoide",
            "Acido Urico",
            "ASO",
        ],
    },
    {
        "title": "🦠 Infeccioso / Febril",
        "tests": [
            "Hemograma Completo",
            "Exámen de orina",
            "Coprológico",
            "Dengue IgG - IgM",
            "Tipificación Sanguínea",
        ],
    },
]


def parse_lab_template_tests(content: str) -> list[str]:
    """Convierte el contenido de una plantilla de laboratorio (JSON o líneas) en lista limpia de estudios."""
    if not content:
        return []
    raw = content.strip()
    items = []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                items = [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            items = []
    elif raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("tests"), list):
                items = [str(x).strip() for x in parsed["tests"] if str(x).strip()]
        except Exception:
            items = []
    if not items:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) == 1 and "," in lines[0] and not any(
            known in lines[0] for known in ("IgG", "IgM", "1,25")
        ):
            items = [part.strip() for part in lines[0].split(",") if part.strip()]
        else:
            items = lines

    deduped = []
    seen = set()
    for item in items:
        clean = item.lstrip("-•* ").strip()
        if not clean:
            continue
        key = clean.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(clean)
    return deduped


def serialize_lab_preset(tpl: ClinicalTemplate) -> dict:
    tests = parse_lab_template_tests(tpl.content)
    return {
        "id": tpl.id,
        "name": tpl.title,
        "title": tpl.title,
        "tests": tests,
        "content": "\n".join(tests),
        "is_factory": bool(tpl.is_global),
    }


def _ensure_lab_seed_marker(db: Session) -> None:
    marker = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.category == LAB_SEEDED_MARKER_CATEGORY)
        .first()
    )
    if not marker:
        db.add(
            ClinicalTemplate(
                doctor_id=None,
                category=LAB_SEEDED_MARKER_CATEGORY,
                title="__lab_presets_seeded_v1__",
                content="seeded",
                is_global=False,
            )
        )
        db.commit()


def ensure_default_lab_presets(db: Session, doctor_id: int | None = None) -> list[ClinicalTemplate]:
    """
    Siembra los perfiles de laboratorio por defecto en SQLite una sola vez.
    Si el médico edita o elimina cualquiera de ellos, sus cambios persisten en la BD
    y los eliminados no vuelven a recrearse salvo que solicite restaurarlos.
    """
    has_marker = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.category == LAB_SEEDED_MARKER_CATEGORY)
        .first()
        is not None
    )
    existing_labs = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.category == "lab")
        .order_by(ClinicalTemplate.id.asc())
        .all()
    )

    if not has_marker and not existing_labs:
        for preset in DEFAULT_LAB_PRESETS:
            db.add(
                ClinicalTemplate(
                    doctor_id=doctor_id,
                    category="lab",
                    title=preset["title"],
                    content="\n".join(preset["tests"]),
                    is_global=True,
                )
            )
        db.add(
            ClinicalTemplate(
                doctor_id=None,
                category=LAB_SEEDED_MARKER_CATEGORY,
                title="__lab_presets_seeded_v1__",
                content="seeded",
                is_global=False,
            )
        )
        db.commit()
        existing_labs = (
            db.query(ClinicalTemplate)
            .filter(ClinicalTemplate.category == "lab")
            .order_by(ClinicalTemplate.id.asc())
            .all()
        )
    elif not has_marker and existing_labs:
        _ensure_lab_seed_marker(db)

    return existing_labs

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
    current_user = Depends(require_permission('labs'))
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

    lab_presets = [
        serialize_lab_preset(t)
        for t in ensure_default_lab_presets(db, getattr(current_user, "id", None))
    ]

    return templates.TemplateResponse(
        request=request,
        name="labs/order_create.html",
        context={
            "user": current_user,
            "patients": patients,
            "selected_patient": selected_patient,
            "consultation_id": consultation_id,
            "panels": LAB_PANELS,
            "lab_presets": lab_presets,
            "default_indication": default_indication,
            "active_tab": "checklist",
        }
    )


async def _extract_preset_payload(request: Request) -> dict:
    """Extrae payload de plantilla de laboratorio tanto si viene en JSON como en Form."""
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            data = await request.json()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    form = await request.form()
    tests_val = form.getlist("tests") if hasattr(form, "getlist") else []
    if not tests_val and form.get("content"):
        tests_val = parse_lab_template_tests(str(form.get("content") or ""))
    return {
        "name": form.get("name") or form.get("title") or "",
        "title": form.get("title") or form.get("name") or "",
        "tests": tests_val,
        "content": form.get("content") or "",
        "other_tests": form.get("other_tests") or "",
        "is_factory": form.get("is_factory"),
        "skip_if_exists": form.get("skip_if_exists"),
    }


def _collect_clean_tests(payload: dict) -> list[str]:
    raw_tests = payload.get("tests")
    collected: list[str] = []
    if isinstance(raw_tests, list):
        for item in raw_tests:
            if isinstance(item, str):
                collected.extend(parse_lab_template_tests(item))
    elif isinstance(raw_tests, str) and raw_tests.strip():
        collected.extend(parse_lab_template_tests(raw_tests))

    if payload.get("content"):
        collected.extend(parse_lab_template_tests(str(payload["content"])))
    if payload.get("other_tests"):
        collected.extend(parse_lab_template_tests(str(payload["other_tests"])))

    return parse_lab_template_tests("\n".join(collected))


@router.get("/presets")
def list_lab_presets_api(
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
):
    """Devuelve todas las plantillas de laboratorio persistidas en SQLite."""
    items = ensure_default_lab_presets(db, getattr(current_user, "id", None))
    return JSONResponse({
        "ok": True,
        "presets": [serialize_lab_preset(t) for t in items],
    })


@router.post("/presets")
async def create_lab_preset_api(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
):
    """Crea y persiste una nueva plantilla de laboratorio en SQLite."""
    ensure_default_lab_presets(db, getattr(current_user, "id", None))
    payload = await _extract_preset_payload(request)
    title = str(payload.get("name") or payload.get("title") or "").strip()
    if not title:
        return JSONResponse(
            {"ok": False, "detail": "Debe ingresar un nombre para la plantilla de laboratorio."},
            status_code=400,
        )

    clean_tests = _collect_clean_tests(payload)
    if not clean_tests:
        return JSONResponse(
            {"ok": False, "detail": "Seleccione o escriba al menos un análisis para guardar la plantilla."},
            status_code=400,
        )

    if payload.get("skip_if_exists"):
        existing = (
            db.query(ClinicalTemplate)
            .filter(ClinicalTemplate.category == "lab", ClinicalTemplate.title == title)
            .first()
        )
        if existing:
            all_items = (
                db.query(ClinicalTemplate)
                .filter(ClinicalTemplate.category == "lab")
                .order_by(ClinicalTemplate.id.asc())
                .all()
            )
            return JSONResponse({
                "ok": True,
                "preset": serialize_lab_preset(existing),
                "presets": [serialize_lab_preset(t) for t in all_items],
            })

    new_tpl = ClinicalTemplate(
        doctor_id=getattr(current_user, "id", None),
        category="lab",
        title=title,
        content="\n".join(clean_tests),
        is_global=bool(payload.get("is_factory", False)),
    )
    db.add(new_tpl)
    db.commit()
    db.refresh(new_tpl)

    all_items = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.category == "lab")
        .order_by(ClinicalTemplate.id.asc())
        .all()
    )
    return JSONResponse({
        "ok": True,
        "preset": serialize_lab_preset(new_tpl),
        "presets": [serialize_lab_preset(t) for t in all_items],
    })


@router.api_route("/presets/{preset_id}/edit", methods=["POST", "PUT"])
@router.put("/presets/{preset_id}")
async def update_lab_preset_api(
    preset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
):
    """Edita el nombre y/o listado de análisis de una plantilla de laboratorio existente."""
    tpl = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.id == preset_id, ClinicalTemplate.category == "lab")
        .first()
    )
    if not tpl:
        return JSONResponse(
            {"ok": False, "detail": "Plantilla de laboratorio no encontrada."},
            status_code=404,
        )

    payload = await _extract_preset_payload(request)
    title = str(payload.get("name") or payload.get("title") or "").strip()
    if not title:
        return JSONResponse(
            {"ok": False, "detail": "El nombre de la plantilla no puede estar vacío."},
            status_code=400,
        )

    clean_tests = _collect_clean_tests(payload)
    if not clean_tests:
        return JSONResponse(
            {"ok": False, "detail": "La plantilla debe incluir al menos un análisis de laboratorio."},
            status_code=400,
        )

    tpl.title = title
    tpl.content = "\n".join(clean_tests)
    db.commit()
    db.refresh(tpl)

    all_items = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.category == "lab")
        .order_by(ClinicalTemplate.id.asc())
        .all()
    )
    return JSONResponse({
        "ok": True,
        "preset": serialize_lab_preset(tpl),
        "presets": [serialize_lab_preset(t) for t in all_items],
    })


@router.api_route("/presets/{preset_id}/delete", methods=["POST", "DELETE"])
@router.delete("/presets/{preset_id}")
def delete_lab_preset_api(
    preset_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
):
    """Elimina permanentemente una plantilla de laboratorio (personalizada o de fábrica no deseada)."""
    _ensure_lab_seed_marker(db)
    tpl = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.id == preset_id, ClinicalTemplate.category == "lab")
        .first()
    )
    if not tpl:
        return JSONResponse(
            {"ok": False, "detail": "Plantilla de laboratorio no encontrada."},
            status_code=404,
        )

    db.delete(tpl)
    db.commit()

    all_items = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.category == "lab")
        .order_by(ClinicalTemplate.id.asc())
        .all()
    )
    return JSONResponse({
        "ok": True,
        "deleted_id": preset_id,
        "presets": [serialize_lab_preset(t) for t in all_items],
    })


@router.post("/presets/restore-defaults")
def restore_default_lab_presets_api(
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
):
    """Restaura los perfiles de laboratorio de fábrica que hayan sido eliminados, conservando los personalizados."""
    _ensure_lab_seed_marker(db)
    existing_titles = {
        (t.title or "").strip().lower()
        for t in db.query(ClinicalTemplate).filter(ClinicalTemplate.category == "lab").all()
    }
    restored = 0
    for preset in DEFAULT_LAB_PRESETS:
        if preset["title"].strip().lower() not in existing_titles:
            db.add(
                ClinicalTemplate(
                    doctor_id=getattr(current_user, "id", None),
                    category="lab",
                    title=preset["title"],
                    content="\n".join(preset["tests"]),
                    is_global=True,
                )
            )
            restored += 1
    if restored > 0:
        db.commit()

    all_items = (
        db.query(ClinicalTemplate)
        .filter(ClinicalTemplate.category == "lab")
        .order_by(ClinicalTemplate.id.asc())
        .all()
    )
    return JSONResponse({
        "ok": True,
        "restored": restored,
        "presets": [serialize_lab_preset(t) for t in all_items],
    })

@router.get("/results")
def list_lab_results_history(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
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
    current_user = Depends(require_permission('labs'))
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
    current_user = Depends(require_permission('labs'))
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
            "Investigación de Células Falciformes (Falcemia)",
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
            "Sonografía Pélvica",
            "Sonografía Transvaginal",
            "Sonografía Abdominal",
            "Sonografía Obstétrica",
            "Sonografía Morfológica",
            "Sonografía Genética",
            "Sonografía Perfil Hemodinámico",
            "Sonografía Doppler Placentario",
            "Sonomamografía",
            "Radiografía Pélvica",
            "Tomografía Abdominal",
            "Tomografía Pélvica",
        ]
    }
]

@router.get("/orders")
def list_lab_orders(
    request: Request,
    patient_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
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
    current_user = Depends(require_permission('labs'))
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
    current_user = Depends(require_permission('labs'))
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


@router.api_route("/talonario/quick", methods=["GET", "POST"])
def quick_talonario_lab_order(
    request: Request,
    patient_id: int = Form(None),
    consultation_id: int = Form(None),
    clinical_indication: str = Form(None),
    tests: list[str] = Form([]),
    other_tests: str = Form(None),
    notes: str = Form(None),
    order_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('labs'))
):
    """
    Guarda la orden e inmediatamente retorna el PDF del talonario preimpreso (21.7 × 13.6 cm).
    Soporta POST (envío directo de formulario) y GET (reimpresión / refresco de pestaña del navegador).
    """
    setting = db.query(Setting).first()

    # Si es petición GET (por ejemplo al recargar la pestaña del navegador o enlace directo)
    if request.method == "GET":
        # 1. Si especifican order_id en query params
        if order_id:
            order = db.query(LabOrder).filter(LabOrder.id == order_id).first()
            if order:
                pdf_buffer = generate_lab_order_talonario_pdf(order, setting)
                p = order.patient
                doc_id = p.document_id if p and p.document_id else (str(p.id) if p else "")
                filename = f"Talonario_Laboratorio_{doc_id}_{order.id}.pdf"
                return StreamingResponse(
                    pdf_buffer,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={filename}"}
                )

        # 2. Si no hay parámetros, recuperar la última orden para renderizar su talonario sin error 405
        last_order = db.query(LabOrder).order_by(LabOrder.id.desc()).first()
        if last_order:
            pdf_buffer = generate_lab_order_talonario_pdf(last_order, setting)
            p = last_order.patient
            doc_id = p.document_id if p and p.document_id else (str(p.id) if p else "")
            filename = f"Talonario_Laboratorio_{doc_id}_{last_order.id}.pdf"
            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )

        return RedirectResponse(url="/lab-results", status_code=303)

    # Si es POST pero no seleccionaron paciente, volver al formulario
    if not patient_id:
        return RedirectResponse(url="/lab-results", status_code=303)

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
    current_user = Depends(require_permission('labs'))
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
    current_user = Depends(require_permission('labs'))
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
    current_user = Depends(require_permission('labs'))
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
