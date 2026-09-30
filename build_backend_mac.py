#!/usr/bin/env python3
"""
Compilación del Backend Python para macOS (Intel x86_64 y Apple Silicon arm64).
Genera el binario Mach-O ejecutable sin extensión en dist/SSCP-Desktop/SSCP-Desktop
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def build():
    print("================================================================")
    print(" 🍏 SSCP Desktop - Compilación del Backend para macOS")
    try:
        arch = os.uname().machine
    except Exception:
        arch = "desconocido"
    print(f"    Arquitectura: {arch} | Python: {sys.version.split()[0]}")
    print("================================================================")

    pyinstaller_bin = shutil.which("pyinstaller") or "pyinstaller"

    spec_file = BASE_DIR / "sscp_desktop.spec"
    assert spec_file.exists(), f"No se encontró el archivo de especificación {spec_file}"

    # 1. Ejecutar PyInstaller
    cmd = [str(pyinstaller_bin), str(spec_file), "--noconfirm", "--clean"]
    print(f"\n[1/3] Ejecutando PyInstaller ({spec_file.name})...")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        print("❌ Error durante la compilación con PyInstaller.")
        sys.exit(result.returncode)

    # 2. Asegurar estructura de datos
    dist_dir = BASE_DIR / "dist" / "SSCP-Desktop"
    data_dest = dist_dir / "data"
    data_dest.mkdir(parents=True, exist_ok=True)

    print("\n[2/3] Preparando directorio de datos...")
    db_dest = data_dest / "sscp.db"
    if not db_dest.exists():
        db_dest.touch()

    # 3. Permisos de ejecución en macOS (chmod +x)
    exe_path = dist_dir / "SSCP-Desktop"
    print("\n[3/3] Verificando resultado de compilación...")
    if exe_path.exists():
        exe_path.chmod(0o755)
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ Binario Mach-O generado exitosamente: {exe_path}")
        print(f"  📦 Tamaño: {size_mb:.2f} MB")
        print("\n🎉 Backend macOS listo en: dist/SSCP-Desktop/")
    else:
        print(f"❌ No se encontró el binario generado en {exe_path}")
        sys.exit(1)

if __name__ == "__main__":
    build()
