"""
Script utilitario para vaciar pacientes e historias clínicas en la base de datos local
manteniendo intactos: Usuarios, Licencia, Configuraciones y Catálogos.
Crea automáticamente una copia de respaldo antes de borrar.
"""
import os
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

def find_db():
    # 1. Chequear argumento
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        return Path(sys.argv[1])
    
    # 2. Chequear %LOCALAPPDATA%/SSCP/data/sscp.db
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        p = Path(local_app_data) / "SSCP" / "data" / "sscp.db"
        if p.exists():
            return p
            
    # 3. Chequear carpeta local del proyecto data/sscp.db
    base_dir = Path(__file__).resolve().parent.parent
    p_dev = base_dir / "data" / "sscp.db"
    if p_dev.exists():
        return p_dev

    return None

def main():
    db_path = find_db()
    if not db_path:
        print("❌ No se encontró el archivo sscp.db.")
        print("   Por favor indica la ruta manualmente: python vaciar_pacientes.py \"C:\\ruta\\a\\sscp.db\"")
        return

    print(f"📁 Base de datos encontrada: {db_path}")
    
    # Crear backup automático
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"sscp_backup_antes_de_vaciar_{timestamp}.db"
    try:
        shutil.copy2(db_path, backup_path)
        print(f"🛡️ Respaldo de seguridad creado en: {backup_path.name}")
    except Exception as e:
        print(f"⚠️ No se pudo crear el respaldo: {e}")
        return

    # Conectar y vaciar tablas de pacientes
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tables = [
        "consultations",
        "vital_signs",
        "appointments",
        "payments",
        "lab_results",
        "vaccines",
        "medical_references",
        "sync_logs",
        "patients"
    ]

    total_deleted = 0
    for table in tables:
        try:
            cursor.execute(f"SELECT count(*) FROM {table}")
            cnt = cursor.fetchone()[0]
            cursor.execute(f"DELETE FROM {table}")
            total_deleted += cnt
            print(f"  - {table}: {cnt} registros eliminados")
        except sqlite3.OperationalError:
            pass # Si la tabla no existe en esta version

    conn.commit()
    cursor.execute("VACUUM")
    conn.close()

    print(f"\n✅ Operación completada exitosamente!")
    print(f"   Se eliminaron {total_deleted} registros relacionados con pacientes e historial.")
    print("   Tu usuario, licencia y ajustes siguen 100% intactos.")
    print("   Ahora puedes abrir SSCP y hacer clic en 'Traer de la Nube (Pull)'.")

if __name__ == "__main__":
    main()
