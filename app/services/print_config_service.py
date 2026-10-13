import json
from pathlib import Path
from typing import Dict, Any
from app.database import get_data_dir

# Coordenadas y dimensiones calibradas por defecto para el talonario del Dr. Carlos M. Heredia
# Dimensiones físicas: 13.6 cm ancho x 21.7 cm alto (Media Carta Vertical)
DEFAULT_PRINT_CONFIG: Dict[str, Any] = {
    "print_mode": "talonario",
    "paper_width_mm": 136.0,
    "paper_height_mm": 217.0,
    "paper_size": "HalfLetter",
    "standard_margins": {
        "top": 15.0,
        "bottom": 15.0,
        "left": 20.0,
        "right": 15.0,
        "paperSize": "Letter"
    },
    "fields": {
        "patient_name": {
            "x": 28.0,
            "y": 178.5,
            "width": 98.0,
            "fontSize": 10.5,
            "onlyValue": True,
            "label": "PACIENTE:"
        },
        "age": {
            "x": 16.0,
            "y": 187.0,
            "width": 25.0,
            "fontSize": 10.0,
            "onlyValue": True,
            "label": "EDAD:"
        },
        "id_card": {
            "x": 52.0,
            "y": 187.0,
            "width": 48.0,
            "fontSize": 10.0,
            "onlyValue": True,
            "label": "CED.:"
        },
        "date": {
            "x": 102.0,
            "y": 187.0,
            "width": 30.0,
            "fontSize": 10.0,
            "onlyValue": True,
            "label": "FECHA:"
        },
        "medications": {
            "x": 16.0,
            "y": 72.0,
            "width": 108.0,
            "fontSize": 9.5,
            "onlyValue": True,
            "label": "Rp."
        }
    }
}

import os
import shutil

def get_print_config_path() -> Path:
    return get_data_dir() / "print_config.json"

def get_print_config() -> Dict[str, Any]:
    """
    Obtiene la configuración activa de márgenes y coordenadas del talonario.
    Si el archivo no existe o está corrupto, busca en el respaldo (.bak)
    antes de recurrir a los valores calibrados por defecto.
    """
    path = get_print_config_path()
    bak_path = path.with_suffix(".json.bak")

    # Intentar leer el principal o el backup si el principal está ausente o corrupto
    for candidate in [path, bak_path]:
        if candidate.exists() and candidate.stat().st_size > 0:
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    merged = dict(DEFAULT_PRINT_CONFIG)
                    merged.update(data)
                    if "fields" in data and isinstance(data["fields"], dict):
                        merged["fields"] = dict(DEFAULT_PRINT_CONFIG["fields"])
                        merged["fields"].update(data["fields"])
                    # Si recuperamos desde el backup porque el principal faltaba, restaurar el principal
                    if candidate == bak_path and (not path.exists() or path.stat().st_size == 0):
                        try:
                            save_print_config(merged)
                        except Exception:
                            pass
                    return merged
            except Exception:
                continue
    
    # Si ninguno existe ni es válido, inicializar con defaults
    save_print_config(DEFAULT_PRINT_CONFIG)
    return dict(DEFAULT_PRINT_CONFIG)

def save_print_config(new_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persiste la configuración de impresión de forma atómica y segura en Windows,
    manteniendo siempre un respaldo .bak para tolerar cortes de energía o reinicios.
    """
    current = {}
    path = get_print_config_path()
    bak_path = path.with_suffix(".json.bak")

    for candidate in [path, bak_path]:
        if candidate.exists() and candidate.stat().st_size > 0:
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    current = json.load(f)
                    break
            except Exception:
                current = {}
            
    merged = dict(DEFAULT_PRINT_CONFIG)
    merged.update(current)
    merged.update(new_config)

    # 1. Integrar plantilla de Electron si viene encapsulada
    if "print_template_config" in new_config and isinstance(new_config["print_template_config"], dict):
        tpl = new_config["print_template_config"]
        if "fields" in tpl and isinstance(tpl["fields"], dict):
            merged["fields"] = dict(tpl["fields"])
        if "paper_width_mm" in tpl:
            merged["paper_width_mm"] = float(tpl["paper_width_mm"])
        if "paper_height_mm" in tpl:
            merged["paper_height_mm"] = float(tpl["paper_height_mm"])
        if "standard_margins" in tpl and isinstance(tpl["standard_margins"], dict):
            std = dict(merged.get("standard_margins", DEFAULT_PRINT_CONFIG["standard_margins"]))
            std.update(tpl["standard_margins"])
            merged["standard_margins"] = std

    # 2. Sincronización bidireccional estricta de standard_margins y print_margin_*
    std = dict(merged.get("standard_margins", DEFAULT_PRINT_CONFIG["standard_margins"]))
    if "standard_margins" in new_config and isinstance(new_config["standard_margins"], dict):
        std.update(new_config["standard_margins"])

    if "print_margin_top" in new_config and new_config["print_margin_top"] is not None:
        std["top"] = float(new_config["print_margin_top"])
    if "print_margin_bottom" in new_config and new_config["print_margin_bottom"] is not None:
        std["bottom"] = float(new_config["print_margin_bottom"])
    if "print_margin_left" in new_config and new_config["print_margin_left"] is not None:
        std["left"] = float(new_config["print_margin_left"])
    if "print_margin_right" in new_config and new_config["print_margin_right"] is not None:
        std["right"] = float(new_config["print_margin_right"])
    if "print_paper_size" in new_config and new_config["print_paper_size"]:
        std["paperSize"] = str(new_config["print_paper_size"])

    # Sincronizar hacia claves de primer nivel para Electron
    merged["standard_margins"] = std
    merged["print_margin_top"] = float(std.get("top", 15.0))
    merged["print_margin_bottom"] = float(std.get("bottom", 15.0))
    merged["print_margin_left"] = float(std.get("left", 20.0))
    merged["print_margin_right"] = float(std.get("right", 15.0))
    merged["print_paper_size"] = str(std.get("paperSize", "Letter"))

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")

        # 1. Escritura atómica en archivo temporal con flush físico
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass

        # 2. Mantener copia de seguridad .bak si el archivo actual es válido
        if path.exists() and path.stat().st_size > 0:
            try:
                shutil.copy2(path, bak_path)
            except Exception:
                pass

        # 3. Reemplazo atómico a nivel de sistema operativo
        os.replace(tmp_path, path)
    except Exception:
        pass

    return merged

