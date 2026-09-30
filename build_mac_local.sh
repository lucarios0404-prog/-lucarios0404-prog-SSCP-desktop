#!/usr/bin/env bash
# Script para compilar localmente SSCP Desktop en una Mac (Intel o Apple Silicon)
set -e

echo "================================================================"
echo " 🍏 Compilación Local de SSCP Desktop para macOS"
echo "================================================================"

# 1. Verificar Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no está instalado. Instálalo vía Homebrew: brew install python"
    exit 1
fi

# 2. Entorno virtual y dependencias
echo -e "\n[1/4] Configurando entorno virtual de Python..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# 3. Compilar Backend
echo -e "\n[2/4] Compilando Backend Standalone Mach-O..."
python build_backend_mac.py

# 4. Instalar dependencias de Electron
echo -e "\n[3/4] Instalando dependencias de Electron..."
cd electron
npm install

# 5. Empaquetar DMG
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    TARGET_FLAG="--arm64"
    echo -e "\n[4/4] Empaquetando para Apple Silicon ($ARCH)..."
else
    TARGET_FLAG="--x64"
    echo -e "\n[4/4] Empaquetando para Intel ($ARCH)..."
fi

npx electron-builder --mac $TARGET_FLAG -c.mac.identity=null

echo -e "\n🎉 ¡Compilación completada exitosamente!"
echo "📦 Instalador generado en: electron/dist/"
ls -lh dist/*.dmg || true
