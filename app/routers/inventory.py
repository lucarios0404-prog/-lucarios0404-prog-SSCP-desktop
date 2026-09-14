from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pathlib import Path
from datetime import datetime

from app.database import get_db
from app.models.inventory import InventoryItem, InventoryMovement
from app.core.deps import require_current_user

router = APIRouter(prefix="/inventory", tags=["inventory"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

COMMON_CATEGORIES = [
    "Medicamento",
    "Material Gastable",
    "Insumo Quirúrgico",
    "Reactivo de Laboratorio",
    "Equipo Médico",
    "Otro"
]

COMMON_UNITS = [
    "Unidad",
    "Caja",
    "Frasco",
    "Ampolla",
    "Blister",
    "Tubo",
    "Sobres",
    "ml"
]

@router.get("/")
def list_inventory(
    request: Request,
    q: str = Query(None),
    category: str = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    query = db.query(InventoryItem)
    
    if q:
        query = query.filter(
            or_(
                InventoryItem.name.ilike(f"%{q}%"),
                InventoryItem.description.ilike(f"%{q}%")
            )
        )
    if category:
        query = query.filter(InventoryItem.category == category)
        
    items = query.order_by(InventoryItem.name.asc()).all()
    
    # Métricas y alertas
    total_items = len(items)
    low_stock_items = [item for item in items if item.stock <= item.min_stock]
    low_stock_count = len(low_stock_items)
    total_inventory_value = sum((item.stock * item.price) for item in items if item.price)
    
    # Últimos movimientos
    recent_movements = db.query(InventoryMovement).order_by(InventoryMovement.created_at.desc()).limit(8).all()
    
    return templates.TemplateResponse(
        request=request,
        name="inventory/index.html",
        context={
            "user": current_user,
            "items": items,
            "total_items": total_items,
            "low_stock_count": low_stock_count,
            "total_inventory_value": total_inventory_value,
            "recent_movements": recent_movements,
            "categories": COMMON_CATEGORIES,
            "q": q or "",
            "selected_category": category or "",
        }
    )

@router.get("/create")
def create_item_form(
    request: Request,
    current_user = Depends(require_current_user)
):
    return templates.TemplateResponse(
        request=request,
        name="inventory/create.html",
        context={
            "user": current_user,
            "categories": COMMON_CATEGORIES,
            "units": COMMON_UNITS,
        }
    )

@router.post("/create")
def create_item(
    request: Request,
    name: str = Form(...),
    category: str = Form("Medicamento"),
    description: str = Form(None),
    stock: int = Form(0),
    min_stock: int = Form(5),
    unit: str = Form("Unidad"),
    price: float = Form(0.0),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    item = InventoryItem(
        name=name.strip(),
        category=category,
        description=description.strip() if description else None,
        stock=max(0, stock),
        min_stock=max(0, min_stock),
        unit=unit,
        price=max(0.0, price)
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    
    # Si ingresó con stock inicial mayor a 0, registrar movimiento
    if stock > 0:
        mov = InventoryMovement(
            inventory_item_id=item.id,
            user_id=current_user.id,
            type="in",
            quantity=stock,
            notes="Stock inicial al crear el producto"
        )
        db.add(mov)
        db.commit()
        
    return RedirectResponse(url="/inventory", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{item_id}")
def view_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
        
    movements = db.query(InventoryMovement).filter(
        InventoryMovement.inventory_item_id == item_id
    ).order_by(InventoryMovement.created_at.desc()).all()
    
    return templates.TemplateResponse(
        request=request,
        name="inventory/view.html",
        context={
            "user": current_user,
            "item": item,
            "movements": movements,
            "categories": COMMON_CATEGORIES,
            "units": COMMON_UNITS,
        }
    )

@router.post("/{item_id}/movement")
def register_movement(
    item_id: int,
    request: Request,
    type: str = Form(...), # in, out, adjustment
    quantity: int = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
        
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")
        
    if type == "in":
        item.stock += quantity
    elif type == "out":
        if item.stock < quantity:
            # permitir con advertencia o limitar a 0
            item.stock = max(0, item.stock - quantity)
        else:
            item.stock -= quantity
    elif type == "adjustment":
        item.stock = quantity
    else:
        raise HTTPException(status_code=400, detail="Tipo de movimiento no válido")
        
    movement = InventoryMovement(
        inventory_item_id=item.id,
        user_id=current_user.id,
        type=type,
        quantity=quantity,
        notes=notes.strip() if notes else None
    )
    db.add(movement)
    db.commit()
    
    return RedirectResponse(url=f"/inventory/{item_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{item_id}/edit")
def edit_item(
    item_id: int,
    request: Request,
    name: str = Form(...),
    category: str = Form("Medicamento"),
    description: str = Form(None),
    min_stock: int = Form(5),
    unit: str = Form("Unidad"),
    price: float = Form(0.0),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
        
    item.name = name.strip()
    item.category = category
    item.description = description.strip() if description else None
    item.min_stock = max(0, min_stock)
    item.unit = unit
    item.price = max(0.0, price)
    
    db.commit()
    return RedirectResponse(url=f"/inventory/{item_id}", status_code=status.HTTP_303_SEE_OTHER)
