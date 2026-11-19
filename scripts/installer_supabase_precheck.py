import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


KEEPALIVE_HUB_URL = "https://sscp.laxarusdevs.com/api/supabase-keepalive/register"


def _resolve_all_data_dirs() -> List[Path]:
    if os.environ.get("SSCP_DATA_DIR"):
        target = Path(os.environ["SSCP_DATA_DIR"])
        target.mkdir(parents=True, exist_ok=True)
        return [target]
    dirs: List[Path] = []
    if os.environ.get("APPDATA"):
        p_roam = Path(os.environ["APPDATA"]) / "SSCP Desktop" / "data"
        p_roam.mkdir(parents=True, exist_ok=True)
        dirs.append(p_roam)
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        p_loc = Path(local_app) / "SSCP" / "data"
        p_loc.mkdir(parents=True, exist_ok=True)
        dirs.append(p_loc)
    if not dirs:
        fallback = Path.home() / "AppData" / "Local" / "SSCP" / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        dirs.append(fallback)
    return dirs


def _resolve_schema_sql() -> Optional[Path]:
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "supabase_schema.sql")
        candidates.append(Path(sys._MEIPASS) / "scripts" / "supabase_schema.sql")
    candidates.append(Path(__file__).resolve().parent / "supabase_schema.sql")
    for p in candidates:
        if p.exists():
            return p
    return None


def _http_json(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 20.0,
) -> Tuple[int, Any, str]:
    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw), raw
            except Exception:
                return resp.status, raw, raw
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace") if err.fp else str(err)
        try:
            return err.code, json.loads(raw), raw
        except Exception:
            return err.code, raw, raw


def _get_suite_version() -> str:
    try:
        from app.version import SUITE_VERSION
        return str(SUITE_VERSION)
    except Exception:
        pass
    try:
        v_file = Path(__file__).resolve().parent.parent / "VERSION.json"
        if v_file.exists():
            return str(json.loads(v_file.read_text(encoding="utf-8")).get("suite") or "1.8.6-supabase")
    except Exception:
        pass
    return "1.8.6-supabase"


def _read_existing_db_info(data_dirs: List[Path]) -> Dict[str, Any]:
    info: Dict[str, Any] = {"db_exists": False, "mobile_users": [], "db_dirs": []}
    for data_dir in data_dirs:
        db_path = data_dir / "sscp.db"
        if not db_path.exists() or db_path.stat().st_size == 0:
            continue
        conn = None
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cur = conn.cursor()
            qchk = cur.execute("PRAGMA quick_check(1)").fetchone()
            ichk = cur.execute("PRAGMA integrity_check(1)").fetchone()
            if not qchk or str(qchk[0]).lower() != "ok" or not ichk or str(ichk[0]).lower() != "ok":
                continue
            info["db_dirs"].append(data_dir)
            cols = [r[1] for r in cur.execute("PRAGMA table_info(settings)").fetchall()]
            if cols and not info["db_exists"]:
                info["db_exists"] = True
                row = cur.execute("SELECT * FROM settings LIMIT 1").fetchone()
                if row:
                    rec = dict(zip(cols, row))
                    info["doctor_name"] = rec.get("doctor_name")
                    info["clinic_name"] = rec.get("clinic_name")
                    info["specialty"] = rec.get("specialty")
                    info["sede_name"] = rec.get("sede_name")
                    info["clinic_id"] = rec.get("relay_channel_id")
                    info["station_secret"] = rec.get("station_secret")
            u_cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
            if u_cols and not info["mobile_users"]:
                for u_row in cur.execute("SELECT id, name, email, role, is_active, hashed_password FROM users WHERE is_active = 1").fetchall():
                    if u_row[2] and u_row[5]:
                        info["mobile_users"].append({
                            "id": u_row[0],
                            "name": u_row[1],
                            "email": str(u_row[2]).strip().lower(),
                            "role": u_row[3],
                            "is_active": bool(u_row[4]),
                            "password_hash": u_row[5],
                        })
        except Exception:
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return info


