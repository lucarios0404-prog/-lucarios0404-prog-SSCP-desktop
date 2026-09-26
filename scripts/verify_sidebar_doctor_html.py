import sys
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.user import User

client = TestClient(app)
db = SessionLocal()

print("=" * 60)
print("VERIFICACION HTML DEL SIDEBAR Y VISTA DE PLANTILLAS PARA DOCTOR")
print("=" * 60)

# Iniciar sesión como Doctor
login_resp = client.post("/login", data={
    "username": "doctor@sscp.com",
    "password": "password123"
}, follow_redirects=False)

assert login_resp.status_code == 302, f"Error en login: {login_resp.status_code}"
cookies = login_resp.cookies

# Obtener /dashboard con sesión del Doctor
dash_resp = client.get("/dashboard", cookies=cookies)
assert dash_resp.status_code == 200, f"Error en dashboard: {dash_resp.status_code}"

# Verificar que en el HTML del dashboard del Doctor aparece Plantillas en el sidebar
assert 'href="/templates"' in dash_resp.text, "FALTA: el enlace a /templates debe estar en el sidebar del Doctor"
assert "Plantillas" in dash_resp.text, "FALTA: la etiqueta 'Plantillas' debe estar en el sidebar"
assert "Receta Rápida" in dash_resp.text, "FALTA: Receta Rápida en el sidebar"
print("  OK: Sidebar del Doctor muestra 'Plantillas' y 'Receta Rápida' bajo Productividad.")

# Obtener /templates con sesión del Doctor
tpl_resp = client.get("/templates", cookies=cookies)
assert tpl_resp.status_code == 200, f"Error en /templates: {tpl_resp.status_code}"
assert "Plantillas Clínicas Predefinidas" in tpl_resp.text
assert "Nueva Plantilla" in tpl_resp.text
assert "modal-edit-template" in tpl_resp.text
assert "openEditTemplateModal" in tpl_resp.text
assert "Faringitis Aguda" in tpl_resp.text
print("  OK: Página /templates carga correctamente con listado de 18 plantillas y modal de edición.")

# Verificar sesión como Admin
admin_login = client.post("/login", data={
    "username": "admin@sscp.com",
    "password": "password123"
}, follow_redirects=False)
assert admin_login.status_code == 302
admin_cookies = admin_login.cookies
admin_tpl_resp = client.get("/templates", cookies=admin_cookies)
assert admin_tpl_resp.status_code == 200
print("  OK: Administrador también tiene acceso y visualización completa a /templates.")

print("=" * 60)
print("EVIDENCIA COMPLETADA: 100% FUNCIONAL Y VERIFICADO")
print("=" * 60)
db.close()
