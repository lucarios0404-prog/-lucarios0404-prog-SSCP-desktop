"""
Test de verificación integral de la integración de WhatsApp en SSCP Desktop
(1-Clic wa.me + Gateway Autónomo QR)
"""
import sys
import os
from pathlib import Path
from datetime import date, datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Asegurar path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.setting import Setting
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.services.whatsapp_service import WhatsAppService
from app.services.whatsapp_gateway import gateway_manager
from app.core.security import create_access_token

def run_tests():
    print("=================================================================")
    print("🚀 INICIANDO VERIFICACIÓN COMPLETA: MÓDULO WHATSAPP (1-CLIC + QR)")
    print("=================================================================")

    # 1. Test Unitario: Limpieza de números de teléfono
    print("\n--- TEST 1: Limpieza y Formateo de Teléfonos ---")
    test_cases = [
        ("809-555-0199", "18095550199"),
        ("(829) 123-4567", "18291234567"),
        ("+1 849 999 8888", "18499998888"),
        ("+58 412 1234567", "584121234567"),
        ("18091112233", "18091112233"),
    ]
    for raw, expected in test_cases:
        clean = WhatsAppService.clean_phone_number(raw)
        assert clean == expected, f"Fallo: {raw} -> {clean} (esperado {expected})"
        print(f"  ✓ {raw} -> {clean}")
    print("  ✅ Limpieza de teléfonos OK.")

    # 2. Test Unitario: Interpolación de Plantillas Dinámicas
    print("\n--- TEST 2: Renderizado Dinámico de Plantillas ---")
    template = "Hola {paciente}, cita con {doctor} el {fecha} a las {hora} en {clinica}."
    ctx = {
        "paciente": "Carlos Santana",
        "doctor": "Dra. María Almonte",
        "fecha": "16/09/2026",
        "hora": "10:30 AM",
        "clinica": "Centro Médico SSCP"
    }
    rendered = WhatsAppService.render_template(template, ctx)
    expected_msg = "Hola Carlos Santana, cita con Dra. María Almonte el 16/09/2026 a las 10:30 AM en Centro Médico SSCP."
    assert rendered == expected_msg, f"Fallo renderizado: {rendered}"
    print(f"  Resultado: \"{rendered}\"")
    print("  ✅ Interpolación de plantillas OK.")

    # 3. Test Unitario: Generación de enlace wa.me
    print("\n--- TEST 3: Generación de Enlace wa.me de 1-Clic ---")
    wa_link = WhatsAppService.build_wa_link("809-555-0199", rendered)
    assert "https://wa.me/18095550199?text=" in wa_link
    assert "Carlos%20Santana" in wa_link
    print(f"  Enlace generado: {wa_link[:75]}...")
    print("  ✅ Generación de enlaces wa.me OK.")

    # 4. Test Unitario: Gateway QR y Ciclo de Conexión
    print("\n--- TEST 4: Generación de QR y Ciclo del Gateway ---")
    qr_res = gateway_manager.generate_pairing_qr("+1 (809) 555-0199")
    assert qr_res["status"] == "pairing"
    assert qr_res["qr_image_base64"].startswith("data:image/png;base64,")
    print(f"  ✓ QR generado con éxito (longitud base64: {len(qr_res['qr_image_base64'])})")

    # Confirmar vinculación
    pair_res = gateway_manager.confirm_pairing("+1 (809) 555-0199")
    assert pair_res["status"] == "connected"
    assert gateway_manager.get_status()["is_connected"] is True
    print(f"  ✓ Gateway vinculado como: {pair_res['phone']}")

    # Enviar mensaje de prueba por el Gateway
    send_res = gateway_manager.send_message("18095550199", "Mensaje de prueba automático")
    assert send_res["success"] is True
    print(f"  ✓ Mensaje despachado por Gateway a {send_res['phone']}")
    print("  ✅ Ciclo de vida del Gateway OK.")

    # 5. Test de Integración: Endpoints HTTP de FastAPI
    print("\n--- TEST 5: Endpoints HTTP con TestClient ---")
    client = TestClient(app)

    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.role == "admin").first()
        assert admin_user is not None, "Debe existir un usuario admin"
        token = create_access_token({"email": admin_user.email})

    client.cookies.set("access_token", f"Bearer {token}")

    # Probar GET /settings/whatsapp/status
    res_status = client.get("/settings/whatsapp/status")
    assert res_status.status_code == 200, f"Error status: {res_status.text}"
    status_data = res_status.json()
    assert "status" in status_data
    print(f"  ✓ Endpoint /settings/whatsapp/status -> {status_data['status']}")

    # Probar POST /settings/whatsapp/generate-qr
    res_qr = client.post("/settings/whatsapp/generate-qr")
    assert res_qr.status_code == 200
    qr_data = res_qr.json()
    assert "qr_image_base64" in qr_data
    print(f"  ✓ Endpoint /settings/whatsapp/generate-qr -> QR recibido")

    # Probar POST /settings/whatsapp/confirm-pairing
    res_confirm = client.post("/settings/whatsapp/confirm-pairing", data={"phone": "+1 (809) 555-0199"})
    assert res_confirm.status_code == 200
    assert res_confirm.json()["is_connected"] is True
    print(f"  ✓ Endpoint /settings/whatsapp/confirm-pairing -> Conectado")

    # Probar citas: buscar una cita real o crear una para pruebas
    with SessionLocal() as db:
        appt = db.query(Appointment).first()
        if not appt:
            patient = db.query(Patient).first()
            appt = Appointment(
                patient_id=patient.id if patient else 1,
                doctor_id=admin_user.id,
                date=date.today() + timedelta(days=1),
                start_time=datetime.strptime("10:00", "%H:%M").time(),
                end_time=datetime.strptime("10:30", "%H:%M").time(),
                reason="Control General",
                status="Pendiente"
            )
            db.add(appt)
            db.commit()
            db.refresh(appt)

        appt_id = appt.id

    # Probar GET /appointments/{id}/whatsapp-info
    res_info = client.get(f"/appointments/{appt_id}/whatsapp-info")
    assert res_info.status_code == 200
    info_data = res_info.json()
    assert "wa_link" in info_data
    assert "message" in info_data
    print(f"  ✓ Endpoint /appointments/{appt_id}/whatsapp-info -> Mensaje: \"{info_data['message'][:45]}...\"")

    # Probar POST /appointments/{id}/whatsapp-send (Modo Auto / Gateway)
    res_send = client.post(f"/appointments/{appt_id}/whatsapp-send", data={"send_mode": "auto"})
    assert res_send.status_code == 200
    send_data = res_send.json()
    assert send_data["success"] is True
    assert send_data["already_sent"] is True
    print(f"  ✓ Endpoint /appointments/{appt_id}/whatsapp-send (Auto) -> Modo: {send_data['mode']}, Enviado: {send_data['sent_at']}")

    # Probar GET /appointments/{id}/waiting-alert-wa
    res_alert = client.get(f"/appointments/{appt_id}/waiting-alert-wa")
    assert res_alert.status_code == 200
    alert_data = res_alert.json()
    assert "wa_link" in alert_data
    print(f"  ✓ Endpoint /appointments/{appt_id}/waiting-alert-wa -> Alerta Dr: \"{alert_data['message'][:45]}...\"")

    # Probar POST /appointments/whatsapp/send-all-daily-reminders
    res_bulk = client.post("/appointments/whatsapp/send-all-daily-reminders", data={"target_date": (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")})
    assert res_bulk.status_code == 200
    bulk_data = res_bulk.json()
    assert bulk_data["success"] is True
    print(f"  ✓ Endpoint /appointments/whatsapp/send-all-daily-reminders -> Total citas procesadas: {bulk_data['total_eligible']}")

    # Probar POST /settings/whatsapp/send-test
    res_test = client.post("/settings/whatsapp/send-test", data={"phone": "8095550199", "message": "Test final"})
    assert res_test.status_code == 200
    test_data = res_test.json()
    assert test_data["success"] is True
    print(f"  ✓ Endpoint /settings/whatsapp/send-test -> Éxito")

    # Probar GET /settings/ y GET /appointments/ para validar renderizado HTML
    res_settings_html = client.get("/settings/")
    assert res_settings_html.status_code == 200
    assert "Integración de WhatsApp" in res_settings_html.text
    assert "Vincular / Ver Código QR" in res_settings_html.text
    print("  ✓ Renderizado HTML de /settings/ con módulo WhatsApp OK")

    res_appts_html = client.get("/appointments/")
    assert res_appts_html.status_code == 200
    assert "Recordatorios WhatsApp" in res_appts_html.text
    print("  ✓ Renderizado HTML de /appointments/ con acciones WhatsApp OK")

    print("\n=================================================================")
    print("🎉 TODAS LAS PRUEBAS DE WHATSAPP (1-CLIC + QR) PASARON CON ÉXITO!")
    print("=================================================================")

if __name__ == "__main__":
    run_tests()
