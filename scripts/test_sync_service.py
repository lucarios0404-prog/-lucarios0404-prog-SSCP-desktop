import sys
import json
import asyncio
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.services.sync_service import SyncService

def test_sync():
    print("=== [TEST SYNC] Probando Motor de Sincronización Offline/Online ===")
    db = SessionLocal()
    
    admin = db.query(User).filter(User.role == "admin").first()
    assert admin is not None, "Debe existir un usuario admin"
    
    # 1. Estadísticas de Sincronización
    print("\n--- 1. Verificando Estadísticas de Datos Locales ---")
    stats = SyncService.get_sync_stats(db)
    assert "total_patients" in stats
    assert "total_consultations" in stats
    print(f"  -> Datos locales detectados: {stats['total_patients']} pacientes, {stats['total_consultations']} consultas.")
    
    # 2. Comprobación de Conectividad
    print("\n--- 2. Verificando Comprobador de Conectividad (Online / Offline Graceful) ---")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Simulación de servidor inalcanzable (modo offline)
    res_offline = loop.run_until_complete(SyncService.check_connection("http://127.0.0.1:9999/not-found", timeout=0.5))
    assert res_offline["online"] is False
    assert "Modo Offline activo" in res_offline["message"]
    print("  ✅ Manejo de Modo Offline validado correctamente.")

    # 3. Exportación de Paquete JSON
    print("\n--- 3. Verificando Exportación de Paquete JSON Completo ---")
    package = SyncService.export_full_package(db)
    assert package["version"] == "1.0"
    assert "data" in package
    assert "patients" in package["data"]
    assert "consultations" in package["data"]
    print(f"  ✅ Paquete generado con éxito ({len(package['data']['patients'])} pacientes exportados).")

    # 4. Importación de Paquete JSON
    print("\n--- 4. Verificando Fusión e Importación de Paquete JSON ---")
    import uuid
    unique_sync_doc = f"SYNC-{uuid.uuid4().hex[:6]}"
    test_import_pkg = {
        "version": "1.0",
        "data": {
            "patients": [
                {
                    "first_name": "Paciente",
                    "last_name": "Sincronizado",
                    "document_id": unique_sync_doc,
                    "phone": "809-555-0000",
                    "email": f"sync.{unique_sync_doc}@test.com",
                    "blood_type": "AB+"
                }
            ],
            "consultations": [
                {
                    "patient_document_id": unique_sync_doc,
                    "reason": "Consulta sincronizada desde nube",
                    "diagnosis": "Diagnóstico remoto",
                    "treatment": "Tratamiento remoto",
                    "sede_origen": "remoto"
                }
            ],
            "vital_signs": [],
            "payments": []
        }
    }
    import_result = SyncService.import_package(db, test_import_pkg)
    assert import_result["success"] is True
    assert import_result["counts"]["patients"] >= 1
    print(f"  ✅ {import_result['message']}")

    # 5. Endpoints HTTP
    print("\n--- 5. Verificando Endpoints HTTP del Router de Sincronización ---")
    client = TestClient(app)
    login_resp = client.post("/login", data={"username": admin.email, "password": "password123"}, follow_redirects=False)
    auth_cookies = login_resp.cookies

    # Dashboard de Sincronización
    r_dash = client.get("/sync", cookies=auth_cookies)
    assert r_dash.status_code == 200
    assert "Centro de Sincronización" in r_dash.text
    print("  ✅ GET /sync -> 200 OK (Dashboard renderizado)")

    # Descarga de Paquete de Exportación
    r_export = client.get("/sync/export", cookies=auth_cookies)
    assert r_export.status_code == 200
    assert r_export.headers["content-type"] == "application/json"
    exported_json = json.loads(r_export.content)
    assert exported_json["version"] == "1.0"
    print("  ✅ GET /sync/export -> 200 OK (Archivo JSON descargable)")

    # Disparo de Trigger de Sincronización
    r_trigger = client.post("/sync/trigger", data={"remote_url": "https://sscp.laxarusdevs.com"}, cookies=auth_cookies, follow_redirects=False)
    assert r_trigger.status_code == 303
    print("  ✅ POST /sync/trigger -> 303 Redirect con status de sincronización")

    db.close()
    loop.close()
    print("\n🎉 FASE B: Motor de Sincronización Offline/Online COMPLETADO Y VALIDADO AL 100%!")

if __name__ == "__main__":
    test_sync()
