import hashlib
import json
import logging
import os
import re
import secrets
import socket
import sys
import threading
import time as pytime
import uuid
from datetime import datetime, date, time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, DATA_DIR, APP_DIR, DB_PATH, Base, engine
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.service import Service
from app.models.setting import Setting
from app.models.user import User

logger = logging.getLogger("uvicorn.error")

DEFAULT_SUPABASE_URL = ""
DEFAULT_SUPABASE_ANON_KEY = ""
KEEPALIVE_HUB_URL = "https://sscp.laxarusdevs.com/api/supabase-keepalive/register"

_SYNC_LOCK = threading.Lock()
_SYNC_WAKE_EVENT = threading.Event()
_HTTP_SESSION: Optional[requests.Session] = None
_LAST_HEARTBEAT_TS: float = 0.0
_LAST_KEEPALIVE_TS: float = 0.0
_LAST_UPSERT_ERROR: Optional[str] = None


def _get_http_session() -> requests.Session:
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = requests.Session()
    return _HTTP_SESSION


def signal_supabase_sync() -> None:
    """Despierta el hilo de sincronizacion para empujar cambios locales de inmediato."""
    _SYNC_WAKE_EVENT.set()


def wait_for_sync_signal(timeout_seconds: float = 20.0) -> None:
    _SYNC_WAKE_EVENT.wait(timeout=timeout_seconds)
    _SYNC_WAKE_EVENT.clear()


def hash_station_secret(secret: str) -> str:
    return hashlib.sha256((secret or "").strip().encode("utf-8")).hexdigest()


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _to_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _detect_network_endpoints() -> Tuple[Optional[str], Optional[str]]:
    port = os.environ.get("SSCP_ACTIVE_PORT", "8080").strip() or "8080"
    local_ip = None
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = None
    finally:
        s.close()

    tailscale_ip = None
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ip.startswith("100.") and not ip.endswith(".0") and not ip.endswith(".255"):
                tailscale_ip = ip
                break
    except Exception:
        tailscale_ip = None

    local_url = f"http://{local_ip}:{port}" if local_ip and local_ip != "127.0.0.1" else None
    tailscale_url = f"http://{tailscale_ip}:{port}" if tailscale_ip else None
    return local_url, tailscale_url


