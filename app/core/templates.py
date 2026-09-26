import sys
from pathlib import Path
from fastapi.templating import Jinja2Templates
from app.services.ars_service import render_ars_badge_html, get_all_ars, find_ars, ARS_LIST

BASE_DIR = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent.parent

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Filtros y helpers globales Jinja2
templates.env.filters["ars_badge"] = lambda name, aff=None: render_ars_badge_html(name, aff)
templates.env.globals["render_ars_badge"] = render_ars_badge_html
templates.env.globals["ARS_LIST"] = ARS_LIST
templates.env.globals["get_all_ars"] = get_all_ars
