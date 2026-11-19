import sys
import gc
import time
import threading
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os
import shutil

_DB_RECOVERY_LOCK = threading.RLock()

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
    4. Modo producción instalado (frozen en Windows): %APPDATA%/SSCP Desktop/data (alineado con Electron).
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

    # Alinear ruta de producción Windows con Electron (app.getPath('userData') / 'data')
    roaming = os.environ.get("APPDATA")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if roaming:
        target = Path(roaming) / "SSCP Desktop" / "data"
    elif local_app_data:
        target = Path(local_app_data) / "SSCP" / "data"
    else:
        target = Path.home() / "AppData" / "Local" / "SSCP" / "data"

    target.mkdir(parents=True, exist_ok=True)

    # Migrar archivos iniciales desde carpeta de instalación o %LOCALAPPDATA%\SSCP\data si faltan en target
    for legacy_dir in [APP_DIR / "data", (Path(local_app_data) / "SSCP" / "data") if local_app_data else None]:
        if not legacy_dir or not legacy_dir.exists() or legacy_dir.resolve() == target.resolve():
            continue
        for item in ["license_mode.txt", ".secret_key", "supabase_preset.json"]:
            src = legacy_dir / item
            dst = target / item
            if src.exists() and not dst.exists():
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass

    return target

DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "sscp.db"


def _sqlite_is_healthy(target: Path) -> bool:
    """Verifica encabezado, integridad rápida y lectura real de sqlite_master / tablas clave."""
    import sqlite3

    if not target.exists() or target.stat().st_size == 0:
        return True
    try:
        with target.open("rb") as fh:
            hdr = fh.read(16)
        if len(hdr) < 16 or hdr != b"SQLite format 3\x00":
            return False
    except Exception:
        return False

    conn = None
    try:
        conn = sqlite3.connect(str(target), timeout=5.0)
        q_row = conn.execute("PRAGMA quick_check(1)").fetchone()
        if not q_row or str(q_row[0]).lower() != "ok":
            return False
        i_row = conn.execute("PRAGMA integrity_check(1)").fetchone()
        if not i_row or str(i_row[0]).lower() != "ok":
            return False
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        existing = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for critical_tbl in ("users", "license_configs", "settings"):
            if critical_tbl in existing:
                conn.execute(f'PRAGMA main.table_info("{critical_tbl}")').fetchall()
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _safe_move_aside(src: Path, dst: Path) -> bool:
    """Mueve o elimina un archivo bloqueado temporalmente en Windows con reintentos breves."""
    if not src.exists():
        return True
    for attempt in range(6):
        gc.collect()
        try:
            src.replace(dst)
            return True
        except Exception:
            time.sleep(0.08 * (attempt + 1))
    try:
        src.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _quarantine_sqlite_sidecars(db_path: Path, stamp: int) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            _safe_move_aside(sidecar, Path(f"{sidecar}.orphan.{stamp}"))


def repair_sqlite_if_malformed(db_path: Path = DB_PATH, *, reset_if_unrecoverable: bool = True) -> bool:
    """Detecta y repara corrupción SQLite o sidecars -wal/-shm huérfanos; si es irrecuperable, aísla y reinicia limpia."""
    import sqlite3

    with _DB_RECOVERY_LOCK:
        if not db_path.exists() or db_path.stat().st_size == 0:
            return True

        if _sqlite_is_healthy(db_path):
            return True

        stamp = int(time.time())
        # 1. Intentar REINDEX + checkpoint WAL
        try:
            c = sqlite3.connect(str(db_path), timeout=5.0)
            try:
                c.execute("REINDEX")
                c.commit()
            except Exception:
                pass
            try:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            c.close()
        except Exception:
            pass
        if _sqlite_is_healthy(db_path):
            return True

        # 2. Aislar sidecars -wal/-shm/-journal desfasados
        _quarantine_sqlite_sidecars(db_path, stamp)
        if _sqlite_is_healthy(db_path):
            return True

        # 3. Rescate completo por iterdump / copia tabla a tabla hacia BD limpia
        repaired_path = Path(f"{db_path}.repaired.{stamp}")
        rescued = False
        src = None
        dst = None
        try:
            src = sqlite3.connect(str(db_path), timeout=5.0)
            dst = sqlite3.connect(str(repaired_path), timeout=5.0)
            try:
                for line in src.iterdump():
                    try:
                        dst.execute(line)
                    except Exception:
                        pass
                dst.commit()
                rescued = True
            except Exception:
                # Respaldo tabla por tabla si iterdump falla en alguna tabla corrupta
                try:
                    tables = src.execute(
                        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    for tname, tsql in tables:
                        try:
                            dst.execute(tsql)
                            rows = src.execute(f'SELECT * FROM "{tname}"').fetchall()
                            if rows:
                                placeholders = ",".join(["?"] * len(rows[0]))
                                dst.executemany(f'INSERT OR IGNORE INTO "{tname}" VALUES ({placeholders})', rows)
                            rescued = True
                        except Exception:
                            pass
                    dst.commit()
                except Exception:
                    pass
        except Exception as exc:
            print(f"[DB Recovery] Aviso abriendo BD dañada para rescate: {exc}")
        finally:
            for handle in (src, dst):
                if handle is not None:
                    try:
                        handle.close()
                    except Exception:
                        pass

        if rescued and _sqlite_is_healthy(repaired_path):
            corrupt_bak = Path(f"{db_path}.corrupt.{stamp}")
            _quarantine_sqlite_sidecars(db_path, stamp)
            if _safe_move_aside(db_path, corrupt_bak):
                if _safe_move_aside(repaired_path, db_path):
                    _quarantine_sqlite_sidecars(db_path, stamp)
                    print(f"[DB Recovery] SQLite reparado automáticamente (respaldo previo: {corrupt_bak.name}).")
                    return True

        try:
            if repaired_path.exists():
                repaired_path.unlink()
        except Exception:
            pass

        # 4. Cuarentena forzada si la corrupción destruyó sqlite_master/encabezado (irrecuperable)
        if reset_if_unrecoverable:
            corrupt_bak = Path(f"{db_path}.corrupt.{stamp}")
            _quarantine_sqlite_sidecars(db_path, stamp)
            if _safe_move_aside(db_path, corrupt_bak):
                _quarantine_sqlite_sidecars(db_path, stamp)
                try:
                    fresh = sqlite3.connect(str(db_path), timeout=5.0)
                    fresh.close()
                except Exception:
                    pass
                if _sqlite_is_healthy(db_path):
                    print(f"[DB Recovery] BD irrecuperable aislada en {corrupt_bak.name}; BD limpia inicializada.")
                    return True

        return False


repair_sqlite_if_malformed(DB_PATH)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=20,
    max_overflow=30,
    pool_timeout=45,
)

from sqlalchemy import event
import unicodedata

@event.listens_for(engine, "connect")
def register_sqlite_functions(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

    def unaccent(value):
        if value is None:
            return ""
        nfkd = unicodedata.normalize('NFKD', str(value))
        return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()
    try:
        dbapi_connection.create_function("unaccent", 1, unaccent)
    except Exception:
        pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
