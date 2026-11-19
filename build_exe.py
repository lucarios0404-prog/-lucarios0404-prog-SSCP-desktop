import os
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

    spec_file = BASE_DIR / "sscp_desktop.spec"
    assert spec_file.exists(), f"No se encontró el archivo de especificación {spec_file}"

    env = os.environ.copy()
    venv_site = BASE_DIR / "venv" / "Lib" / "site-packages"
    extra_paths = [str(BASE_DIR)]
    if venv_site.exists():
        for sub in [venv_site, venv_site / "win32", venv_site / "win32" / "lib", venv_site / "Pythonwin", venv_site / "pywin32_system32"]:
            if sub.exists():
                extra_paths.append(str(sub))
        pywin32_sys = venv_site / "pywin32_system32"
        if pywin32_sys.exists():
            env["PATH"] = os.pathsep.join([str(pywin32_sys), env.get("PATH", "")])
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(extra_paths + ([existing_pp] if existing_pp else []))

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_file),
        "--noconfirm",
    ]
    print(f"\n[1/3] Ejecutando PyInstaller con {spec_file.name}...")
    result = subprocess.run(cmd, cwd=str(BASE_DIR), env=env)
    if result.returncode != 0:
        print("❌ Error durante la compilación con PyInstaller.")
        sys.exit(result.returncode)

    # 2. Asegurar estructura de datos en 'dist/SSCP-Desktop'
    dist_dir = BASE_DIR / "dist" / "SSCP-Desktop"
    data_dest = dist_dir / "data"
    data_dest.mkdir(parents=True, exist_ok=True)

    print("\n[2/3] Preparando directorio de datos limpio en dist/...")
    # SEGURIDAD Y LIMPIEZA: El instalador NUNCA debe empaquetar base de datos con pacientes.
    # El sistema debe iniciar limpio y vacío.
    db_dest = data_dest / "sscp.db"
    if db_dest.exists():
        db_dest.unlink()
        print("  -> sscp.db excluido de dist (instalador limpio y vacío sin pacientes)")


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
