from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models.template import ClinicalTemplate
from app.core.deps import require_permission
from app.routers.lab_results import (
    LAB_SEEDED_MARKER_CATEGORY,
    ensure_default_lab_presets,
    parse_lab_template_tests,
    _ensure_lab_seed_marker,
)

router = APIRouter(prefix="/templates", tags=["templates"])
from app.core.templates import templates

@router.get("/")
def list_templates(
    request: Request,
    category: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('templates'))
):
    ensure_default_lab_presets(db, getattr(current_user, "id", None))
    query = db.query(ClinicalTemplate).filter(ClinicalTemplate.category != LAB_SEEDED_MARKER_CATEGORY)
    if category:
        query = query.filter(ClinicalTemplate.category == category)
        
    clinical_templates = query.order_by(ClinicalTemplate.title).all()
    
    return templates.TemplateResponse(
        request=request,
        name="clinical_templates/index.html",
        context={
            "user": current_user,
            "templates": clinical_templates,
            "selected_category": category,
        }
    )

@router.post("/create")
def create_template(
    title: str = Form(...),
    category: str = Form(...), # "prescription", "consultation", "license", "reference", "lab"
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('templates'))
):
    clean_title = title.strip()
    clean_content = content.strip()
    if category == "lab":
        _ensure_lab_seed_marker(db)
        parsed_tests = parse_lab_template_tests(clean_content)
        clean_content = "\n".join(parsed_tests) if parsed_tests else clean_content

    new_tpl = ClinicalTemplate(
        doctor_id=current_user.id,
        category=category,
        title=clean_title,
        content=clean_content,
        is_global=(category != "lab")
    )
    db.add(new_tpl)
    db.commit()
    return RedirectResponse(url="/templates", status_code=303)

@router.post("/{template_id}/edit")
def edit_template(
    template_id: int,
    title: str = Form(...),
    category: str = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('templates'))
):
    tpl = (
        db.query(ClinicalTemplate)
        .filter(
            ClinicalTemplate.id == template_id,
            ClinicalTemplate.category != LAB_SEEDED_MARKER_CATEGORY,
        )
        .first()
    )
    if not tpl:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    clean_title = title.strip()
    clean_content = content.strip()
    if category == "lab":
        _ensure_lab_seed_marker(db)
        parsed_tests = parse_lab_template_tests(clean_content)
        clean_content = "\n".join(parsed_tests) if parsed_tests else clean_content
    tpl.title = clean_title
    tpl.category = category
    tpl.content = clean_content
    db.commit()
    return RedirectResponse(url="/templates", status_code=303)

@router.post("/{template_id}/delete")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('templates'))
):
    tpl = (
        db.query(ClinicalTemplate)
        .filter(
            ClinicalTemplate.id == template_id,
            ClinicalTemplate.category != LAB_SEEDED_MARKER_CATEGORY,
        )
        .first()
    )
    if tpl:
        if tpl.category == "lab":
            _ensure_lab_seed_marker(db)
        db.delete(tpl)
        db.commit()
    return RedirectResponse(url="/templates", status_code=303)

@router.get("/api")
def api_get_templates(
    category: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission('templates'))
):
    ensure_default_lab_presets(db, getattr(current_user, "id", None))
    query = db.query(ClinicalTemplate).filter(ClinicalTemplate.category != LAB_SEEDED_MARKER_CATEGORY)
    if category:
        query = query.filter(ClinicalTemplate.category == category)
    items = query.order_by(ClinicalTemplate.title).all()
    return JSONResponse([
        {"id": t.id, "title": t.title, "category": t.category, "content": t.content}
        for t in items
    ])
