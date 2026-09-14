"""
Script to generate standard Windows .ico file with all standard resolutions
from high-resolution brand images.
"""
from pathlib import Path
from PIL import Image

def generate():
    base_dir = Path(__file__).resolve().parent.parent
    src_png = base_dir / "static" / "images" / "brand" / "icon-color.png"
    if not src_png.exists():
        src_png = base_dir / "static" / "images" / "brand" / "logo-full-color.png"
    
    print(f"Source image: {src_png}")
    img = Image.open(src_png).convert("RGBA")
    
    # Save standard Windows icon sizes
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    out_ico = base_dir / "static" / "app_icon.ico"
    img.save(str(out_ico), format="ICO", sizes=sizes)
    print(f"[OK] Generated: {out_ico} ({out_ico.stat().st_size} bytes)")
    
    # Also overwrite static/favicon.ico with the proper format so browsers/tools don't choke
    fav_ico = base_dir / "static" / "favicon.ico"
    img.save(str(fav_ico), format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"[OK] Generated: {fav_ico} ({fav_ico.stat().st_size} bytes)")

if __name__ == "__main__":
    generate()
