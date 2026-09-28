import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from main import app, ensure_schema_migrations
from app.database import SessionLocal, engine
from app.models.setting import Setting

def test_station_role_and_settings():
    print("=" * 70)
    print(">>> INICIANDO PRUEBAS DE FASE 4 & 5: ROL DE ESTACIÓN Y RED TAILSCALE (v1.2.0)")
    print("=" * 70)

    # 1. Asegurar migraciones
    ensure_schema_migrations(engine)

    client = TestClient(app)

    # 2. Login
    print("\n[PASO 1] Autenticación...")
    login_resp = client.post(
        "/login",
        data={"username": "admin@sscp.com", "password": "password123"},
        follow_redirects=False
    )
    assert login_resp.status_code == 302
    print("  -> Autenticación OK.")

    # 3. GET /settings
    print("\n[PASO 2] Verificando interfaz de configuración (/settings)...")
    get_resp = client.get("/settings")
    assert get_resp.status_code == 200
    html = get_resp.text
    assert 'name="station_role"' in html
    assert "Estación de Doctor Principal" in html
    assert "Estación de Secretaría / Recepción" in html
    assert 'name="central_station_url"' in html
    print("  -> Interfaz verificada: Selector de Rol de Estación y URL Central presentes.")

    # 4. POST /settings (Configurar rol Secretaría)
    print("\n[PASO 3] Cambiando rol de estación a 'secretaria'...")
    post_payload = {
        "clinic_name": "Centro Médico SSCP",
        "doctor_name": "Dr. Carlos Mendoza",
        "specialty": "Medicina Interna",
        "phone": "809-555-0199",
        "email": "contacto@sscp.local",
        "address": "Av. Principal #100",
        "currency": "RD$",
        "sede_name": "Recepción Consultorio A",
        "tailscale_ip": "100.64.1.20",
        "sync_interval_minutes": 1,
        "station_role": "secretaria",
        "central_station_url": "http://100.64.1.10:8080"
    }

    save_resp = client.post("/settings", data=post_payload)
    assert save_resp.status_code == 200

    # 5. Verificar en Base de Datos
    db = SessionLocal()
    try:
        s = db.query(Setting).first()
        assert s.station_role == "secretaria"
        assert s.central_station_url == "http://100.64.1.10:8080"
        assert s.tailscale_ip == "100.64.1.20"
        print(f"  -> Guardado en BD verificado: station_role='{s.station_role}', central_url='{s.central_station_url}'")
    finally:
        db.close()

    # 6. Revertir a Doctor Principal
    print("\n[PASO 4] Restaurando a rol 'doctor_principal'...")
    post_payload["station_role"] = "doctor_principal"
    post_payload["central_station_url"] = ""
    save_resp2 = client.post("/settings", data=post_payload)
    assert save_resp2.status_code == 200

    db = SessionLocal()
    try:
        s2 = db.query(Setting).first()
        assert s2.station_role == "doctor_principal"
        print("  -> Restaurado a 'doctor_principal' con éxito.")
    finally:
        db.close()

    print("\n" + "=" * 70)
    print(">>> TODAS LAS PRUEBAS DE FASE 4 & 5 (ROL DE ESTACIÓN) EXITOSAS AL 100%")
    print("=" * 70)

if __name__ == "__main__":
    test_station_role_and_settings()
