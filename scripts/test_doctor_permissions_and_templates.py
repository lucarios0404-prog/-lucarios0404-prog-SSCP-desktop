import sys
sys.path.insert(0, ".")
import json
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.models.user import User
from app.models.template import ClinicalTemplate
from main import app
from app.core.deps import require_current_user

db = SessionLocal()

print("=" * 60)
print("TEST 1: Doctor has templates permission always")
print("=" * 60)
doc = db.query(User).filter(User.email == "doctor@sscp.com").first()
# Test with permissions = None
doc.permissions = None
db.commit()
db.refresh(doc)
assert doc.has_permission("templates") == True, "Doctor must have templates permission"
print("  OK: Doctor with permissions=None has templates: True")

# Test with restricted permissions JSON that does NOT include templates
doc.permissions = json.dumps(["dashboard", "patients"])
db.commit()
db.refresh(doc)
assert doc.has_permission("templates") == True, "Doctor MUST have templates permission even if omitted in custom JSON"
print("  OK: Doctor with restricted JSON ['dashboard', 'patients'] still has templates: True (essential medical tool)")

# Test with settings permission granted
doc.permissions = json.dumps(["dashboard", "patients", "settings"])
db.commit()
db.refresh(doc)
assert doc.has_permission("settings") == True, "Doctor must have settings permission when granted"
assert doc.has_permission("templates") == True, "Doctor still has templates"
print("  OK: Doctor with granted 'settings' has settings: True and templates: True")

print("\n" + "=" * 60)
print("TEST 2: Doctor accessing /settings when granted permission")
print("=" * 60)
client = TestClient(app)

# Override current user to doctor with settings permission
app.dependency_overrides[require_current_user] = lambda: doc

resp = client.get("/settings")
assert resp.status_code == 200, f"Expected 200 for doctor with settings permission, got {resp.status_code}: {resp.text[:200]}"
assert "Parámetros generales de la clínica" in resp.text
print("  OK: Doctor with settings permission accesses /settings successfully (HTTP 200 - NO 403 / No 'Se requieren permisos de Administrador')")

# Test posting to /settings/ as doctor
save_resp = client.post("/settings/", data={
    "clinic_name": "Clínica Médica Especializada",
    "doctor_name": "Dr. Carlos Mendoza",
    "specialty": "Medicina Interna",
    "phone": "809-555-0100",
    "email": "doctor@sscp.com",
    "address": "Av. Principal 123",
    "currency": "RD$",
    "sede_name": "Sede Central",
    "sync_interval_minutes": "5"
}, follow_redirects=True)
assert save_resp.status_code == 200, f"Expected success saving settings, got {save_resp.status_code}"
print("  OK: Doctor with settings permission can save settings (NO 403)")

print("\n" + "=" * 60)
print("TEST 3: Doctor WITHOUT settings permission is properly restricted")
print("=" * 60)
# Doctor without settings
doc.permissions = json.dumps(["dashboard", "patients"])
db.commit()
db.refresh(doc)
resp_forbidden = client.get("/settings")
assert resp_forbidden.status_code == 403, f"Expected 403 for doctor without settings permission, got {resp_forbidden.status_code}"
print(f"  OK: Doctor without settings permission correctly blocked with HTTP 403: {resp_forbidden.json()['detail']}")

print("\n" + "=" * 60)
print("TEST 4: Doctor mounting clinical templates (/templates)")
print("=" * 60)
# Doctor accesses /templates
resp_tpl = client.get("/templates")
assert resp_tpl.status_code == 200, f"Expected 200, got {resp_tpl.status_code}"
assert "Plantillas Clínicas Predefinidas" in resp_tpl.text
print("  OK: Doctor accesses /templates successfully (HTTP 200)")

# Doctor creates a new template
create_tpl_resp = client.post("/templates/create", data={
    "title": "Protocolo Hipertensión Arterial Grado II",
    "category": "prescription",
    "content": "Losartán Potásico 50mg VO cada 12 horas por 30 días.\nAmlodipina 5mg VO cada 24 horas por la mañana.\nControl de presión arterial ambulatorio diario."
}, follow_redirects=True)
assert create_tpl_resp.status_code == 200
assert "Protocolo Hipertensión Arterial Grado II" in create_tpl_resp.text
print("  OK: Doctor successfully created a new clinical template")

# Get template ID
new_tpl = db.query(ClinicalTemplate).filter(ClinicalTemplate.title == "Protocolo Hipertensión Arterial Grado II").first()
assert new_tpl is not None
print(f"  OK: Template persisted in DB with ID: {new_tpl.id}")

# Doctor edits template
edit_tpl_resp = client.post(f"/templates/{new_tpl.id}/edit", data={
    "title": "Protocolo Hipertensión Arterial Grado II (Actualizado)",
    "category": "prescription",
    "content": "Losartán Potásico 100mg VO cada 24 horas.\nAmlodipina 5mg VO cada 24 horas.\nDieta baja en sodio."
}, follow_redirects=True)
assert edit_tpl_resp.status_code == 200
assert "Protocolo Hipertensión Arterial Grado II (Actualizado)" in edit_tpl_resp.text
db.refresh(new_tpl)
assert new_tpl.title == "Protocolo Hipertensión Arterial Grado II (Actualizado)"
print("  OK: Doctor successfully edited template and changes were updated")

# Doctor deletes test template
del_resp = client.post(f"/templates/{new_tpl.id}/delete", follow_redirects=True)
assert del_resp.status_code == 200
deleted_check = db.query(ClinicalTemplate).filter(ClinicalTemplate.id == new_tpl.id).first()
assert deleted_check is None
print("  OK: Doctor successfully deleted template")

# Reset doctor permissions back to defaults for clean state
doc.permissions = None
db.commit()
print("\n" + "=" * 60)
print("ALL TESTS PASSED WITH 100% SUCCESS!")
print("=" * 60)
app.dependency_overrides.clear()
db.close()
