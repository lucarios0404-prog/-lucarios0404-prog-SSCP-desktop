import sys
sys.path.insert(0, ".")
from app.database import SessionLocal
from app.models.user import User
from app.models.permission_catalog import PermissionCatalog
import json

db = SessionLocal()
print("=== PERMISSIONS CATALOG ===")
for p in db.query(PermissionCatalog).all():
    print(f"  {p.key}: {p.label} (active={p.is_active})")

print("\n=== USERS ===")
for u in db.query(User).all():
    print(f"ID: {u.id}, Name: {u.name}, Email: {u.email}, Role: {u.role}")
    print(f"  Permissions field: {u.permissions}")
    print(f"  has_permission('templates'): {u.has_permission('templates')}")
    print(f"  has_permission('settings'): {u.has_permission('settings')}")
from app.models.template import ClinicalTemplate

print("\n=== CLINICAL TEMPLATES ===")
templates = db.query(ClinicalTemplate).all()
print(f"Total templates in DB: {len(templates)}")
for t in templates:
    print(f"  [{t.category}] ID: {t.id} - {t.title}")
db.close()
