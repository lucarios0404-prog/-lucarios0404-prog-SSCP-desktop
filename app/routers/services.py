from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.database import get_db
from app.models.service import Service
from app.models.user import User
from app.core.deps import require_current_user
from app.core.templates import templates

router = APIRouter(prefix="/services", tags=["services"])

# --- JSON API para Citas, Pagos y App Móvil ---
@router.get("/api/list")
def get_services_json(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    """Retorna la lista de servicios activos para autocompletado en citas y cobros."""
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.name).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "price": s.price,
            "price_formatted": f"RD$ {s.price:,.2f}",
            "color": s.color or "#3b82f6",
            "category": s.category or "General"
        }
        for s in services
    ]

# --- Vista Web del Talonario de Servicios y Precios ---
@router.get("/", response_class=HTMLResponse)
def list_services_view(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    services = db.query(Service).order_by(Service.category, Service.name).all()
    
    # Agrupar por categorías
    categories = {}
    for s in services:
        cat = s.category or "General"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(s)

    return templates.TemplateResponse(
        request=request,
        name="services/index.html",
        context={
            "user": current_user,
            "services": services,
            "categories": categories,
            "total_services": len(services),
            "active_services": sum(1 for s in services if s.is_active)
        }
    )

# --- Crear Nuevo Servicio ---
@router.post("/create")
def create_service(
    request: Request,
    name: str = Form(...),
    price: float = Form(0.0),
    color: str = Form("#3b82f6"),
    category: str = Form("Consultas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre del servicio es obligatorio")

    existing = db.query(Service).filter(func.lower(Service.name) == clean_name.lower()).first()
    if existing:
        # Si ya existe pero estaba inactivo, lo reactivamos
        existing.is_active = True
        existing.price = price
        existing.color = color
        existing.category = category
        db.commit()
    else:
        srv = Service(
            name=clean_name,
            price=price,
            color=color,
            category=category,
            is_active=True
        )
        db.add(srv)
        db.commit()

    return RedirectResponse(url="/services?created=1", status_code=303)

# --- Editar Servicio ---
@router.post("/{service_id}/edit")
def edit_service(
    service_id: int,
    name: str = Form(...),
    price: float = Form(0.0),
    color: str = Form("#3b82f6"),
    category: str = Form("Consultas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    srv = db.query(Service).filter(Service.id == service_id).first()
    if not srv:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    srv.name = name.strip()
    srv.price = price
    srv.color = color
    srv.category = category
    db.commit()

    return RedirectResponse(url="/services?updated=1", status_code=303)

# --- Alternar Estado / Eliminar ---
@router.post("/{service_id}/toggle")
def toggle_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    srv = db.query(Service).filter(Service.id == service_id).first()
    if not srv:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    srv.is_active = not srv.is_active
    db.commit()

    return RedirectResponse(url="/services?toggled=1", status_code=303)
