from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime

from app.database import get_db
from app.models.message import InternalMessage
from app.models.user import User
from app.models.patient import Patient
from app.core.deps import require_current_user

router = APIRouter(prefix="/messages", tags=["messages"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

@router.get("/")
def list_messages(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    # Mensajes recibidos o dirigidos a todos
    messages = db.query(InternalMessage).filter(
        (InternalMessage.recipient_id == current_user.id) | (InternalMessage.recipient_id == None)
    ).order_by(InternalMessage.created_at.desc()).all()

    users = db.query(User).filter(User.id != current_user.id).all()
    patients = db.query(Patient).order_by(Patient.last_name).all()

    return templates.TemplateResponse(
        request=request,
        name="messages/index.html",
        context={
            "user": current_user,
            "messages": messages,
            "users": users,
            "patients": patients,
        }
    )

@router.post("/send")
def send_message(
    request: Request,
    recipient_id: int = Form(None),
    patient_id: int = Form(None),
    subject: str = Form("Aviso interno"),
    content: str = Form(...),
    priority: str = Form("normal"),
    db: Session = Depends(get_db),
    current_user = Depends(require_current_user)
):
    new_msg = InternalMessage(
        sender_id=current_user.id,
        recipient_id=recipient_id if recipient_id and recipient_id > 0 else None,
        patient_id=patient_id if patient_id and patient_id > 0 else None,
        subject=subject,
        content=content,
        priority=priority,
    )
    db.add(new_msg)
    db.commit()
    return RedirectResponse(url="/messages", status_code=303)
