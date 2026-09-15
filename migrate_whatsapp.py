"""
Migración para soporte de WhatsApp en SSCP Desktop
Agrega columnas a 'settings' y 'appointments'.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "sscp.db"

def migrate():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # 1. Migrar tabla 'settings'
    cursor.execute("PRAGMA table_info(settings)")
    settings_cols = [col[1] for col in cursor.fetchall()]
    
    new_settings_cols = {
        "whatsapp_doctor_phone": "TEXT",
        "whatsapp_auto_send": "BOOLEAN DEFAULT 0",
        "whatsapp_auto_hour": "TEXT DEFAULT '08:30'",
        "whatsapp_template_reminder": "TEXT DEFAULT 'Estimado(a) {paciente}, le recordamos su cita médica con el {doctor} el día {fecha} a las {hora} en {clinica}. Por favor responda para confirmar su asistencia.'",
        "whatsapp_template_waiting": "TEXT DEFAULT 'Dr. {doctor}, el paciente {paciente} ha llegado a recepción y se encuentra en sala de espera.'",
        "whatsapp_template_followup": "TEXT DEFAULT 'Estimado(a) {paciente}, el {doctor} le consulta cómo ha evolucionado con el tratamiento indicado y le recuerda su cita de control.'",
        "whatsapp_gateway_status": "TEXT DEFAULT 'disconnected'",
        "whatsapp_connected_phone": "TEXT"
    }
    
    for col_name, col_def in new_settings_cols.items():
        if col_name not in settings_cols:
            print(f"[Migration] Agregando columna {col_name} a settings...")
            cursor.execute(f"ALTER TABLE settings ADD COLUMN {col_name} {col_def}")
            
    # 2. Migrar tabla 'appointments'
    cursor.execute("PRAGMA table_info(appointments)")
    appt_cols = [col[1] for col in cursor.fetchall()]
    
    new_appt_cols = {
        "whatsapp_reminder_sent": "BOOLEAN DEFAULT 0",
        "whatsapp_reminder_sent_at": "DATETIME"
    }
    
    for col_name, col_def in new_appt_cols.items():
        if col_name not in appt_cols:
            print(f"[Migration] Agregando columna {col_name} a appointments...")
            cursor.execute(f"ALTER TABLE appointments ADD COLUMN {col_name} {col_def}")
            
    conn.commit()
    conn.close()
    print("✅ Migración de WhatsApp completada con éxito.")

if __name__ == "__main__":
    migrate()
