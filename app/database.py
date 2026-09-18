import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os
import shutil

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

def get_data_dir() -> Path:
    """
    Determina la ruta de datos con permisos de escritura garantizados:
    1. Variable de entorno explícita SSCP_DATA_DIR (si existe).
    2. Modo portátil: si existe 'portable.flag' o SSCP_PORTABLE=1 en APP_DIR.
    3. Modo desarrollo (no congelado): APP_DIR / 'data'.
    4. Modo producción instalado (frozen en Windows): %LOCALAPPDATA%/SSCP/data.
    """
    if os.environ.get("SSCP_DATA_DIR"):
        target = Path(os.environ["SSCP_DATA_DIR"])
        target.mkdir(parents=True, exist_ok=True)
        return target

    is_frozen = getattr(sys, 'frozen', False)
    is_portable = (
        os.environ.get("SSCP_PORTABLE") == "1"
        or (APP_DIR / "portable.flag").exists()
        or (APP_DIR / "portable.dat").exists()
    )

    if not is_frozen or is_portable:
        target = APP_DIR / "data"
        target.mkdir(parents=True, exist_ok=True)
        return target

    # Modo ejecutable instalado en Windows: usar %LOCALAPPDATA%
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        target = Path(local_app_data) / "SSCP" / "data"
    else:
        target = Path.home() / "AppData" / "Local" / "SSCP" / "data"

    target.mkdir(parents=True, exist_ok=True)

    # Migrar o copiar archivos iniciales generados en la instalación (e.g. license_mode.txt)
    install_data = APP_DIR / "data"
    if install_data.exists():
        for item in ["license_mode.txt"]:
            src = install_data / item
            dst = target / item
            if src.exists() and not dst.exists():
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass

    return target

DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "sscp.db"

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
