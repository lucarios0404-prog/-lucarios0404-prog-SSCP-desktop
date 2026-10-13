import sys
import shutil
import subprocess
from pathlib import Path

# UTF-8 for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent

def build():
    print("================================================================")
    print(" 🛠️  SSCP Desktop - Compilación de Ejecutable Portable (.exe)")
    print("================================================================")

    pyinstaller_bin = BASE_DIR / "venv" / "Scripts" / "pyinstaller.exe"
    if not pyinstaller_bin.exists():
        pyinstaller_bin = "pyinstaller"

    spec_file = BASE_DIR / "sscp_desktop.spec"
    assert spec_file.exists(), f"No se encontró el archivo de especificación {spec_file}"

    # 1. Ejecutar PyInstaller
    cmd = [str(pyinstaller_bin), str(spec_file), "--noconfirm"]
    print(f"\n[1/3] Ejecutando PyInstaller con {spec_file.name}...")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        print("❌ Error durante la compilación con PyInstaller.")
        sys.exit(result.returncode)

    # 2. Asegurar estructura de datos en 'dist/SSCP-Desktop'
    dist_dir = BASE_DIR / "dist" / "SSCP-Desktop"
    data_dest = dist_dir / "data"
    data_dest.mkdir(parents=True, exist_ok=True)

    print("\n[2/3] Preparando directorio de datos limpio en dist/...")
    # SECURITY: Never package an sscp.db in the installer distributable.
    # SQLite and Alembic initialise the real clinic database in %APPDATA%/SSCP Desktop/data.
    db_dest = data_dest / "sscp.db"
    if db_dest.exists() and db_dest.stat().st_size == 0:
        db_dest.unlink()
        print("  -> Eliminado sscp.db dummy (0 bytes) para evitar colisiones.")


    # 3. Resumen final
    exe_path = dist_dir / "SSCP-Desktop.exe"
    print("\n[3/3] Verificando resultado de compilación...")
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ Ejecutable generado exitosamente: {exe_path}")
        print(f"  📦 Tamaño del binario principal: {size_mb:.2f} MB")
        print("\n🎉 Distribución lista en la carpeta: dist\\SSCP-Desktop\\")
        print("   Para iniciar, simplemente ejecute: dist\\SSCP-Desktop\\SSCP-Desktop.exe")
    else:
        print("❌ Advertencia: No se encontró el archivo ejecutable esperado.")

if __name__ == "__main__":
    build()
