from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models.template import ClinicalTemplate
from app.core.deps import require_current_user

router = APIRouter(prefix="/templates", tags=["templates"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/")
def list_templates(
    request: Request,
    category: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(ClinicalTemplate)
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
    category: str = Form(...), # "prescription", "consultation", "license", "reference"
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    new_tpl = ClinicalTemplate(
        doctor_id=current_user.id,
        category=category,
        title=title,
        content=content,
        is_global=True
    )
    db.add(new_tpl)
    db.commit()
    return RedirectResponse(url="/templates", status_code=303)

@router.post("/{template_id}/delete")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    tpl = db.query(ClinicalTemplate).filter(ClinicalTemplate.id == template_id).first()
    if tpl:
        db.delete(tpl)
        db.commit()
    return RedirectResponse(url="/templates", status_code=303)

@router.get("/api")
def api_get_templates(
    category: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(ClinicalTemplate)
    if category:
        query = query.filter(ClinicalTemplate.category == category)
    items = query.order_by(ClinicalTemplate.title).all()
    return JSONResponse([
        {"id": t.id, "title": t.title, "category": t.category, "content": t.content}
        for t in items
    ])
