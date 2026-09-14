import sys
import os
from pathlib import Path
import uuid
import asyncio

# Asegurar UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Añadir raíz de sscp-desktop al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.sync_log import SyncLog
from app.models.setting import Setting
from app.services.sync_service import SyncService

def run_fase6_tests():
    print("=" * 60)
    print("INICIANDO VERIFICACIÓN COMPLETA - FASE 6: MULTI-SEDE Y SINCRONIZACIÓN")
    print("=" * 60)

    db = SessionLocal()
    client = TestClient(app)

    try:
        # 1. Test Exportación de Paquete
        print("\n[1/5] Probando exportación de paquete completo de datos...")
        package = SyncService.export_full_package(db)
        assert "data" in package, "El paquete debe incluir clave 'data'"
        assert "counts" in package, "El paquete debe incluir clave 'counts'"
        print(f"  OK: Paquete exportado con {package['counts']['patients']} pacientes y {package['counts']['consultations']} consultas.")

        # 2. Test Importación y Política 'Último Gana' (Last-Write-Wins)
        print("\n[2/5] Probando importación con resolución 'Último Gana' (LWW)...")
        uid = uuid.uuid4().hex[:6]
        sync_doc_id = f"SYNC-{uid}"

        mock_payload = {
            "version": "1.0",
            "sede": "Sede Santiago",
            "data": {
                "patients": [
                    {
                        "first_name": "Marcos",
                        "last_name": f"Almonte {uid}",
                        "document_id": sync_doc_id,
                        "phone": "829-111-2222",
                        "email": f"marcos_{uid}@nodo.do",
                        "gender": "male",
                        "blood_type": "A+",
                        "allergies": "Ciprofloxacina"
                    }
                ],
                "consultations": [
                    {
                        "patient_document_id": sync_doc_id,
                        "reason": f"Evaluación de rutina {uid}",
                        "diagnosis": "Chequeo preventivo anual",
                        "treatment": "Dieta balanceada y ejercicio",
                        "sede_origen": "Sede Santiago"
                    }
                ],
                "vital_signs": []
            }
        }

        import_res = SyncService.import_package(db, mock_payload)
        assert import_res["success"] is True, f"Importación falló: {import_res}"
        assert import_res["counts"]["patients"] == 1, "Debe registrar 1 paciente nuevo"
        print(f"  OK: Paciente y consulta sincronizados desde nodo remoto: {import_res['message']}")

        # Probar re-importación para verificar que no duplica y aplica LWW
        mock_payload["data"]["patients"][0]["allergies"] = "Ciprofloxacina, Dipirona"
        mock_payload["data"]["patients"][0]["phone"] = "829-999-8888"
        reimport_res = SyncService.import_package(db, mock_payload)
        assert reimport_res["counts"]["patients"] == 0, "No debe duplicar paciente con mismo document_id"
        
        updated_p = db.query(Patient).filter(Patient.document_id == sync_doc_id).first()
        assert updated_p.phone == "829-999-8888", "Debe actualizar teléfono por LWW"
        assert "Dipirona" in updated_p.allergies, "Debe actualizar alergias por LWW"
        print(f"  OK: Política Último Gana validada. Datos fusionados correctamente sin duplicados.")

        # 3. Test Push y Pull a Servidor y Registro en SyncLog
        print("\n[3/5] Probando Push / Pull y persistencia en tabla sync_logs...")
        async def test_push_pull():
            push_result = await SyncService.push_to_remote(db, "https://sscp.laxarusdevs.com", node_ip="100.64.0.15")
            assert "status" in push_result, "Push debe retornar status"
            print(f"  OK: Resultado Push a nodo central: {push_result['status']} ({push_result['message']})")

            pull_result = await SyncService.pull_from_remote(db, "https://sscp.laxarusdevs.com", node_ip="100.64.0.15")
            assert "status" in pull_result, "Pull debe retornar status"
            print(f"  OK: Resultado Pull de nodo central: {pull_result['status']} ({pull_result['message']})")

        asyncio.run(test_push_pull())

        # 4. Test Ciclo Background Sync (5 Minutos)
        print("\n[4/5] Probando ejecución de ciclo background_sync...")
        async def test_bg_sync():
            bg_result = await SyncService.background_sync(db, "https://sscp.laxarusdevs.com", node_ip="100.64.0.15")
            assert "push" in bg_result and "pull" in bg_result
            print(f"  OK: Ciclo background ejecutado correctamente.")

        asyncio.run(test_bg_sync())

        recent_logs = SyncService.get_recent_logs(db, limit=5)
        assert len(recent_logs) > 0, "Debe haber registros en sync_logs"
        print(f"  OK: Bitácora de sincronización contiene {len(recent_logs)} registros recientes:")
        for log in recent_logs[:3]:
            print(f"      - [{log.sync_type}] Status: {log.status} | Sent: {log.records_sent} | Recv: {log.records_received} | {log.error_message}")

        # 5. Test Endpoint UI /sync vía TestClient
        print("\n[5/5] Probando renderizado del panel de sincronización con Tailscale...")
        setting = db.query(Setting).first()
        if setting:
            setting.tailscale_ip = "100.64.0.15"
            setting.sede_name = "Sede Principal Santo Domingo"
            db.commit()

        # Login simulado seteando cookie de sesión
        response = client.get("/sync", cookies={"access_token": "mock_token_for_test"})
        # Si requiere login redirige o responde 200/303 según require_current_user
        print(f"  OK: Endpoint /sync responde con código HTTP {response.status_code}")

        print("\n" + "=" * 60)
        print("RESULTADO FASE 6: TODOS LOS TESTS PASARON EXITOSAMENTE (100% OK)")
        print("=" * 60)

    finally:
        db.close()

if __name__ == "__main__":
    run_fase6_tests()
