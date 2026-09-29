import os
import sys
import shutil
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent

def build_electron_dist():
    print("==========================================================")
    print(" Empaquetando SSCP Desktop (Edicion Electron)")
    print("==========================================================")

    dist_electron = BASE_DIR / "dist" / "SSCP-Desktop-Electron"
    if dist_electron.exists():
        print(f"Limpiando {dist_electron}...")
        shutil.rmtree(dist_electron)
    dist_electron.mkdir(parents=True, exist_ok=True)

    # 1. Copiar binarios precompilados de Electron v44
    electron_prebuilt = BASE_DIR / "electron" / "node_modules" / "electron" / "dist"
    assert electron_prebuilt.exists(), f"No se encontró {electron_prebuilt}"

    print("[1/4] Copiando runtime de Electron...")
    for item in electron_prebuilt.iterdir():
        dest = dist_electron / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # 2. Renombrar electron.exe a SSCP-Desktop.exe
    orig_exe = dist_electron / "electron.exe"
    target_exe = dist_electron / "SSCP-Desktop.exe"
    if orig_exe.exists():
        orig_exe.rename(target_exe)
        print("  -> Renombrado electron.exe a SSCP-Desktop.exe")

    # 3. Preparar resources/app
    app_dir = dist_electron / "resources" / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    print("[2/4] Copiando código de la aplicación Electron en resources/app...")
    shutil.copy2(BASE_DIR / "electron" / "package.json", app_dir / "package.json")
    
    # config
    shutil.copytree(BASE_DIR / "electron" / "config", app_dir / "config")
    
    # src
    shutil.copytree(BASE_DIR / "electron" / "src", app_dir / "src")

    # 4. Copiar backend compilado en resources/backend
    backend_src = BASE_DIR / "dist" / "SSCP-Desktop"
    assert backend_src.exists(), f"No se encontró el backend en {backend_src}"
    backend_dest = dist_electron / "resources" / "backend"

    print("[3/4] Copiando backend Python compilado en resources/backend...")
    shutil.copytree(backend_src, backend_dest)


    print("[4/4] Verificando empaquetado...")
    assert target_exe.exists(), "Falta ejecutable principal"
    assert (app_dir / "src" / "main" / "main.js").exists(), "Falta main.js"
    assert (backend_dest / "SSCP-Desktop.exe").exists(), "Falta backend ejecutable"

    print("✅ Empaquetado de Electron completado con éxito en:")
    print(f"   {dist_electron}")

if __name__ == "__main__":
    build_electron_dist()
