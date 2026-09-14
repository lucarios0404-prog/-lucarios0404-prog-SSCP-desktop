"""
Router for Importing Data from 'Consulta Práctica' (MDB), CSV and Excel spreadsheets.
"""
import os
import json
import time
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import require_current_user, require_permission
from app.services.data_importer import DataImporterService

router = APIRouter(prefix="/patients/import", tags=["import"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Temporary in-memory session cache for large import payloads during preview
_import_preview_cache = {}

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def show_import_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("patients"))
):
    """
    Renders the data import wizard view.
    """
    return templates.TemplateResponse(
        request=request,
        name="patients/import.html",
        context={
            "user": current_user,
            "title": "Importar Datos — Consulta Práctica",
            "active_menu": "import"
        }
    )

@router.post("/preview")
async def preview_import_file(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("patients"))
):
    """
    Parses the uploaded file (.mdb, .csv, .xlsx) and returns preview statistics.
    """
    filename = file.filename.lower()
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="El archivo subido está vacío.")

    temp_path = None
    try:
        if filename.endswith(".mdb"):
            # Microsoft Access Consulta Práctica file
            with tempfile.NamedTemporaryFile(suffix=".mdb", delete=False) as tmp:
                tmp.write(content)
                temp_path = tmp.name
            raw_records = DataImporterService.parse_mdb(temp_path)
            source_type = "Base de Datos Access (Consulta Práctica)"
        elif filename.endswith(".xlsx"):
            # Excel spreadsheet
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(content)
                temp_path = tmp.name
            raw_records = DataImporterService.parse_excel(temp_path)
            source_type = "Hoja de Cálculo Excel (.xlsx)"
        elif filename.endswith(".csv") or filename.endswith(".txt"):
            # CSV tabular export
            raw_records = DataImporterService.parse_csv(content)
            source_type = "Archivo Delimitado CSV / TXT"
        else:
            raise HTTPException(
                status_code=400,
                detail="Formato no soportado. Por favor seleccione un archivo .mdb de Consulta Práctica, un archivo .csv o una hoja .xlsx."
            )

        if not raw_records:
            raise HTTPException(
                status_code=400,
                detail="No se encontraron registros de pacientes válidos en el archivo proporcionado."
            )

        preview_result = DataImporterService.preview_data(raw_records, db)
        preview_result["source_type"] = source_type
        preview_result["filename"] = file.filename

        # Cache key for confirmation
        cache_token = f"import_{current_user.id}_{int(time.time())}"
        _import_preview_cache[cache_token] = preview_result["all_records"]
        preview_result["cache_token"] = cache_token
        
        # Omit all_records from preview JSON to keep payload lightweight
        preview_result.pop("all_records", None)

        return JSONResponse(content=preview_result)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

@router.post("/confirm")
async def confirm_import(
    request: Request,
    cache_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("patients"))
):
    """
    Executes the database import from the cached preview token.
    """
    records = _import_preview_cache.get(cache_token)
    if not records:
        raise HTTPException(
            status_code=400,
            detail="La sesión de importación ha expirado o no es válida. Por favor vuelva a cargar el archivo."
        )

    result = DataImporterService.execute_import(
        patients_data=records,
        db=db,
        doctor_id=current_user.id
    )

    # Clean cache
    _import_preview_cache.pop(cache_token, None)

    return JSONResponse(content=result)