class SupabaseSyncService:
    """Puente incremental bidireccional entre SQLite local y Supabase PostgreSQL."""

    _ENSURED_ENGINES: set = set()

    @classmethod
    def ensure_sync_tables(cls, db: Session) -> None:
        bind_key = id(db.get_bind()) if hasattr(db, "get_bind") else None
        if bind_key and bind_key in cls._ENSURED_ENGINES:
            try:
                db.execute(text("SELECT 1 FROM mobile_sync_keys LIMIT 1"))
                return
            except Exception:
                cls._ENSURED_ENGINES.discard(bind_key)

        db.execute(text("""
            CREATE TABLE IF NOT EXISTS mobile_sync_keys (
                client_uuid TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                row_hash TEXT
            )
        """))
        cols = [r[1] for r in db.execute(text("PRAGMA table_info(mobile_sync_keys)")).fetchall()]
        if "row_hash" not in cols:
            db.execute(text("ALTER TABLE mobile_sync_keys ADD COLUMN row_hash TEXT"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_mobile_sync_keys_ent ON mobile_sync_keys (entity_type, entity_id)"
        ))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS supabase_sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            )
        """))
        db.commit()
        if bind_key:
            cls._ENSURED_ENGINES.add(bind_key)

    @classmethod
    def get_meta(cls, db: Session, key: str) -> Optional[str]:
        cls.ensure_sync_tables(db)
        row = db.execute(
            text("SELECT value FROM supabase_sync_meta WHERE key = :k"),
            {"k": key},
        ).fetchone()
        return row[0] if row else None

    @classmethod
    def set_meta(cls, db: Session, key: str, value: str) -> None:
        cls.ensure_sync_tables(db)
        db.execute(
            text("""
                INSERT OR REPLACE INTO supabase_sync_meta (key, value, updated_at)
                VALUES (:k, :v, :u)
            """),
            {"k": key, "v": value, "u": datetime.utcnow().isoformat()},
        )
        db.commit()

    @classmethod
    def _preset_file_candidates(cls) -> List[Path]:
        cands = [
            DATA_DIR / "supabase_preset.json",
            APP_DIR / "data" / "supabase_preset.json",
        ]
        if os.environ.get("APPDATA"):
            cands.append(Path(os.environ["APPDATA"]) / "SSCP Desktop" / "data" / "supabase_preset.json")
        if os.environ.get("LOCALAPPDATA"):
            cands.append(Path(os.environ["LOCALAPPDATA"]) / "SSCP" / "data" / "supabase_preset.json")
        return cands

    @classmethod
    def load_preset(cls) -> Optional[Dict[str, Any]]:
        for candidate in cls._preset_file_candidates():
            if candidate.exists():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("supabase_url") and data.get("supabase_anon_key"):
                        return data
                except Exception:
                    pass
        return None

    @classmethod
    def save_preset(cls, data: Dict[str, Any]) -> None:
        raw_secret = str(data.get("station_secret") or "").strip()
        sec_hash = str(data.get("secret_hash") or "").strip() or (hash_station_secret(raw_secret) if raw_secret else "")
        safe = {
            "clinic_id": str(data.get("clinic_id") or "").strip(),
            "supabase_url": str(data.get("supabase_url") or "").strip().rstrip("/"),
            "supabase_anon_key": str(data.get("supabase_anon_key") or "").strip(),
            "secret_hash": sec_hash,
            "doctor_name": str(data.get("doctor_name") or "").strip(),
        }
        if data.get("include_secret_once") and raw_secret:
            safe["station_secret"] = raw_secret
        if not (safe["supabase_url"] and safe["supabase_anon_key"]):
            return
        try:
            target = DATA_DIR / "supabase_preset.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def _scrub_preset_secret(cls) -> None:
        """Elimina station_secret en claro de supabase_preset.json una vez guardado en SQLite settings."""
        for candidate in cls._preset_file_candidates():
            if candidate.exists():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("station_secret"):
                        sec = str(data.pop("station_secret") or "").strip()
                        if sec and not data.get("secret_hash"):
                            data["secret_hash"] = hash_station_secret(sec)
                        candidate.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass

    @classmethod
    def get_bridge_config(cls, db: Session) -> Dict[str, Any]:
        from app.services.relay_service import RelayService

        setting = db.query(Setting).first()
        if not setting:
            return {"enabled": False}

        dirty = False
        preset = cls.load_preset()
        if preset and (not getattr(setting, "supabase_url", None) or not getattr(setting, "supabase_anon_key", None)):
            setting.supabase_url = preset["supabase_url"]
            setting.supabase_anon_key = preset["supabase_anon_key"]
            if preset.get("station_secret") and not getattr(setting, "station_secret", None):
                setting.station_secret = preset["station_secret"]
            if preset.get("clinic_id"):
                setting.relay_channel_id = preset["clinic_id"]
            dirty = True

        if not getattr(setting, "station_secret", None) or not setting.station_secret.strip():
            setting.station_secret = f"sscp_{secrets.token_urlsafe(18)}"
            dirty = True

        supabase_url = (
            os.environ.get("SSCP_SUPABASE_URL")
            or getattr(setting, "supabase_url", None)
            or DEFAULT_SUPABASE_URL
        ).strip().rstrip("/")
        supabase_anon_key = (
            os.environ.get("SSCP_SUPABASE_ANON_KEY")
            or getattr(setting, "supabase_anon_key", None)
            or DEFAULT_SUPABASE_ANON_KEY
        ).strip()

        if getattr(setting, "supabase_url", None) != supabase_url:
            setting.supabase_url = supabase_url
            dirty = True
        if getattr(setting, "supabase_anon_key", None) != supabase_anon_key:
            setting.supabase_anon_key = supabase_anon_key
            dirty = True

        clinic_id = RelayService.get_clinic_id(db)
        if not getattr(setting, "relay_channel_id", None) or setting.relay_channel_id.strip() != clinic_id:
            setting.relay_channel_id = clinic_id
            dirty = True

        if dirty:
            db.commit()
            db.refresh(setting)
        if preset and preset.get("station_secret") and getattr(setting, "station_secret", None):
            demo_emails = ("admin@sscp.com", "doctor@sscp.com", "secretaria@sscp.com")
            has_custom_user = db.query(User.id).filter(~User.email.in_(demo_emails)).first() is not None
            if has_custom_user:
                cls._scrub_preset_secret()

        if not supabase_url or not supabase_anon_key:
            return {
                "enabled": False,
                "clinic_id": clinic_id,
                "station_secret": setting.station_secret,
                "secret_hash": hash_station_secret(setting.station_secret),
                "supabase_url": supabase_url or "",
                "supabase_anon_key": supabase_anon_key or "",
                "doctor_name": setting.doctor_name or "Médico Especialista",
                "clinic_name": setting.clinic_name or "Centro Médico SSCP",
                "specialty": setting.specialty or "Medicina General",
                "sede_name": setting.sede_name or "Sede Central",
            }

        return {
            "enabled": True,
            "supabase_url": supabase_url,
            "supabase_anon_key": supabase_anon_key,
            "clinic_id": clinic_id,
            "station_secret": setting.station_secret,
            "secret_hash": hash_station_secret(setting.station_secret),
            "doctor_name": setting.doctor_name or "Médico Especialista",
            "clinic_name": setting.clinic_name or "Centro Médico SSCP",
            "specialty": setting.specialty or "Medicina General",
            "sede_name": setting.sede_name or "Sede Central",
        }

    @classmethod
    def get_last_error(cls) -> Optional[str]:
        return _LAST_UPSERT_ERROR

    @classmethod
    def _rpc_post(
        cls,
        cfg: Dict[str, Any],
        fn_name: str,
        payload: Dict[str, Any],
        timeout: float = 12.0,
    ) -> Optional[Any]:
        global _LAST_UPSERT_ERROR
        url = f"{cfg['supabase_url']}/rest/v1/rpc/{fn_name}"
        headers = {
            "apikey": cfg["supabase_anon_key"],
            "Authorization": f"Bearer {cfg['supabase_anon_key']}",
            "Content-Type": "application/json",
            "User-Agent": "SSCP-Desktop-Supabase/1.0",
        }
        try:
            res = _get_http_session().post(url, json=payload, headers=headers, timeout=timeout)
            if res.status_code >= 400:
                body_txt = (res.text or "")[:260]
                if "unauthorized_clinic_station" in body_txt:
                    _LAST_UPSERT_ERROR = "unauthorized_clinic_station"
                logger.warning(f"[SupabaseSync] RPC {fn_name} HTTP {res.status_code}: {body_txt[:220]}")
                return None
            if fn_name == "sscp_upsert_station":
                _LAST_UPSERT_ERROR = None
            return res.json() if res.text else {}
        except Exception as exc:
            logger.warning(f"[SupabaseSync] RPC {fn_name} error: {exc}")
            return None

    @classmethod
    def get_or_assign_uuid(cls, db: Session, entity_type: str, entity_id: int) -> str:
        cls.ensure_sync_tables(db)
        row = db.execute(
            text("SELECT client_uuid FROM mobile_sync_keys WHERE entity_type = :et AND entity_id = :eid"),
            {"et": entity_type, "eid": int(entity_id)},
        ).fetchone()
        if row and row[0]:
            return str(row[0])
        new_uuid = f"pc-{entity_type[:3]}-{uuid.uuid4().hex[:16]}"
        db.execute(
            text("""
                INSERT OR REPLACE INTO mobile_sync_keys (client_uuid, entity_type, entity_id, created_at)
                VALUES (:cu, :et, :eid, :ca)
            """),
            {"cu": new_uuid, "et": entity_type, "eid": int(entity_id), "ca": datetime.utcnow().isoformat()},
        )
        return new_uuid

    @classmethod
    def link_uuid(cls, db: Session, client_uuid: str, entity_type: str, entity_id: int) -> None:
        if not client_uuid or not entity_id:
            return
        cls.ensure_sync_tables(db)
        db.execute(
            text("""
                INSERT OR REPLACE INTO mobile_sync_keys (client_uuid, entity_type, entity_id, created_at)
                VALUES (:cu, :et, :eid, :ca)
            """),
            {"cu": str(client_uuid).strip(), "et": entity_type, "eid": int(entity_id), "ca": datetime.utcnow().isoformat()},
        )

    @classmethod
    def find_entity_id(cls, db: Session, entity_type: str, client_uuid: Optional[str]) -> Optional[int]:
        if not client_uuid or not str(client_uuid).strip():
            return None
        cls.ensure_sync_tables(db)
        row = db.execute(
            text("SELECT entity_id FROM mobile_sync_keys WHERE client_uuid = :cu AND entity_type = :et"),
            {"cu": str(client_uuid).strip(), "et": entity_type},
        ).fetchone()
        return int(row[0]) if row else None

    @classmethod
    def _resolve_station_doctor_id(cls, db: Session, setting: Optional[Setting]) -> int:
        doc = None
        if setting and setting.doctor_name:
            clean = setting.doctor_name.replace("Dr. ", "").replace("Dra. ", "").strip()
            if clean:
                doc = db.query(User).filter(User.name.ilike(f"%{clean}%"), User.role == "doctor").first()
        if not doc:
            doc = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        if not doc:
            doc = db.query(User).filter(User.is_active == True).first()
        return doc.id if doc else 1

    @classmethod
    def _collect_mobile_users(cls, db: Optional[Session]) -> List[Dict[str, Any]]:
        own_db = db is None
        sess = db or SessionLocal()
        try:
            users = sess.query(User).filter(User.is_active == True).all()
            return [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": (u.email or "").strip().lower(),
                    "role": u.role,
                    "assigned_doctor_id": getattr(u, "assigned_doctor_id", None),
                    "is_active": bool(u.is_active),
                    "password_hash": u.hashed_password or "",
                }
                for u in users
                if (u.email or "").strip() and (u.hashed_password or "").strip()
            ]
        except Exception:
            return []
        finally:
            if own_db:
                sess.close()

    @classmethod
    def upsert_station(cls, cfg: Dict[str, Any], force: bool = False, db: Optional[Session] = None) -> bool:
        global _LAST_HEARTBEAT_TS
        import time as pytime
        from app.version import SUITE_VERSION

        now_ts = pytime.time()
        if not force and (now_ts - _LAST_HEARTBEAT_TS) < 45.0:
            return True

        local_url, tailscale_url = _detect_network_endpoints()
        mobile_users = cls._collect_mobile_users(db)
        res = cls._rpc_post(
            cfg,
            "sscp_upsert_station",
            {
                "p_clinic_id": cfg["clinic_id"],
                "p_secret_hash": cfg["secret_hash"],
                "p_doctor_name": cfg["doctor_name"],
                "p_clinic_name": cfg["clinic_name"],
                "p_specialty": cfg["specialty"],
                "p_sede_name": cfg["sede_name"],
                "p_local_url": local_url,
                "p_tailscale_url": tailscale_url,
                "p_app_version": SUITE_VERSION,
                "p_mobile_users": mobile_users,
            },
            timeout=6.0,
        )
        if res and res.get("ok"):
            _LAST_HEARTBEAT_TS = now_ts
            return True
        return False

    @classmethod
    def _reconcile_services(cls, db: Session, rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            cu = row.get("client_uuid")
            if not cu:
                continue
            eid = cls.find_entity_id(db, "service", cu)
            svc = db.query(Service).filter(Service.id == eid).first() if eid else None
            if not svc and row.get("name"):
                svc = db.query(Service).filter(Service.name.ilike(row["name"].strip())).first()
            if svc:
                svc.name = row.get("name") or svc.name
                svc.price = float(row.get("price") or svc.price or 0.0)
                svc.category = row.get("category") or svc.category
                svc.color = row.get("color") or svc.color
                svc.is_active = bool(row.get("is_active", True))
                cls.link_uuid(db, cu, "service", svc.id)
            else:
                svc = Service(
                    name=row.get("name") or "Consulta General",
                    price=float(row.get("price") or 0.0),
                    category=row.get("category") or "Consulta",
                    color=row.get("color") or "#3b82f6",
                    is_active=bool(row.get("is_active", True)),
                )
                db.add(svc)
                db.flush()
                cls.link_uuid(db, cu, "service", svc.id)

    @staticmethod
    def _safe_int(val: Any) -> Optional[int]:
        if val is None or isinstance(val, bool):
            return None
        try:
            return int(str(val).strip())
        except (ValueError, TypeError):
            return None

    @classmethod
    def _resolve_valid_doctor_id(cls, db: Session, raw_doc_id: Any, default_doc_id: int) -> int:
        did = cls._safe_int(raw_doc_id)
        if did and db.query(User.id).filter(User.id == did).first():
            return did
        return default_doc_id

    @classmethod
    def _resolve_valid_service_id(cls, db: Session, row: Dict[str, Any]) -> Optional[int]:
        sid = cls.find_entity_id(db, "service", row.get("service_uuid")) or cls._safe_int(row.get("service_id"))
        if sid and db.query(Service.id).filter(Service.id == sid).first():
            return sid
        sname = (row.get("service_name") or "").strip()
        if sname:
            svc = db.query(Service.id).filter(Service.name.ilike(sname)).first()
            if svc:
                return svc[0]
        return None

    @classmethod
    def _resolve_valid_appointment_id(cls, db: Session, row: Dict[str, Any]) -> Optional[int]:
        aid = cls.find_entity_id(db, "appointment", row.get("appointment_uuid")) or cls._safe_int(row.get("appointment_local_id"))
        if aid and db.query(Appointment.id).filter(Appointment.id == aid).first():
            return aid
        return None

    @classmethod
    def _reconcile_patients(cls, db: Session, rows: List[Dict[str, Any]], default_doc_id: int) -> None:
        for row in rows:
            cu = row.get("client_uuid")
            if not cu:
                continue
            eid = cls.find_entity_id(db, "patient", cu)
            pat = db.query(Patient).filter(Patient.id == eid).first() if eid else None

            doc_id_str = (row.get("document_id") or "").strip() or None
            if not pat and doc_id_str:
                pat = db.query(Patient).filter(Patient.document_id == doc_id_str).first()

            fn = (row.get("first_name") or "").strip() or "Paciente"
            ln = (row.get("last_name") or "").strip()
            phone = (row.get("phone") or "").strip() or None
            if not pat and phone:
                pat = db.query(Patient).filter(
                    Patient.first_name.ilike(fn),
                    Patient.last_name.ilike(ln),
                    Patient.phone == phone,
                ).first()

            dob_val = None
            if row.get("date_of_birth"):
                try:
                    dob_val = datetime.strptime(str(row["date_of_birth"])[:10], "%Y-%m-%d").date()
                except Exception:
                    dob_val = None

            if not pat and dob_val:
                pat = db.query(Patient).filter(
                    Patient.first_name.ilike(fn),
                    Patient.last_name.ilike(ln),
                    Patient.date_of_birth == dob_val,
                ).first()

            if pat:
                pat.first_name = fn
                pat.last_name = ln
                if doc_id_str:
                    pat.document_id = doc_id_str
                if dob_val is not None:
                    pat.date_of_birth = dob_val
                if row.get("gender"):
                    pat.gender = row["gender"]
                if phone is not None:
                    pat.phone = phone
                if row.get("email"):
                    pat.email = row["email"]
                if row.get("address"):
                    pat.address = row["address"]
                if row.get("blood_type"):
                    pat.blood_type = row["blood_type"]
                if row.get("allergies"):
                    pat.allergies = row["allergies"]
                if row.get("insurance_name"):
                    pat.insurance_name = row["insurance_name"]
                if row.get("insurance_number") is not None:
                    pat.insurance_number = row["insurance_number"]
                if row.get("emergency_contact_name"):
                    pat.emergency_contact_name = row["emergency_contact_name"]
                if row.get("emergency_contact_phone"):
                    pat.emergency_contact_phone = row["emergency_contact_phone"]
                pat.is_active = bool(row.get("is_active", True))
                pat.updated_at = datetime.utcnow()
                cls.link_uuid(db, cu, "patient", pat.id)
            else:
                pat = Patient(
                    doctor_id=cls._resolve_valid_doctor_id(db, row.get("doctor_id"), default_doc_id),
                    first_name=fn,
                    last_name=ln,
                    document_id=doc_id_str,
                    date_of_birth=dob_val,
                    gender=row.get("gender"),
                    phone=phone,
                    email=row.get("email"),
                    address=row.get("address"),
                    blood_type=row.get("blood_type"),
                    allergies=row.get("allergies"),
                    insurance_name=row.get("insurance_name") or "Privado / Particular",
                    insurance_number=row.get("insurance_number"),
                    emergency_contact_name=row.get("emergency_contact_name"),
                    emergency_contact_phone=row.get("emergency_contact_phone"),
                    is_active=bool(row.get("is_active", True)),
                    sede_origen=row.get("sede_origen") or "supabase_bridge",
                )
                db.add(pat)
                db.flush()
                cls.link_uuid(db, cu, "patient", pat.id)

    @classmethod
    def _resolve_patient_id_for_row(cls, db: Session, row: Dict[str, Any]) -> Optional[int]:
        p_uuid = row.get("patient_uuid")
        if p_uuid:
            pid = cls.find_entity_id(db, "patient", p_uuid)
            if pid:
                return pid
        p_lid = cls._safe_int(row.get("patient_local_id"))
        if p_lid:
            pat = db.query(Patient).filter(Patient.id == p_lid).first()
            if pat:
                return pat.id
        return None

    @classmethod
    def _parse_hhmm(cls, raw: Optional[str]) -> Optional[time]:
        if not raw or ":" not in str(raw):
            return None
        try:
            parts = str(raw).strip().split(":")
            return time(int(parts[0]), int(parts[1]))
        except Exception:
            return None

    @classmethod
    def _reconcile_appointments(cls, db: Session, rows: List[Dict[str, Any]], default_doc_id: int) -> None:
        from app.routers.appointments import assign_next_queue_number, find_same_day_appointment

        for row in rows:
            cu = row.get("client_uuid")
            if not cu:
                continue

            eid = cls.find_entity_id(db, "appointment", cu)
            appt = db.query(Appointment).filter(Appointment.id == eid).first() if eid else None

            pid = cls._resolve_patient_id_for_row(db, row)
            if not appt and not pid:
                continue

            try:
                appt_date = datetime.strptime(str(row.get("date"))[:10], "%Y-%m-%d").date()
            except Exception:
                appt_date = date.today()

            st_t = cls._parse_hhmm(row.get("start_time")) or time(9, 0)
            end_t = cls._parse_hhmm(row.get("end_time")) or time((st_t.hour + 1) % 24, st_t.minute)
            target_status = row.get("status") or "Pendiente"
            svc_id = cls._resolve_valid_service_id(db, row)
            remote_wa_sent = bool(row.get("whatsapp_reminder_sent"))
            remote_wa_at = _parse_iso_dt(row.get("whatsapp_reminder_sent_at"))

            from app.services.appointment_reconciliation import (
                compute_monotonic_sync_utc,
                has_consultation_for_appointment,
                is_active_appointment_status,
                is_completed_appointment_status,
            )

            if appt:
                locally_completed = is_completed_appointment_status(appt.status) or has_consultation_for_appointment(db, appt)
                if locally_completed and is_active_appointment_status(target_status):
                    appt.status = "Completada"
                    appt.updated_at = compute_monotonic_sync_utc(db)
                else:
                    appt.status = target_status
                    appt.updated_at = datetime.utcnow()
                appt.date = appt_date
                appt.start_time = st_t
                appt.end_time = end_t
                appt.reason = row.get("reason") or appt.reason
                if row.get("queue_number") is not None:
                    appt.queue_number = row.get("queue_number")
                if svc_id is not None:
                    appt.service_id = svc_id
                appt.price = float(row.get("price") or appt.price or 0.0)
                if row.get("notes") is not None:
                    appt.notes = row["notes"]
                if remote_wa_sent and not appt.whatsapp_reminder_sent:
                    appt.whatsapp_reminder_sent = True
                if remote_wa_at and not appt.whatsapp_reminder_sent_at:
                    appt.whatsapp_reminder_sent_at = remote_wa_at
                cls.link_uuid(db, cu, "appointment", appt.id)
                continue

            # Conciliar si ya existe cita activa el mismo dia para el mismo paciente
            existing_same_day = find_same_day_appointment(db, pid, appt_date)
            if existing_same_day:
                if (
                    is_completed_appointment_status(target_status)
                    and not is_completed_appointment_status(existing_same_day.status)
                ):
                    existing_same_day.status = "Completada"
                    existing_same_day.updated_at = compute_monotonic_sync_utc(db)
                if remote_wa_sent and not existing_same_day.whatsapp_reminder_sent:
                    existing_same_day.whatsapp_reminder_sent = True
                if remote_wa_at and not existing_same_day.whatsapp_reminder_sent_at:
                    existing_same_day.whatsapp_reminder_sent_at = remote_wa_at
                cls.link_uuid(db, cu, "appointment", existing_same_day.id)
                continue

            q_num = row.get("queue_number")
            if target_status == "En Espera" and not q_num:
                q_num = assign_next_queue_number(db, appt_date)

            appt = Appointment(
                patient_id=pid,
                doctor_id=cls._resolve_valid_doctor_id(db, row.get("doctor_id"), default_doc_id),
                date=appt_date,
                start_time=st_t,
                end_time=end_t,
                reason=row.get("reason") or "Consulta Médica",
                status=target_status,
                queue_number=q_num,
                service_id=svc_id,
                price=float(row.get("price") or 0.0),
                notes=row.get("notes"),
                whatsapp_reminder_sent=remote_wa_sent,
                whatsapp_reminder_sent_at=remote_wa_at,
                sede_origen="supabase_bridge",
            )
            db.add(appt)
            db.flush()
            cls.link_uuid(db, cu, "appointment", appt.id)

    @classmethod
    def _reconcile_consultations(cls, db: Session, rows: List[Dict[str, Any]], default_doc_id: int) -> None:
        for row in rows:
            cu = row.get("client_uuid")
            if not cu:
                continue

            eid = cls.find_entity_id(db, "consultation", cu)
            cons = db.query(Consultation).filter(Consultation.id == eid).first() if eid else None

            pid = cls._resolve_patient_id_for_row(db, row)
            if not cons and not pid:
                continue

            appt_id = cls._resolve_valid_appointment_id(db, row)
            if cons:
                cons.reason = row.get("reason") or cons.reason
                cons.clinical_history = row.get("clinical_history") or cons.clinical_history
                cons.symptoms = row.get("symptoms") or cons.symptoms
                cons.physical_exam = row.get("physical_exam") or cons.physical_exam
                cons.diagnosis = row.get("diagnosis") or cons.diagnosis
                cons.treatment = row.get("treatment") or cons.treatment
                cons.prescription = row.get("prescription") or cons.prescription
                cons.notes = row.get("notes") or cons.notes
                cons.edit_version = max(cls._safe_int(row.get("edit_version")) or 1, cons.edit_version or 1)
                cons.updated_at = datetime.utcnow()
                cls.link_uuid(db, cu, "consultation", cons.id)
            else:
                created_dt = _parse_iso_dt(row.get("created_at_iso")) or datetime.utcnow()
                cons = Consultation(
                    patient_id=pid,
                    doctor_id=cls._resolve_valid_doctor_id(db, row.get("doctor_id"), default_doc_id),
                    appointment_id=appt_id,
                    reason=row.get("reason") or "Consulta médica",
                    clinical_history=row.get("clinical_history"),
                    symptoms=row.get("symptoms"),
                    physical_exam=row.get("physical_exam"),
                    diagnosis=row.get("diagnosis"),
                    treatment=row.get("treatment"),
                    prescription=row.get("prescription"),
                    notes=row.get("notes"),
                    is_first_visit=bool(row.get("is_first_visit", False)),
                    edit_version=cls._safe_int(row.get("edit_version")) or 1,
                    created_at=created_dt,
                    sede_origen="supabase_bridge",
                )
                db.add(cons)
                db.flush()
                cls.link_uuid(db, cu, "consultation", cons.id)

            from app.services.appointment_reconciliation import reconcile_completed_appointments
            reconcile_completed_appointments(
                db,
                patient_id=cons.patient_id,
                appointment_id=cons.appointment_id,
                consultation=cons,
            )

    @classmethod
    def _reconcile_payments(cls, db: Session, rows: List[Dict[str, Any]], default_doc_id: int) -> None:
        for row in rows:
            cu = row.get("client_uuid")
            if not cu:
                continue

            eid = cls.find_entity_id(db, "payment", cu)
            pay = db.query(Payment).filter(Payment.id == eid).first() if eid else None

            pid = cls._resolve_patient_id_for_row(db, row)
            if not pay and not pid:
                continue

            appt_id = cls._resolve_valid_appointment_id(db, row)
            svc_id = cls._resolve_valid_service_id(db, row)
            if pay:
                pay.service_name = row.get("service_name") or pay.service_name
                if svc_id is not None:
                    pay.service_id = svc_id
                pay.amount = float(row.get("amount") or pay.amount or 0.0)
                pay.discount = float(row.get("discount") or pay.discount or 0.0)
                pay.total = float(row.get("total") or pay.total or 0.0)
                pay.status = row.get("status") or pay.status
                pay.payment_method = row.get("payment_method") or pay.payment_method
                pay.insurance_name = row.get("insurance_name") or pay.insurance_name
                if row.get("notes") is not None:
                    pay.notes = row["notes"]
                pay.updated_at = datetime.utcnow()
                cls.link_uuid(db, cu, "payment", pay.id)
            else:
                receipt = row.get("receipt_number") or f"REC-SB-{uuid.uuid4().hex[:6].upper()}"
                created_dt = _parse_iso_dt(row.get("created_at_iso")) or datetime.utcnow()
                pay = Payment(
                    patient_id=pid,
                    appointment_id=appt_id,
                    service_id=svc_id,
                    service_name=row.get("service_name") or "Consulta Médica General",
                    amount=float(row.get("amount") or 0.0),
                    discount=float(row.get("discount") or 0.0),
                    total=float(row.get("total") or row.get("amount") or 0.0),
                    status=row.get("status") or "paid",
                    payment_method=row.get("payment_method") or "cash",
                    insurance_name=row.get("insurance_name") or "Privado / Particular",
                    receipt_number=receipt,
                    notes=row.get("notes"),
                    created_by_id=cls._resolve_valid_doctor_id(db, row.get("doctor_id"), default_doc_id),
                    created_at=created_dt,
                    sede_origen="supabase_bridge",
                )
                db.add(pay)
                db.flush()
                cls.link_uuid(db, cu, "payment", pay.id)

    @classmethod
    def pull_incremental(cls, cfg: Dict[str, Any], db: Session) -> bool:
        last_pull = cls.get_meta(db, "last_pull_at")
        res = cls._rpc_post(
            cfg,
            "sscp_pull_changes",
            {
                "p_clinic_id": cfg["clinic_id"],
                "p_secret_hash": cfg["secret_hash"],
                "p_since": last_pull,
            },
            timeout=15.0,
        )
        if not res or not res.get("ok"):
            return False

        setting = db.query(Setting).first()
        default_doc_id = cls._resolve_station_doctor_id(db, setting)

        # Registrar mayor timestamp remoto visto para evitar bloqueos por desfase de reloj
        candidate_ts = [res.get("server_time")]
        for coll in ("services", "patients", "appointments", "consultations", "payments"):
            for item in (res.get(coll) or []):
                if isinstance(item, dict) and item.get("updated_at"):
                    candidate_ts.append(item.get("updated_at"))
        parsed_ts = [dt for dt in (_parse_iso_dt(x) for x in candidate_ts if x) if dt is not None]
        if parsed_ts:
            max_seen = max(parsed_ts)
            prev_max = _parse_iso_dt(cls.get_meta(db, "max_remote_ts"))
            if prev_max is None or max_seen > prev_max:
                cls.set_meta(db, "max_remote_ts", max_seen.replace(tzinfo=timezone.utc).isoformat())

        cls._reconcile_services(db, res.get("services") or [])
        cls._reconcile_patients(db, res.get("patients") or [], default_doc_id)
        cls._reconcile_appointments(db, res.get("appointments") or [], default_doc_id)
        cls._reconcile_consultations(db, res.get("consultations") or [], default_doc_id)
        cls._reconcile_payments(db, res.get("payments") or [], default_doc_id)

        from app.services.appointment_reconciliation import reconcile_completed_appointments
        reconcile_completed_appointments(db)
        db.commit()

        if res.get("server_time"):
            cls.set_meta(db, "last_pull_at", str(res["server_time"]))
        return True

    @staticmethod
    def _compute_row_hash(item: Dict[str, Any]) -> str:
        comparable = {k: v for k, v in item.items() if k not in ("updated_at", "source_device")}
        raw = json.dumps(comparable, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @classmethod
    def _build_incremental_batches(cls, db: Session) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, str]]:
        cls.ensure_sync_tables(db)
        existing_rows = db.execute(
            text("SELECT entity_type, entity_id, client_uuid, row_hash FROM mobile_sync_keys")
        ).fetchall()
        uuid_map: Dict[Tuple[str, int], str] = {(r[0], int(r[1])): str(r[2]) for r in existing_rows}
        hash_map: Dict[str, Optional[str]] = {str(r[2]): r[3] for r in existing_rows}
        pending_hashes: Dict[str, str] = {}
        new_uuid_rows: List[Dict[str, Any]] = []
        now_iso_key = datetime.utcnow().isoformat()

        def get_uuid(et: str, eid: int) -> str:
            existing = uuid_map.get((et, int(eid)))
            if existing:
                return existing
            assigned = f"pc-{et[:3]}-{uuid.uuid4().hex[:16]}"
            new_uuid_rows.append({"cu": assigned, "et": et, "eid": int(eid), "ca": now_iso_key})
            uuid_map[(et, int(eid))] = assigned
            hash_map[assigned] = None
            return assigned

        def include_if_changed(target_list: List[Dict[str, Any]], item: Dict[str, Any]) -> None:
            rhash = cls._compute_row_hash(item)
            cu = item["client_uuid"]
            if hash_map.get(cu) == rhash:
                return
            target_list.append(item)
            pending_hashes[cu] = rhash

        setting = db.query(Setting).first()
        default_doc_name = setting.doctor_name if setting and setting.doctor_name else "Médico Especialista"

        patients_out: List[Dict[str, Any]] = []
        for p in db.query(Patient).all():
            cu = get_uuid("patient", p.id)
            item = {
                "client_uuid": cu,
                "local_id": p.id,
                "doctor_id": p.doctor_id,
                "first_name": p.first_name or "Paciente",
                "last_name": p.last_name or "",
                "document_id": p.document_id or "",
                "date_of_birth": str(p.date_of_birth) if p.date_of_birth else None,
                "gender": p.gender or "",
                "phone": p.phone or "",
                "email": p.email or "",
                "address": p.address or "",
                "blood_type": p.blood_type or "",
                "allergies": p.allergies or "",
                "insurance_name": p.insurance_name or "Privado / Particular",
                "insurance_number": p.insurance_number or "",
                "emergency_contact_name": p.emergency_contact_name or "",
                "emergency_contact_phone": p.emergency_contact_phone or "",
                "is_active": True if p.is_active is None else bool(p.is_active),
                "source_device": "pc_desktop",
                "updated_at": _to_iso_utc(p.updated_at or p.created_at or datetime.utcnow()),
            }
            include_if_changed(patients_out, item)

        appts_out: List[Dict[str, Any]] = []
        for a in db.query(Appointment).all():
            cu = get_uuid("appointment", a.id)
            p_uuid = uuid_map.get(("patient", int(a.patient_id))) if a.patient_id else None
            p_name = f"{a.patient.first_name} {a.patient.last_name}".strip() if a.patient else "Paciente"
            item = {
                "client_uuid": cu,
                "local_id": a.id,
                "patient_uuid": p_uuid,
                "patient_local_id": a.patient_id,
                "patient_name": p_name,
                "doctor_id": a.doctor_id,
                "date": a.date.strftime("%Y-%m-%d") if a.date else date.today().strftime("%Y-%m-%d"),
                "start_time": a.start_time.strftime("%H:%M") if a.start_time else "09:00",
                "end_time": a.end_time.strftime("%H:%M") if a.end_time else "",
                "reason": a.reason or "Consulta Médica",
                "status": a.status or "Pendiente",
                "queue_number": a.queue_number,
                "service_id": a.service_id,
                "service_name": a.service.name if a.service else (a.reason or "Consulta Médica"),
                "price": float(a.price or 0.0),
                "notes": a.notes or "",
                "whatsapp_reminder_sent": bool(a.whatsapp_reminder_sent),
                "whatsapp_reminder_sent_at": _to_iso_utc(a.whatsapp_reminder_sent_at),
                "source_device": "pc_desktop",
                "updated_at": _to_iso_utc(a.updated_at or a.created_at or datetime.utcnow()),
            }
            include_if_changed(appts_out, item)

        cons_out: List[Dict[str, Any]] = []
        for c in db.query(Consultation).all():
            cu = get_uuid("consultation", c.id)
            p_uuid = uuid_map.get(("patient", int(c.patient_id))) if c.patient_id else None
            a_uuid = uuid_map.get(("appointment", int(c.appointment_id))) if c.appointment_id else None
            item = {
                "client_uuid": cu,
                "local_id": c.id,
                "patient_uuid": p_uuid,
                "patient_local_id": c.patient_id,
                "appointment_uuid": a_uuid,
                "appointment_local_id": c.appointment_id,
                "doctor_id": c.doctor_id,
                "doctor_name": c.doctor.name if c.doctor else default_doc_name,
                "reason": c.reason or "Consulta médica",
                "clinical_history": c.clinical_history or "",
                "symptoms": c.symptoms or "",
                "physical_exam": c.physical_exam or "",
                "diagnosis": c.diagnosis or "",
                "treatment": c.treatment or "",
                "prescription": c.prescription or "",
                "notes": c.notes or "",
                "is_first_visit": bool(c.is_first_visit),
                "edit_version": int(c.edit_version or 1),
                "created_at_iso": _to_iso_utc(c.created_at),
                "source_device": "pc_desktop",
                "updated_at": _to_iso_utc(c.updated_at or c.created_at or datetime.utcnow()),
            }
            include_if_changed(cons_out, item)

        pays_out: List[Dict[str, Any]] = []
        for py in db.query(Payment).all():
            cu = get_uuid("payment", py.id)
            p_uuid = uuid_map.get(("patient", int(py.patient_id))) if py.patient_id else None
            a_uuid = uuid_map.get(("appointment", int(py.appointment_id))) if py.appointment_id else None
            item = {
                "client_uuid": cu,
                "local_id": py.id,
                "patient_uuid": p_uuid,
                "patient_local_id": py.patient_id,
                "appointment_uuid": a_uuid,
                "appointment_local_id": py.appointment_id,
                "service_id": py.service_id,
                "service_name": py.service_name or "Consulta Médica General",
                "amount": float(py.amount or 0.0),
                "discount": float(py.discount or 0.0),
                "total": float(py.total if py.total is not None else (py.amount or 0.0)),
                "status": py.status or "paid",
                "payment_method": py.payment_method or "cash",
                "insurance_name": py.insurance_name or "Privado / Particular",
                "receipt_number": py.receipt_number or f"REC-{py.id:04d}",
                "notes": py.notes or "",
                "created_at_iso": _to_iso_utc(py.created_at),
                "source_device": "pc_desktop",
                "updated_at": _to_iso_utc(py.updated_at or py.created_at or datetime.utcnow()),
            }
            include_if_changed(pays_out, item)

        svcs_out: List[Dict[str, Any]] = []
        for s in db.query(Service).all():
            cu = get_uuid("service", s.id)
            item = {
                "client_uuid": cu,
                "local_id": s.id,
                "name": s.name,
                "price": float(s.price or 0.0),
                "category": getattr(s, "category", "Consulta") or "Consulta",
                "color": getattr(s, "color", "#3b82f6") or "#3b82f6",
                "is_active": bool(s.is_active),
                "updated_at": _to_iso_utc(datetime.utcnow()),
            }
            include_if_changed(svcs_out, item)

        if new_uuid_rows:
            db.execute(
                text("""
                    INSERT OR REPLACE INTO mobile_sync_keys (client_uuid, entity_type, entity_id, created_at)
                    VALUES (:cu, :et, :eid, :ca)
                """),
                new_uuid_rows,
            )
        db.commit()
        return {
            "patients": patients_out,
            "appointments": appts_out,
            "consultations": cons_out,
            "payments": pays_out,
            "services": svcs_out,
        }, pending_hashes

    @classmethod
    def push_incremental(cls, cfg: Dict[str, Any], db: Session, chunk_size: int = 200) -> bool:
        batches, pending_hashes = cls._build_incremental_batches(db)
        total = sum(len(v) for v in batches.values())
        if total == 0:
            return True

        # Enviar en chunks ordenados: servicios y pacientes primero, luego citas, consultas y pagos
        order = ["services", "patients", "appointments", "consultations", "payments"]
        last_server_time = None
        for key in order:
            items = batches[key]
            for i in range(0, len(items), chunk_size):
                chunk = items[i : i + chunk_size]
                payload = {
                    "p_clinic_id": cfg["clinic_id"],
                    "p_secret_hash": cfg["secret_hash"],
                    "p_device_id": "pc_desktop",
                    "p_patients": chunk if key == "patients" else [],
                    "p_appointments": chunk if key == "appointments" else [],
                    "p_consultations": chunk if key == "consultations" else [],
                    "p_payments": chunk if key == "payments" else [],
                    "p_services": chunk if key == "services" else [],
                }
                res = cls._rpc_post(cfg, "sscp_push_batch", payload, timeout=20.0)
                if not res or not res.get("ok"):
                    return False
                last_server_time = res.get("server_time") or last_server_time
                for row_item in chunk:
                    cu = row_item["client_uuid"]
                    if cu in pending_hashes:
                        db.execute(
                            text("UPDATE mobile_sync_keys SET row_hash = :rh WHERE client_uuid = :cu"),
                            {"rh": pending_hashes[cu], "cu": cu},
                        )
                db.commit()

        cls.set_meta(db, "last_push_at", datetime.utcnow().replace(tzinfo=timezone.utc).isoformat())
        if last_server_time and not cls.get_meta(db, "last_pull_at"):
            cls.set_meta(db, "last_pull_at", str(last_server_time))
        return True

    @staticmethod
    def _resolve_schema_sql_path() -> Optional[Path]:
        candidates = []
        if getattr(sys, "_MEIPASS", None):
            candidates.append(Path(sys._MEIPASS) / "scripts" / "supabase_schema.sql")
        candidates.append(Path(__file__).resolve().parent.parent.parent / "scripts" / "supabase_schema.sql")
        for c in candidates:
            if c.exists():
                return c
        return None

    @classmethod
    def register_keepalive_monitor(cls, clinic_id: str, supabase_url: str, anon_key: str) -> bool:
        """Registra el proyecto Supabase del doctor solo si SSCP_ENABLE_KEEPALIVE_HUB=1 está activo explícitamente."""
        if os.environ.get("SSCP_ENABLE_KEEPALIVE_HUB", "0").strip() != "1":
            return False
        hub = os.environ.get("SSCP_KEEPALIVE_HUB_URL", KEEPALIVE_HUB_URL).strip()
        if not hub or not supabase_url or not anon_key:
            return False
        try:
            res = _get_http_session().post(
                hub,
                json={
                    "clinic_id": clinic_id,
                    "supabase_url": supabase_url.strip().rstrip("/"),
                    "supabase_anon_key": anon_key.strip(),
                },
                headers={"User-Agent": "SSCP-Desktop/1.0", "Content-Type": "application/json"},
                timeout=5.0,
            )
            return res.status_code < 400
        except Exception as exc:
            logger.warning(f"[SupabaseSync] Aviso registrando Keep-Alive externo: {exc}")
            return False

    @classmethod
    def ping_keepalive(cls, cfg: Dict[str, Any], source: str = "pc_desktop") -> bool:
        if not cfg.get("enabled"):
            return False
        res = cls._rpc_post(cfg, "sscp_keepalive", {"p_source": source}, timeout=8.0)
        return bool(res and res.get("ok"))

    @classmethod
    def _maybe_ping_keepalive(cls, cfg: Dict[str, Any]) -> None:
        global _LAST_KEEPALIVE_TS
        now_ts = pytime.time()
        if (now_ts - _LAST_KEEPALIVE_TS) < 43200.0:
            return
        if cls.ping_keepalive(cfg, source="pc_desktop"):
            _LAST_KEEPALIVE_TS = now_ts

    @classmethod
    def _provision_supabase_backend(
        cls,
        clinic_id: str,
        station_secret: str,
        doctor_name: str = "Médico Especialista",
        clinic_name: str = "Consultorio Médico SSCP",
        access_token: Optional[str] = None,
        project_ref: Optional[str] = None,
        manual_url: Optional[str] = None,
        manual_anon_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ejecuta DDL/RLS/RPC con token sbp_... (creando proyecto gratis si no existe) o valida URL + Anon Key."""
        tok = (access_token or "").strip()
        ref = (project_ref or "").strip()
        supa_url = (manual_url or "").strip().rstrip("/")
        anon_key = (manual_anon_key or "").strip()
        headers = None
        sess = _get_http_session()

        if tok:
            headers = {
                "Authorization": f"Bearer {tok}",
                "Content-Type": "application/json",
                "User-Agent": "SSCP-Desktop-Setup/1.0",
            }
            try:
                p_res = sess.get("https://api.supabase.com/v1/projects", headers=headers, timeout=15.0)
                if p_res.status_code >= 400:
                    return {"ok": False, "error": f"Token de Supabase invalido o rechazado (HTTP {p_res.status_code})."}
                projects = p_res.json() or []
            except Exception as exc:
                return {"ok": False, "error": f"No se pudo conectar con Supabase API: {exc}"}

            if not projects:
                # Auto-crear proyecto gratuito en la primera organizacion del doctor
                try:
                    org_res = sess.get("https://api.supabase.com/v1/organizations", headers=headers, timeout=15.0)
                    orgs = org_res.json() if org_res.ok else []
                    if not orgs:
                        return {"ok": False, "error": "Tu cuenta de Supabase no tiene organizacion creada todavia."}
                    org_id = orgs[0].get("id")
                    slug_name = re.sub(r"[^a-z0-9-]", "-", (clinic_id or "consultorio").lower()).strip("-")[:24] or "consultorio"
                    db_pass = secrets.token_urlsafe(18) + "A1!"
                    cr_res = sess.post(
                        "https://api.supabase.com/v1/projects",
                        headers=headers,
                        json={
                            "organization_id": org_id,
                            "name": f"sscp-{slug_name}",
                            "db_pass": db_pass,
                            "region": "us-east-1",
                            "plan": "free",
                        },
                        timeout=25.0,
                    )
                    if cr_res.status_code >= 400:
                        return {"ok": False, "error": f"No se pudo crear proyecto automatico (HTTP {cr_res.status_code}): {cr_res.text[:160]}"}
                    target_proj = cr_res.json() or {}
                except Exception as exc:
                    return {"ok": False, "error": f"Error creando proyecto automatico en Supabase: {exc}"}
            else:
                if not ref and supa_url:
                    m = re.match(r"^https://([a-z0-9-]+)\.supabase\.co", supa_url, re.IGNORECASE)
                    if m:
                        ref = m.group(1)

                target_proj = None
                if ref:
                    target_proj = next((p for p in projects if p.get("ref") == ref or p.get("id") == ref), None)
                    if not target_proj:
                        return {"ok": False, "error": f"Proyecto '{ref}' no encontrado en esa cuenta de Supabase."}
                elif len(projects) == 1:
                    target_proj = projects[0]
                else:
                    refs = ", ".join(f"{p.get('name')} ({p.get('ref')})" for p in projects[:5])
                    return {"ok": False, "error": f"Hay varios proyectos en esta cuenta; indica cual en URL o Ref: {refs}"}

            ref = target_proj.get("ref") or target_proj.get("id")
            status = target_proj.get("status")
            for _ in range(30):
                if status == "ACTIVE_HEALTHY":
                    break
                pytime.sleep(3)
                chk = sess.get(f"https://api.supabase.com/v1/projects/{ref}", headers=headers, timeout=15.0)
                if chk.ok:
                    status = (chk.json() or {}).get("status")

            schema_path = cls._resolve_schema_sql_path()
            if not schema_path:
                return {"ok": False, "error": "No se encontro supabase_schema.sql en el paquete."}
            sql_text = schema_path.read_text(encoding="utf-8")

            q_res = sess.post(
                f"https://api.supabase.com/v1/projects/{ref}/database/query",
                headers=headers,
                json={"query": sql_text},
                timeout=30.0,
            )
            if q_res.status_code >= 400:
                return {"ok": False, "error": f"Error creando tablas en Supabase (HTTP {q_res.status_code}): {q_res.text[:180]}"}

            k_res = sess.get(f"https://api.supabase.com/v1/projects/{ref}/api-keys", headers=headers, timeout=15.0)
            if k_res.status_code >= 400:
                return {"ok": False, "error": "Tablas creadas, pero no se pudo leer la Anon Key."}
            keys = k_res.json() or []
            anon_key = next((k.get("api_key", "") for k in keys if k.get("name") == "anon"), "") or anon_key
            supa_url = f"https://{ref}.supabase.co"

            safe_cid = re.sub(r"[^a-zA-Z0-9_-]", "_", clinic_id)
            safe_hash = re.sub(r"[^a-f0-9]", "", hash_station_secret(station_secret).lower())
            try:
                sess.post(
                    f"https://api.supabase.com/v1/projects/{ref}/database/query",
                    headers=headers,
                    json={"query": f"UPDATE public.clinic_stations SET secret_hash = '{safe_hash}', updated_at = now() WHERE clinic_id = '{safe_cid}';"},
                    timeout=15.0,
                )
            except Exception:
                pass

        if not supa_url or not anon_key:
            return {"ok": False, "error": "Debes ingresar Access Token (sbp_...) o Project URL + Anon Key."}

        return {
            "ok": True,
            "supabase_url": supa_url,
            "supabase_anon_key": anon_key,
            "clinic_id": clinic_id,
            "station_secret": station_secret,
            "doctor_name": doctor_name,
            "clinic_name": clinic_name,
        }

    @classmethod
    def provision_doctor_supabase(
        cls,
        db: Session,
        access_token: Optional[str] = None,
        project_ref: Optional[str] = None,
        manual_url: Optional[str] = None,
        manual_anon_key: Optional[str] = None,
        clinic_id_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Configura por primera vez o cambia el Supabase propio de este doctor (creando tablas/RLS/RPC si se da token)."""
        setting = db.query(Setting).first()
        if not setting:
            return {"ok": False, "error": "No se encontro configuracion local de la clinica."}

        if clinic_id_override and clinic_id_override.strip():
            norm = re.sub(r"[^a-zA-Z0-9_-]+", "_", clinic_id_override.strip().lower()).strip("_")
            if norm:
                setting.relay_channel_id = norm
                db.commit()

        from app.services.relay_service import RelayService
        cid = RelayService.get_clinic_id(db)
        if not getattr(setting, "station_secret", None) or not setting.station_secret.strip():
            setting.station_secret = f"sscp_{secrets.token_urlsafe(18)}"
            db.commit()

        backend_res = cls._provision_supabase_backend(
            clinic_id=cid,
            station_secret=setting.station_secret,
            doctor_name=setting.doctor_name or "Médico Especialista",
            clinic_name=setting.clinic_name or "Consultorio Médico SSCP",
            access_token=access_token,
            project_ref=project_ref,
            manual_url=manual_url,
            manual_anon_key=manual_anon_key,
        )
        if not backend_res.get("ok"):
            return backend_res

        supa_url = backend_res["supabase_url"]
        anon_key = backend_res["supabase_anon_key"]
        setting.supabase_url = supa_url
        setting.supabase_anon_key = anon_key
        setting.relay_channel_id = cid
        setting.updated_at = datetime.utcnow()
        db.commit()

        cfg = cls.get_bridge_config(db)
        cls.save_preset({**cfg})
        station_ok = cls.upsert_station(cfg, force=True, db=db)
        keepalive_ok = cls.ping_keepalive(cfg, source="desktop_setup")
        if not (station_ok and keepalive_ok):
            if _LAST_UPSERT_ERROR == "unauthorized_clinic_station":
                return {
                    "ok": False,
                    "error": (
                        f"El canal '{cfg['clinic_id']}' ya existe en Supabase con la clave de una instalación anterior. "
                        "Ingresa tu Access Token (sbp_...) para recuperar la propiedad del canal o cambia el Canal del Doctor."
                    ),
                }
            return {"ok": False, "error": "Credenciales guardadas, pero la verificacion RPC en Supabase fallo (asegura haber corrido supabase_schema.sql)."}

        hub_registered = cls.register_keepalive_monitor(cfg["clinic_id"], supa_url, anon_key)
        try:
            cls.push_incremental(cfg, db)
        except Exception:
            pass
        signal_supabase_sync()
        return {
            "ok": True,
            "clinic_id": cfg["clinic_id"],
            "supabase_url": supa_url,
            "keepalive_ok": keepalive_ok,
            "hub_registered": hub_registered,
        }

    @classmethod
    def provision_from_installer_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutado desde el instalador Windows NSIS: aprovisiona la nube antes de iniciar la app."""
        tok = (payload.get("access_token") or payload.get("supabase_token") or "").strip()
        ref = (payload.get("project_ref") or "").strip()
        supa_url = (payload.get("supabase_url") or "").strip()
        anon_key = (payload.get("supabase_anon_key") or "").strip()
        raw_cid = (payload.get("clinic_id") or "").strip()
        doc_name = (payload.get("doctor_name") or "").strip() or "Médico Especialista"

        if not tok and not (supa_url and anon_key):
            return {"ok": True, "skipped": True, "reason": "no_credentials_provided"}

        # Si ya existe una BD previa (actualizacion de PC vieja), actualizarla directo
        db_exists = DB_PATH.exists() and DB_PATH.stat().st_size > 0
        if db_exists:
            Base.metadata.create_all(bind=engine)
            with SessionLocal() as db:
                st = db.query(Setting).first()
                if st:
                    return cls.provision_doctor_supabase(
                        db,
                        access_token=tok or None,
                        project_ref=ref or None,
                        manual_url=supa_url or None,
                        manual_anon_key=anon_key or None,
                        clinic_id_override=raw_cid or None,
                    )

        # Instalacion nueva (todavia no existe BD/usuarios): provisionar nube y guardar solo supabase_preset.json
        cid = re.sub(r"[^a-z0-9_-]+", "_", (raw_cid or "consultorio_principal").lower()).strip("_") or "consultorio_principal"
        sec = f"sscp_{secrets.token_urlsafe(18)}"
        res = cls._provision_supabase_backend(
            clinic_id=cid,
            station_secret=sec,
            doctor_name=doc_name,
            clinic_name=f"Consultorio {doc_name}",
            access_token=tok or None,
            project_ref=ref or None,
            manual_url=supa_url or None,
            manual_anon_key=anon_key or None,
        )
        if not res.get("ok"):
            return res

        cfg = {
            "enabled": True,
            "clinic_id": cid,
            "station_secret": sec,
            "secret_hash": hash_station_secret(sec),
            "supabase_url": res["supabase_url"],
            "supabase_anon_key": res["supabase_anon_key"],
            "doctor_name": doc_name,
            "clinic_name": f"Consultorio {doc_name}",
            "specialty": "Medicina General",
            "sede_name": "Sede Principal",
        }
        station_ok = cls.upsert_station(cfg, force=True, db=None)
        keepalive_ok = cls.ping_keepalive(cfg, source="windows_installer")
        if not (station_ok and keepalive_ok):
            return {"ok": False, "error": "Fallo al verificar RPC en Supabase durante instalacion."}

        hub_ok = cls.register_keepalive_monitor(cid, cfg["supabase_url"], cfg["supabase_anon_key"])
        cfg_save = dict(cfg)
        cfg_save["include_secret_once"] = True
        cls.save_preset(cfg_save)
        return {
            "ok": True,
            "clinic_id": cid,
            "supabase_url": cfg["supabase_url"],
            "keepalive_ok": keepalive_ok,
            "hub_registered": hub_ok,
            "preset_saved": True,
        }

    @classmethod
    def run_incremental_cycle(cls) -> Dict[str, Any]:
        if not _SYNC_LOCK.acquire(blocking=False):
            return {"skipped": True, "reason": "sync_in_progress"}
        _SYNC_THREAD_STATE.active = True
        try:
            with SessionLocal() as db:
                cfg = cls.get_bridge_config(db)
                if not cfg.get("enabled"):
                    return {"ok": False, "reason": "disabled"}

                cls.upsert_station(cfg, force=False, db=db)
                cls._maybe_ping_keepalive(cfg)
                pushed_first = cls.push_incremental(cfg, db)
                pulled = cls.pull_incremental(cfg, db)
                from app.services.appointment_reconciliation import reconcile_completed_appointments
                if reconcile_completed_appointments(db) > 0:
                    db.commit()
                pushed_after = cls.push_incremental(cfg, db)
                pushed = bool(pushed_first or pushed_after)
                return {
                    "ok": bool(pulled or pushed),
                    "clinic_id": cfg["clinic_id"],
                    "pulled": pulled,
                    "pushed": pushed,
                }
        except Exception as exc:
            logger.warning(f"[SupabaseSync] Cycle error: {exc}")
            return {"ok": False, "error": str(exc)}
        finally:
            _SYNC_THREAD_STATE.active = False
            _SYNC_LOCK.release()


_SYNC_THREAD_STATE = threading.local()

try:
    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(SessionLocal, "after_commit")
    def _sscp_auto_signal_sync_after_commit(session):
        if getattr(_SYNC_THREAD_STATE, "active", False):
            return
        signal_supabase_sync()
except Exception:
    pass
