import json
import os
import hashlib
import shutil
import re

with open("sscp-desktop/VERSION.json", "r", encoding="utf-8") as vf:
    VER = json.load(vf)["apk"]

# 1. Update version badges to target version in sscp/public/mobile/index.html
index_path = "sscp/public/mobile/index.html"
with open(index_path, "r", encoding="utf-8") as f:
    html = f.read()

html = re.sub(r'>v\d+\.\d+\.\d+(?:-[a-zA-Z0-9._-]+)?<', f'>v{VER}<', html)

with open(index_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Updated version badges to v{VER} in sscp/public/mobile/index.html")

# 2. Update MainActivity.java
main_act_path = "sscp-mobile/app/src/main/java/com/sscp/mobile/MainActivity.java"
with open(main_act_path, "r", encoding="utf-8") as f:
    act_code = f.read()

act_code = re.sub(r'assets/www/index\.html\?v=[^"]+', f'assets/www/index.html?v={VER}', act_code)
with open(main_act_path, "w", encoding="utf-8") as f:
    f.write(act_code)
print(f"Updated MainActivity.java to v={VER}")

# 3. Update sscp/routes/pwa.php
pwa_path = "sscp/routes/pwa.php"
with open(pwa_path, "r", encoding="utf-8") as f:
    pwa_code = f.read()

pwa_code = re.sub(r"config\('release\.apk',\s*'[^']+'\)", f"config('release.apk', '{VER}')", pwa_code)
with open(pwa_path, "w", encoding="utf-8") as f:
    f.write(pwa_code)
print(f"Updated sscp/routes/pwa.php to {VER} fallback")

# 4. Copy to all replicas
targets = [
    "sscp-desktop/app/templates/mobile/index.html",
    "sscp-mobile/app/src/main/assets/www/index.html",
    "sscp-mobile/index.html",
    "sscp/resources/views/pwa/index.blade.php",
    "sscp/resources/views/mobile/index.blade.php"
]

if os.path.exists("sscp-mobile/app/src/main/assets/index.html"):
    targets.append("sscp-mobile/app/src/main/assets/index.html")

for t in targets:
    os.makedirs(os.path.dirname(t), exist_ok=True)
    shutil.copyfile(index_path, t)
    print(f"Copied to {t}")

# Verify checksums
print("\n--- Checksums ---")
for t in [index_path] + targets:
    with open(t, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    print(f"{h[:16]}... {t}")
