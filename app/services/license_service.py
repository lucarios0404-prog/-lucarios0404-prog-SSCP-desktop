"""
app/services/license_service.py
Servicio central de licenciamiento SSCP Desktop.

Soporta dos modalidades:
  - Modalidad A (offline): valida firma criptografica Ed25519 sin internet.
  - Modalidad B (online):  verifica contra servidor + cache local de 7 dias.
"""

import base64
import threading
import time
import hashlib
import json
import platform
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from app.database import DATA_DIR

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LICENSE_CACHE_FILE = DATA_DIR / "license_cache.json"
LICENSE_MODE_FILE = DATA_DIR / "license_mode.txt"

LICENSE_SERVER_URL = "https://sscp.laxarusdevs.com/api/v1/license"
CACHE_TTL_DAYS = 7

_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA3h68Aq7p2S+pJ+Sq3smhJIqVbth8ACRjgPJ1udwusTY=
-----END PUBLIC KEY-----"""


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    UNLICENSED = "unlicensed"
    EXPIRED = "expired"
    MACHINE_MISMATCH = "machine_mismatch"
    SERVER_UNREACHABLE = "server_unreachable"


class LicenseInfo:
    def __init__(self, status, machine_id="", doctor_name="", plan="",
                 expires_at=None, mode="offline", days_remaining=0):
        self.status = status
        self.machine_id = machine_id
        self.doctor_name = doctor_name
        self.plan = plan
        self.expires_at = expires_at
        self.mode = mode
        self.days_remaining = days_remaining


_cached_machine_id = None


def _run_wmic(query):
    try:
        startupinfo = None
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        result = subprocess.check_output(
            ["wmic"] + query.split(),
            stderr=subprocess.DEVNULL,
            timeout=5,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        lines = result.decode(errors="ignore").strip().splitlines()
        for line in lines:
            line = line.strip()
            if line and line not in ("Caption", query.split()[-1]):
                return line
    except Exception:
        pass
    return ""


def get_machine_id():
    global _cached_machine_id
    if _cached_machine_id:
        return _cached_machine_id

    parts = []
    if platform.system() == "Windows":
        parts.append(_run_wmic("baseboard get SerialNumber"))
        parts.append(_run_wmic("cpu get ProcessorId"))
        parts.append(_run_wmic("diskdrive get SerialNumber"))
    if not any(parts):
        parts.append(str(uuid.getnode()))
        parts.append(platform.node())
    raw = "|".join(filter(None, parts))
    digest = hashlib.sha256(raw.encode()).hexdigest().upper()
    _cached_machine_id = f"SSCP-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"
    return _cached_machine_id


def _load_public_key():
    return serialization.load_pem_public_key(_PUBLIC_KEY_PEM)


def _verify_offline_license(license_key, machine_id):
    try:
        parts = license_key.strip().split(".")
        if len(parts) != 2:
            return LicenseInfo(LicenseStatus.UNLICENSED, machine_id=machine_id)
        payload_b64, sig_b64 = parts
        payload_bytes = base64.b64decode(payload_b64)
        signature = base64.b64decode(sig_b64)
        pub_key = _load_public_key()
        pub_key.verify(signature, payload_bytes)
        payload = json.loads(payload_bytes.decode("utf-8"))
        lic_machine_id = payload.get("machine_id", "")
        doctor_name = payload.get("doctor_name", "Doctor")
        plan = payload.get("plan", "Standard")
        expires_str = payload.get("expires_at")
        if lic_machine_id and lic_machine_id != machine_id:
            return LicenseInfo(LicenseStatus.MACHINE_MISMATCH, machine_id=machine_id)
        expires_at = None
        days_remaining = 99999
        if expires_str and expires_str != "lifetime":
            expires_at = datetime.fromisoformat(expires_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            days_remaining = (expires_at - datetime.now(timezone.utc)).days
            if days_remaining < 0:
                return LicenseInfo(LicenseStatus.EXPIRED, machine_id=machine_id,
                                   doctor_name=doctor_name, plan=plan,
                                   expires_at=expires_at, days_remaining=0)
        return LicenseInfo(LicenseStatus.ACTIVE, machine_id=machine_id,
                           doctor_name=doctor_name, plan=plan, expires_at=expires_at,
                           mode="offline", days_remaining=days_remaining)
    except InvalidSignature:
        return LicenseInfo(LicenseStatus.UNLICENSED, machine_id=machine_id)
    except Exception:
        return LicenseInfo(LicenseStatus.UNLICENSED, machine_id=machine_id)


DESKTOP_LICENSE_API_KEY = "sscp-license-api-sec-2026-laxarus"


import hmac


def _compute_cache_signature(cache_data: dict, machine_id: str) -> str:
    """Genera una firma HMAC de 256 bits vinculada al Machine ID para garantizar la integridad de la caché."""
    key = hashlib.sha256(f"{machine_id}::SSCP_CACHE_INTEGRITY_SALT_2026".encode()).digest()
    canonical = (
        f"{cache_data.get('valid')}|{cache_data.get('machine_id')}|"
        f"{cache_data.get('license_token')}|{cache_data.get('doctor_name')}|"
        f"{cache_data.get('plan')}|{cache_data.get('expires_at')}|"
        f"{cache_data.get('cached_at')}"
    )
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_cache_integrity(cache_data: dict, machine_id: str) -> bool:
    """Verifica si la caché de licencia ha sido modificada manualmente o transferida de otra PC."""
    sig = cache_data.get("signature")
    if not sig:
        return False
    expected = _compute_cache_signature(cache_data, machine_id)
    return hmac.compare_digest(sig, expected)


def _verify_online_license(license_key, machine_id, force_remote=False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "SSCP-Desktop/1.0",
        "X-License-Key": DESKTOP_LICENSE_API_KEY,
    }

    # 1. Chequeo de cache local reciente con verificación de firma criptográfica HMAC
    if not force_remote and LICENSE_CACHE_FILE.exists():
        try:
            cache = json.loads(LICENSE_CACHE_FILE.read_text(encoding="utf-8"))
            if _verify_cache_integrity(cache, machine_id):
                cached_at = datetime.fromisoformat(cache.get("cached_at", ""))
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                elapsed_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600.0

                if (elapsed_hours < 4.0 and cache.get("valid") and
                    cache.get("machine_id") == machine_id and cache.get("license_token") == license_key):
                    expires_str = cache.get("expires_at")
                    expires_at = datetime.fromisoformat(expires_str) if expires_str else None
                    days_remaining = 99999
                    if expires_at:
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        days_remaining = max(0, (expires_at - datetime.now(timezone.utc)).days)
                        if days_remaining < 0:
                            return LicenseInfo(LicenseStatus.EXPIRED, machine_id=machine_id)
                    return LicenseInfo(LicenseStatus.ACTIVE, machine_id=machine_id,
                                       doctor_name=cache.get("doctor_name", "Doctor"),
                                       plan=cache.get("plan", "Standard"),
                                       expires_at=expires_at, mode="online_cached",
                                       days_remaining=days_remaining)
        except Exception:
            pass

    # 2. Consulta al servidor remoto
    try:
        response = httpx.post(
            f"{LICENSE_SERVER_URL}/verify",
            json={
                "machine_id": machine_id,
                "license_token": license_key,
                "device_name": platform.node(),
                "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
            },
            headers=headers,
            timeout=8.0,
            verify=True,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("valid"):
                expires_str = data.get("expires_at")
                expires_at = datetime.fromisoformat(expires_str) if expires_str else None
                days_remaining = 99999
                if expires_at:
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    days_remaining = max(0, (expires_at - datetime.now(timezone.utc)).days)
                result = LicenseInfo(LicenseStatus.ACTIVE, machine_id=machine_id,
                                     doctor_name=data.get("doctor_name", "Doctor"),
                                     plan=data.get("plan", "Standard"),
                                     expires_at=expires_at, mode="online",
                                     days_remaining=days_remaining)
                cache = {
                    "valid": True,
                    "machine_id": machine_id,
                    "license_token": license_key,
                    "doctor_name": result.doctor_name,
                    "plan": result.plan,
                    "expires_at": expires_str,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                }
                cache["signature"] = _compute_cache_signature(cache, machine_id)
                LICENSE_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
                return result
            else:
                reason = data.get("reason", "")
                if reason == "expired":
                    return LicenseInfo(LicenseStatus.EXPIRED, machine_id=machine_id)
                elif reason == "device_limit_reached":
                    return LicenseInfo(LicenseStatus.MACHINE_MISMATCH, machine_id=machine_id)
                return LicenseInfo(LicenseStatus.UNLICENSED, machine_id=machine_id)
    except Exception:
        pass

    # 3. Periodo de gracia offline (7 dias) si el servidor no responde (requiere HMAC válido)
    if LICENSE_CACHE_FILE.exists():
        try:
            cache = json.loads(LICENSE_CACHE_FILE.read_text(encoding="utf-8"))
            if _verify_cache_integrity(cache, machine_id):
                cached_at = datetime.fromisoformat(cache.get("cached_at", ""))
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - cached_at).days
                if (age_days <= CACHE_TTL_DAYS and cache.get("valid") and
                    cache.get("machine_id") == machine_id and cache.get("license_token") == license_key):
                    expires_str = cache.get("expires_at")
                    expires_at = datetime.fromisoformat(expires_str) if expires_str else None
                    days_remaining = 99999
                    if expires_at:
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        days_remaining = max(0, (expires_at - datetime.now(timezone.utc)).days)
                        if days_remaining < 0:
                            return LicenseInfo(LicenseStatus.EXPIRED, machine_id=machine_id)
                    return LicenseInfo(LicenseStatus.ACTIVE, machine_id=machine_id,
                                       doctor_name=cache.get("doctor_name", "Doctor"),
                                       plan=cache.get("plan", "Standard"),
                                       expires_at=expires_at, mode="online_grace",
                                       days_remaining=days_remaining)
        except Exception:
            pass
    return LicenseInfo(LicenseStatus.SERVER_UNREACHABLE, machine_id=machine_id)


def get_license_mode():
    if LICENSE_MODE_FILE.exists():
        return LICENSE_MODE_FILE.read_text(encoding="utf-8").strip().lower()
    return "offline"



_last_heartbeat_timestamp = 0.0
_HEARTBEAT_INTERVAL_SECONDS = 3600  # Máximo 1 reporte cada hora para no saturar


def _send_telemetry_ping(license_key: str, machine_id: str):
    """Reporte de telemetría en segundo plano. Nunca lanza excepciones ni bloquea la app."""
    try:
        device_name = platform.node() or "PC-SSCP"
        os_platform = f"{platform.system()} {platform.release()} ({platform.machine()})"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SSCP-Desktop/1.0",
            "X-License-Key": DESKTOP_LICENSE_API_KEY,
        }
        payload = {
            "machine_id": machine_id,
            "license_token": license_key,
            "device_name": device_name,
            "platform": os_platform,
        }
        with httpx.Client(timeout=5.0) as client:
            client.post(f"{LICENSE_SERVER_URL}/verify", json=payload, headers=headers)
    except Exception:
        # Falla silenciosa esperada cuando la máquina no tiene acceso a internet
        pass


def _trigger_background_heartbeat(license_key: str, machine_id: str, force: bool = False):
    global _last_heartbeat_timestamp
    now_ts = time.time()
    if force or (now_ts - _last_heartbeat_timestamp >= _HEARTBEAT_INTERVAL_SECONDS):
        _last_heartbeat_timestamp = now_ts
        thread = threading.Thread(
            target=_send_telemetry_ping,
            args=(license_key, machine_id),
            daemon=True,
            name="SSCP-Telemetry",
        )
        thread.start()


def check_license():
    machine_id = get_machine_id()
    from app.database import SessionLocal
    from app.models.license_config import LicenseConfig
    try:
        with SessionLocal() as db:
            config = db.query(LicenseConfig).first()
            if not config or not config.license_key:
                return LicenseInfo(LicenseStatus.UNLICENSED, machine_id=machine_id)
            mode = config.mode or get_license_mode()
            if mode == "online":
                return _verify_online_license(config.license_key, machine_id)
            info = _verify_offline_license(config.license_key, machine_id)
            if info.status == LicenseStatus.ACTIVE:
                _trigger_background_heartbeat(config.license_key, machine_id)
            return info
    except Exception:
        return LicenseInfo(LicenseStatus.UNLICENSED, machine_id=machine_id)


def activate(license_key, mode="offline"):
    machine_id = get_machine_id()
    license_key = (license_key or "").strip()
    if not license_key:
        return LicenseInfo(LicenseStatus.UNLICENSED, machine_id=machine_id)
    if mode == "online":
        info = _verify_online_license(license_key, machine_id, force_remote=True)
    else:
        info = _verify_offline_license(license_key, machine_id)
    if info.status == LicenseStatus.ACTIVE:
        from app.database import SessionLocal
        from app.models.license_config import LicenseConfig
        with SessionLocal() as db:
            config = db.query(LicenseConfig).first()
            if not config:
                config = LicenseConfig()
                db.add(config)
            config.mode = mode
            config.license_key = license_key
            config.machine_id = machine_id
            config.doctor_name = info.doctor_name
            config.plan = info.plan
            config.expires_at = info.expires_at
            config.activated_at = datetime.now(timezone.utc)
            config.last_verified_at = datetime.now(timezone.utc)
            db.commit()
        # Disparar telemetría silenciosa inmediatamente en segundo plano
        _trigger_background_heartbeat(license_key, machine_id, force=True)
    return info
