from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt
import os
import secrets
from pathlib import Path
from app.database import DATA_DIR

def _get_or_create_secret_key() -> str:
    """
    Obtiene o genera una clave secreta criptográfica única de 256 bits por instalación.
    Evita que tokens JWT puedan ser falsificados entre distintas máquinas.
    """
    env_key = os.environ.get("SSCP_SECRET_KEY")
    if env_key and len(env_key) >= 32:
        return env_key

    key_file = DATA_DIR / ".secret_key"
    if key_file.exists():
        try:
            stored_key = key_file.read_text(encoding="utf-8").strip()
            if len(stored_key) >= 32:
                return stored_key
        except Exception:
            pass

    # Generar nueva clave aleatoria de alta entropía (64 caracteres hexadecimales = 256 bits)
    new_key = secrets.token_hex(32)
    try:
        key_file.write_text(new_key, encoding="utf-8")
    except Exception:
        pass
    return new_key

SECRET_KEY = _get_or_create_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 días

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
