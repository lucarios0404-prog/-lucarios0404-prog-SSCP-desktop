"""
Verification script: Brand assets, templates, and installer packaging validation.
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app

def test_brand_assets_and_templates():
    client = TestClient(app)
    
    # 1. Verify static icon and brand assets
    asset_paths = [
        "/static/app_icon.ico",
        "/static/favicon.ico",
        "/static/images/brand/logo-full-color.png",
        "/static/images/brand/icon-color.png",
        "/static/images/hero/hero-illustration.png",
    ]
    
    print("[1/3] Verifying static brand assets availability...")
    for path in asset_paths:
        res = client.get(path)
        assert res.status_code == 200, f"Failed to fetch {path}: status {res.status_code}"
        assert len(res.content) > 0, f"Asset {path} is empty"
        print(f"  [OK] {path} -> HTTP 200 ({len(res.content)} bytes)")

    # 2. Verify Login Page HTML template branding
    print("\n[2/3] Verifying Login Page HTML template branding...")
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "logo-full-color.png" in html, "Logo not found in login template"
    assert "app_icon.ico" in html or "favicon.ico" in html, "Favicon not linked in HTML"
    assert "SSCP" in html
    print("  [OK] Login template renders with full-color logo and favicon!")

    # 3. Verify Installer EXE file in dist/
    print("\n[3/3] Verifying Setup Installer executable...")
    base_dir = Path(__file__).resolve().parent.parent
    installer_exe = base_dir / "dist" / "SSCP_Desktop_Setup_v1.0.0.exe"
    assert installer_exe.exists(), "Installer EXE was not found in dist/"
    size_mb = installer_exe.stat().st_size / (1024 * 1024)
    assert size_mb > 20, f"Installer size looks suspiciously small: {size_mb} MB"
    print(f"  [OK] Installer exists: {installer_exe.name} ({size_mb:.2f} MB)")
    
    print("\n=======================================================")
    print("[ALL CHECKS PASSED] Brand assets and Setup installer verified!")
    print("=======================================================")

if __name__ == "__main__":
    test_brand_assets_and_templates()
