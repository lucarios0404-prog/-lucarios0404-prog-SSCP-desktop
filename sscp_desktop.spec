# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

added_files = [
    ('app/templates', 'app/templates'),
    ('static', 'static'),
    ('alembic', 'alembic'),
    ('alembic.ini', '.'),
]

hidden_imports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespans',
    'uvicorn.lifespans.on',
    'uvicorn.lifespans.off',
    'reportlab',
    'reportlab.platypus',
    'reportlab.lib',
    'reportlab.lib.colors',
    'reportlab.lib.pagesizes',
    'reportlab.lib.styles',
    'reportlab.lib.units',
    'sqlalchemy.dialects.sqlite',
    'sqlite3',
    'pydantic',
    'pydantic_settings',
    'jinja2',
    'passlib.handlers.bcrypt',
    'jose',
    'httpx',
    'app.routers.auth',
    'app.routers.patients',
    'app.routers.appointments',
    'app.routers.payments',
    'app.routers.consultations',
    'app.routers.settings',
    'app.routers.vital_signs',
    'app.routers.lab_results',
    'app.routers.vaccines',
    'app.routers.messages',
    'app.routers.inventory',
    'app.routers.sync',
    'app.routers.quick_prescriptions',
    'app.routers.templates',
    'app.routers.medical_licenses',
    'app.routers.medical_references',
    'app.models.template',
    'app.models.medical_license',
    'app.models.medical_reference',
    'app.models.sync_log',
    'app.services.qr_service',
    'app.services.pdf_service',
    'app.services.sync_service',
    'app.models.audit_log',
    'app.services.audit_service',
    'app.services.patient_service',
    'app.routers.reports',
    'app.routers.users',
    'app.core.permissions',
    'app.routers.data_import',
    'app.services.data_importer',
    'access_parser',
    'construct',
    'openpyxl',
    'et_xmlfile',
    'qrcode',
    'qrcode.image.pil',
    'PIL',
    'PIL.Image',
    'cryptography',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.serialization',
    'cryptography.hazmat.primitives.asymmetric.ed25519',
    'wmi',
    'app.models.license_config',
    'app.services.license_service',
    'app.routers.activation',
]

import os
use_obfuscated = os.path.exists("app_obfuscated")
if use_obfuscated:
    pathex_dirs = ['app_obfuscated', '.']
    for item in os.listdir('app_obfuscated'):
        if item.startswith('pyarmor_runtime'):
            hidden_imports.append(item)
            added_files.append((os.path.join('app_obfuscated', item), item))
else:
    pathex_dirs = ['.']

a = Analysis(
    ['desktop_launcher.py'],
    pathex=pathex_dirs,
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SSCP-Desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SSCP-Desktop',
)
