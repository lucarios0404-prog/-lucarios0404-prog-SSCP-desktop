"""Propaga VERSION.json a todos los componentes del ecosistema SSCP.

Uso:
    python scripts/sync_versions.py --check   # falla (exit 1) si hay desfase o versiones sueltas
    python scripts/sync_versions.py --apply   # reescribe los archivos que dependen de VERSION.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent.parent
WORKSPACE = DESKTOP.parent
VERSION_FILE = DESKTOP / "VERSION.json"

# Archivos que consumen la version generada: no deben contener versiones escritas a mano.
CONSUMERS = [
    DESKTOP / "main.py",
    DESKTOP / "electron" / "src" / "main" / "menu.js",
    DESKTOP / "app" / "templates" / "dashboard.html",
    DESKTOP / "app" / "templates" / "settings" / "index.html",
    WORKSPACE / "sscp" / "resources" / "views" / "welcome.blade.php",
    WORKSPACE / "sscp" / "resources" / "views" / "pwa" / "login.blade.php",
]
LITERAL_VERSION = re.compile(r"(?<![\w.])v?\d+\.\d+\.\d+(?![\w.])")
COMMENT_PREFIXES = ("<!--", "{{--", "//", "#", "*")


def load_versions() -> dict:
    return json.loads(VERSION_FILE.read_text(encoding="utf-8"))


def render_python_module(v: dict) -> str:
    return (
        '"""Generado por scripts/sync_versions.py desde VERSION.json. No editar a mano."""\n'
        f'SUITE_VERSION = "{v["suite"]}"\n'
        f'APK_VERSION = "{v["apk"]}"\n'
        f'APK_CODE = {v["apk_code"]}\n'
        f'NUBE_APK_VERSION = "{v["nube_apk"]}"\n'
        f'MAC_VERSION = "{v.get("mac", "")}"\n'
    )


def render_laravel_config(v: dict) -> str:
    return (
        "<?php\n\n"
        "// Generado por scripts/sync_versions.py desde VERSION.json. No editar a mano.\n"
        "return [\n"
        f"    'suite' => '{v['suite']}',\n"
        f"    'apk' => '{v['apk']}',\n"
        f"    'nube_apk' => '{v['nube_apk']}',\n"
        f"    'mac' => '{v.get('mac', '')}',\n"
        "];\n"
    )


def read_raw(path: Path) -> str:
    """Lee sin traducir finales de linea para no ensuciar los diffs de git."""
    return path.read_bytes().decode("utf-8")


def write_raw(path: Path, content: str) -> None:
    path.write_bytes(content.encode("utf-8"))


def build_targets(v: dict):
    """Lista de (ruta, contenido_actual_o_None, contenido_esperado)."""
    generated = {
        DESKTOP / "app" / "version.py": render_python_module(v),
        WORKSPACE / "sscp" / "config" / "release.php": render_laravel_config(v),
    }
    targets = [
        (path, read_raw(path) if path.exists() else None, expected)
        for path, expected in generated.items()
    ]

    edits = [
        (DESKTOP / "electron" / "package.json", r'^(\s*"version":\s*")[^"]+(")', rf'\g<1>{v["suite"]}\g<2>'),
        (DESKTOP / "installer.nsi", r'(!define PRODUCT_VERSION ")[^"]+(")', rf'\g<1>{v["suite"]}\g<2>'),
        (WORKSPACE / "sscp-mobile" / "app" / "build.gradle", r'(versionCode\s+)\d+', rf'\g<1>{v["apk_code"]}'),
        (WORKSPACE / "sscp-mobile" / "app" / "build.gradle", r'(versionName\s+")[^"]+(")', rf'\g<1>{v["apk"]}\g<2>'),
    ]
    originals, contents = {}, {}
    for path, pattern, replacement in edits:
        originals.setdefault(path, read_raw(path))
        contents.setdefault(path, originals[path])
        contents[path], count = re.subn(pattern, replacement, contents[path], count=1, flags=re.M)
        if count != 1:
            raise SystemExit(f"[ERROR] patron no encontrado en {path}: {pattern}")
    targets += [(path, originals[path], contents[path]) for path in originals]

    # mobile/index.html: fuente única en sscp-mobile, reflejada en desktop
    mobile_master = WORKSPACE / "sscp-mobile" / "app" / "src" / "main" / "assets" / "www" / "index.html"
    desktop_replica = DESKTOP / "app" / "templates" / "mobile" / "index.html"
    if mobile_master.exists():
        targets.append((desktop_replica, read_raw(desktop_replica) if desktop_replica.exists() else None, read_raw(mobile_master)))

    return targets


def find_stray_literals():
    stray = []
    for path in CONSUMERS:
        for number, line in enumerate(read_raw(path).splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(COMMENT_PREFIXES) or "<!--" in line or "{{--" in line:
                continue
            for match in LITERAL_VERSION.finditer(line):
                stray.append(f"{path.relative_to(WORKSPACE)}:{number}: {match.group()}")
    return stray


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    versions = load_versions()
    problems = []
    for path, current, expected in build_targets(versions):
        if current == expected:
            continue
        if args.apply:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_raw(path, expected)
            print(f"[ACTUALIZADO] {path.relative_to(WORKSPACE)}")
        else:
            problems.append(f"desfase: {path.relative_to(WORKSPACE)}")

    problems += [f"version suelta: {item}" for item in find_stray_literals()]
    if problems:
        print("\n".join(problems))
        return 1
    print(f"OK - suite {versions['suite']} / apk {versions['apk']} ({versions['apk_code']}) / nube {versions['nube_apk']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