def _update_existing_db_settings(data_dir: Path, cid: str, secret: str, url: str, anon_key: str) -> bool:
    db_path = data_dir / "sscp.db"
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False
    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        cur = conn.cursor()
        qchk = cur.execute("PRAGMA quick_check(1)").fetchone()
        ichk = cur.execute("PRAGMA integrity_check(1)").fetchone()
        if not qchk or str(qchk[0]).lower() != "ok" or not ichk or str(ichk[0]).lower() != "ok":
            return False
        cols = [r[1] for r in cur.execute("PRAGMA table_info(settings)").fetchall()]
        if not cols:
            return False
        for needed in ("relay_channel_id", "station_secret", "supabase_url", "supabase_anon_key"):
            if needed not in cols:
                cur.execute(f"ALTER TABLE settings ADD COLUMN {needed} TEXT")
        cur.execute(
            """
            UPDATE settings
            SET relay_channel_id = ?, station_secret = ?, supabase_url = ?, supabase_anon_key = ?
            WHERE id = (SELECT id FROM settings LIMIT 1)
            """,
            (cid, secret, url, anon_key),
        )
        conn.commit()
        try:
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def provision(payload: Dict[str, Any]) -> Dict[str, Any]:
    tok = (payload.get("access_token") or payload.get("supabase_token") or "").strip()
    ref = (payload.get("project_ref") or "").strip()
    supa_url = (payload.get("supabase_url") or "").strip().rstrip("/")
    anon_key = (payload.get("supabase_anon_key") or "").strip()
    raw_cid = (payload.get("clinic_id") or "").strip()

    if not tok and not (supa_url and anon_key):
        return {"ok": False, "error": "Debes ingresar tu Key de Supabase (sbp_...) o Project URL + Anon Key."}

    data_dirs = _resolve_all_data_dirs()
    db_info = _read_existing_db_info(data_dirs)
    doc_name = (payload.get("doctor_name") or db_info.get("doctor_name") or "Médico Especialista").strip()
    clinic_name = db_info.get("clinic_name") or f"Consultorio {doc_name}"
    specialty = db_info.get("specialty") or "Medicina General"
    sede_name = db_info.get("sede_name") or "Sede Principal"
    cid = re.sub(r"[^a-z0-9_-]+", "_", (raw_cid or db_info.get("clinic_id") or "consultorio_principal").lower()).strip("_") or "consultorio_principal"
    sec = (db_info.get("station_secret") or "").strip() or f"sscp_{secrets.token_urlsafe(18)}"
    sec_hash = hashlib.sha256(sec.encode("utf-8")).hexdigest()

    if tok:
        headers = {
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "User-Agent": "SSCP-Desktop-Setup/1.0",
        }
        code, projects, raw_p = _http_json("https://api.supabase.com/v1/projects", "GET", headers=headers, timeout=15.0)
        if code >= 400 or code == 0 or not isinstance(projects, list):
            return {"ok": False, "error": f"Token de Supabase invalido o sin conexion (HTTP {code})."}

        if not projects:
            o_code, orgs, _ = _http_json("https://api.supabase.com/v1/organizations", "GET", headers=headers, timeout=15.0)
            if o_code >= 400 or not isinstance(orgs, list) or not orgs:
                return {"ok": False, "error": "La cuenta de Supabase no tiene organizacion creada."}
            org_id = orgs[0].get("id")
            slug_name = re.sub(r"[^a-z0-9-]", "-", cid.lower()).strip("-")[:24] or "consultorio"
            db_pass = secrets.token_urlsafe(18) + "A1!"
            c_code, c_proj, c_raw = _http_json(
                "https://api.supabase.com/v1/projects",
                "POST",
                headers=headers,
                payload={
                    "organization_id": org_id,
                    "name": f"sscp-{slug_name}",
                    "db_pass": db_pass,
                    "region": "us-east-1",
                    "plan": "free",
                },
                timeout=25.0,
            )
            if c_code >= 400 or not isinstance(c_proj, dict):
                return {"ok": False, "error": f"No se pudo crear proyecto automatico (HTTP {c_code}): {str(c_raw)[:140]}"}
            target_proj = c_proj
        else:
            if not ref and supa_url:
                m = re.match(r"^https://([a-z0-9-]+)\.supabase\.co", supa_url, re.IGNORECASE)
                if m:
                    ref = m.group(1)
            if ref:
                target_proj = next((p for p in projects if p.get("ref") == ref or p.get("id") == ref), None)
                if not target_proj:
                    return {"ok": False, "error": f"Proyecto '{ref}' no encontrado en esta cuenta."}
            elif len(projects) == 1:
                target_proj = projects[0]
            else:
                refs = ", ".join(f"{p.get('name')} ({p.get('ref')})" for p in projects[:5])
                return {"ok": False, "error": f"Hay varios proyectos en tu cuenta; indica el Project URL o Ref: {refs}"}

        ref = target_proj.get("ref") or target_proj.get("id")
        status = target_proj.get("status")
        for _ in range(30):
            if status == "ACTIVE_HEALTHY":
                break
            time.sleep(3)
            s_code, s_proj, _ = _http_json(f"https://api.supabase.com/v1/projects/{ref}", "GET", headers=headers, timeout=15.0)
            if s_code < 400 and isinstance(s_proj, dict):
                status = s_proj.get("status")

        schema_path = _resolve_schema_sql()
        if not schema_path:
            return {"ok": False, "error": "No se encontro supabase_schema.sql en el instalador."}
        sql_text = schema_path.read_text(encoding="utf-8")

        q_code, _, q_raw = _http_json(
            f"https://api.supabase.com/v1/projects/{ref}/database/query",
            "POST",
            headers=headers,
            payload={"query": sql_text},
            timeout=30.0,
        )
        if q_code >= 400:
            return {"ok": False, "error": f"Error creando tablas en Supabase (HTTP {q_code}): {str(q_raw)[:160]}"}

        k_code, keys, _ = _http_json(f"https://api.supabase.com/v1/projects/{ref}/api-keys", "GET", headers=headers, timeout=15.0)
        if k_code >= 400 or not isinstance(keys, list):
            return {"ok": False, "error": "Tablas creadas, pero no se pudo obtener la Anon Key."}
        anon_key = next((k.get("api_key", "") for k in keys if k.get("name") == "anon"), "") or anon_key
        supa_url = f"https://{ref}.supabase.co"

        safe_cid = re.sub(r"[^a-zA-Z0-9_-]", "_", cid)
        safe_hash = re.sub(r"[^a-f0-9]", "", sec_hash.lower())
        _http_json(
            f"https://api.supabase.com/v1/projects/{ref}/database/query",
            "POST",
            headers=headers,
            payload={"query": f"UPDATE public.clinic_stations SET secret_hash = '{safe_hash}', updated_at = now() WHERE clinic_id = '{safe_cid}';"},
            timeout=15.0,
        )

    rpc_headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
        "User-Agent": "SSCP-Desktop-Setup/1.0",
    }
    st_code, st_res, st_raw = _http_json(
        f"{supa_url}/rest/v1/rpc/sscp_upsert_station",
        "POST",
        headers=rpc_headers,
        payload={
            "p_clinic_id": cid,
            "p_secret_hash": sec_hash,
            "p_doctor_name": doc_name,
            "p_clinic_name": clinic_name,
            "p_specialty": specialty,
            "p_sede_name": sede_name,
            "p_local_url": None,
            "p_tailscale_url": None,
            "p_app_version": _get_suite_version(),
            "p_mobile_users": db_info.get("mobile_users") or [],
        },
        timeout=15.0,
    )
    if st_code >= 400 or not (isinstance(st_res, dict) and st_res.get("ok")):
        return {"ok": False, "error": f"Fallo al verificar estacion en Supabase (HTTP {st_code}): {str(st_raw)[:140]}"}

    ka_code, ka_res, ka_raw = _http_json(
        f"{supa_url}/rest/v1/rpc/sscp_keepalive",
        "POST",
        headers=rpc_headers,
        payload={"p_source": "windows_installer"},
        timeout=15.0,
    )
    keepalive_ok = ka_code < 400 and isinstance(ka_res, dict) and bool(ka_res.get("ok"))
    if not keepalive_ok:
        return {"ok": False, "error": f"Fallo la verificacion Keep-Alive en Supabase (HTTP {ka_code}): {str(ka_raw)[:140]}"}

    hub_url = os.environ.get("SSCP_KEEPALIVE_HUB_URL", KEEPALIVE_HUB_URL).strip()
    hub_ok = False
    if hub_url:
        h_code, _, _ = _http_json(
            hub_url,
            "POST",
            headers={"Content-Type": "application/json", "User-Agent": "SSCP-Desktop-Setup/1.0"},
            payload={"clinic_id": cid, "supabase_url": supa_url, "supabase_anon_key": anon_key},
            timeout=10.0,
        )
        hub_ok = h_code < 400

    for ddir in data_dirs:
        updated_db = False
        if ddir in db_info.get("db_dirs", []):
            updated_db = _update_existing_db_settings(ddir, cid, sec, supa_url, anon_key)
        preset_data = {
            "clinic_id": cid,
            "supabase_url": supa_url,
            "supabase_anon_key": anon_key,
            "secret_hash": sec_hash,
            "doctor_name": doc_name,
        }
        if not updated_db:
            # Solo temporal hasta que la PC arranque, guarde en SQLite settings y limpie este secreto del JSON
            preset_data["station_secret"] = sec
        (ddir / "supabase_preset.json").write_text(json.dumps(preset_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "ok": True,
        "clinic_id": cid,
        "supabase_url": supa_url,
        "keepalive_ok": keepalive_ok,
        "hub_registered": hub_ok,
    }


def main() -> None:
    if "--provision-supabase-file" not in sys.argv:
        sys.exit(1)
    idx = sys.argv.index("--provision-supabase-file")
    cfg_path = Path(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else None
    status_path = Path(str(cfg_path) + ".status.txt") if cfg_path else None
    payload: Dict[str, Any] = {}
    try:
        if cfg_path and cfg_path.exists():
            raw = cfg_path.read_text(encoding="utf-8", errors="replace").replace("\x00", "").strip()
            # Sobrescribir y borrar de inmediato el archivo temporal con el token sbp_...
            try:
                cfg_path.write_bytes(b"\x00" * max(64, cfg_path.stat().st_size))
                cfg_path.unlink(missing_ok=True)
            except Exception:
                pass
            if raw.startswith("{"):
                payload = json.loads(raw)
            else:
                for line in raw.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        payload[k.strip()] = v.strip()
        res = provision(payload)
        print("SUPA_PRECHECK_RESULT:", json.dumps(res, ensure_ascii=False))
        if status_path:
            if res.get("ok"):
                ka = "Activado" if res.get("keepalive_ok") else "Pendiente"
                lines = [
                    f"Canal del Doctor: {res.get('clinic_id', '-')}",
                    f"Proyecto Supabase: {res.get('supabase_url', '-')}",
                    f"Tablas RLS y RPCs: Creadas y verificadas | Keep-Alive: {ka}",
                ]
            else:
                lines = [str(res.get("error") or "Error conectando con Supabase.")]
            status_path.write_text("\n".join(lines) + "\n", encoding="cp1252", errors="replace")
        sys.exit(0 if res.get("ok") else 1)
    except Exception as exc:
        print("SUPA_PRECHECK_ERROR:", str(exc))
        if status_path:
            try:
                status_path.write_text(str(exc).replace("\r", " ").replace("\n", " ") + "\r\n", encoding="cp1252", errors="replace")
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
