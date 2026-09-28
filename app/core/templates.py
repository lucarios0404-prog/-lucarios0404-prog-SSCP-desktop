import sys
from pathlib import Path
from fastapi.templating import Jinja2Templates
from app.services.ars_service import render_ars_badge_html, get_all_ars, find_ars, ARS_LIST

BASE_DIR = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent.parent

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

from datetime import date, datetime, time

def safe_date_fmt(val, fmt="%d/%m/%Y", default="—"):
    if not val:
        return default
    try:
        if isinstance(val, (datetime, date)):
            return val.strftime(fmt)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.strftime(fmt)
            except Exception:
                return val
    except Exception:
        pass
    return default

def safe_time_fmt(val, fmt="%H:%M", default="—"):
    if not val:
        return default
    try:
        if isinstance(val, (datetime, time)):
            return val.strftime(fmt)
        if isinstance(val, str):
            return val
    except Exception:
        pass
    return default

def safe_datetime_fmt(val, fmt="%d/%m/%Y %H:%M", default="—"):
    if not val:
        return default
    try:
        if isinstance(val, (datetime, date)):
            return val.strftime(fmt)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.strftime(fmt)
            except Exception:
                return val
    except Exception:
        pass
    return default

# Filtros y helpers globales Jinja2
templates.env.filters["date_fmt"] = safe_date_fmt
templates.env.filters["time_fmt"] = safe_time_fmt
templates.env.filters["datetime_fmt"] = safe_datetime_fmt
templates.env.globals["format_date"] = safe_date_fmt
templates.env.globals["format_time"] = safe_time_fmt
templates.env.globals["format_datetime"] = safe_datetime_fmt
templates.env.filters["ars_badge"] = lambda name, aff=None: render_ars_badge_html(name, aff)
templates.env.globals["render_ars_badge"] = render_ars_badge_html
templates.env.globals["ARS_LIST"] = ARS_LIST
templates.env.globals["get_all_ars"] = get_all_ars

def get_current_setting():
    try:
        from app.database import SessionLocal
        from app.models.setting import Setting
        with SessionLocal() as db:
            s = db.query(Setting).first()
            if s:
                # Detach object or create lightweight dict to prevent session detachment issues
                return {
                    "station_role": getattr(s, "station_role", "doctor_principal") or "doctor_principal",
                    "central_station_url": getattr(s, "central_station_url", None),
                    "clinic_name": s.clinic_name,
                    "doctor_name": s.doctor_name,
                    "tailscale_ip": s.tailscale_ip,
                    "updated_at": s.updated_at
                }
    except Exception:
        pass
    return {
        "station_role": "doctor_principal",
        "central_station_url": None,
        "clinic_name": "SSCP Desktop",
        "doctor_name": "Dr. Especialista",
        "tailscale_ip": None,
        "updated_at": None
    }

templates.env.globals["get_current_setting"] = get_current_setting
