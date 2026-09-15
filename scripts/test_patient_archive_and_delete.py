import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.patient import Patient
from app.models.user import User
from app.models.consultation import Consultation
from app.models.appointment import Appointment
from app.models.payment import Payment
from app.models.vital_sign import VitalSign

def test_patient_archive_and_delete_flow():
    print("==================================================================")
    print("TEST: ARCHIVO CLÍNICO (SOFT DELETE) Y GOBERNANZA DE BORRADO ADMIN")
    print("==================================================================")

    db = SessionLocal()
    admin_client = TestClient(app)
    doc_client = TestClient(app)
    sec_client = TestClient(app)

    # 1. Autenticar clientes
    print("\n[1/7] Autenticando usuarios (Admin, Doctor, Secretaria)...")
    r_adm = admin_client.post("/login", data={"username": "admin@sscp.com", "password": "password123"}, follow_redirects=False)
    assert r_adm.status_code in [200, 302, 303], "Error al autenticar admin"

    r_doc = doc_client.post("/login", data={"username": "doctor@sscp.com", "password": "password123"}, follow_redirects=False)
    assert r_doc.status_code in [200, 302, 303], "Error al autenticar doctor"

    r_sec = sec_client.post("/login", data={"username": "secretaria@sscp.com", "password": "password123"}, follow_redirects=False)
    assert r_sec.status_code in [200, 302, 303], "Error al autenticar secretaria"
    print("  [OK] Sesiones autenticadas correctamente.")

    # 2. Crear paciente de prueba
    print("\n[2/7] Creando paciente de prueba...")
    unique_doc = f"TEST-{int(time.time())}"
    r_create = sec_client.post("/patients/create", data={
        "first_name": "PacientePrueba",
        "last_name": "ParaArchivar",
        "document_id": unique_doc,
        "date_of_birth": "1990-05-15",
        "phone": "8095550099",
        "email": "test.archivar@ejemplo.com"
    }, follow_redirects=False)
    assert r_create.status_code in [200, 302, 303]

    patient = db.query(Patient).filter(Patient.document_id == unique_doc).first()
    assert patient is not None, "El paciente debe existir en BD"
    assert patient.is_active is True or patient.is_active == 1, "El paciente nuevo debe ser activo"
    print(f"  [OK] Paciente creado con éxito (ID: {patient.id}, Activo: {patient.is_active})")

    # 3. Secretaria o Doctor archiva al paciente
    print("\n[3/7] Secretaria archiva al paciente con motivo...")
    archive_reason = "Registro de prueba duplicado"
    r_arch = sec_client.post(f"/patients/{patient.id}/archive", data={
        "reason": archive_reason
    }, follow_redirects=False)
    assert r_arch.status_code in [200, 302, 303], f"Error al archivar paciente: {r_arch.status_code}"

    db.refresh(patient)
    assert patient.is_active is False or patient.is_active == 0, "El paciente debe estar inactivo tras archivar"
    assert patient.archived_reason == archive_reason, "El motivo debe coincidir"
    assert patient.archived_at is not None, "Debe tener fecha de archivo registrada"
    print(f"  [OK] Paciente archivado correctamente (is_active={patient.is_active}, Motivo='{patient.archived_reason}')")

    # 4. Verificar que el paciente NO aparece en listas activas ni en selectores de consulta
    print("\n[4/7] Verificando que el paciente desapareció de las listas y selectores activos...")
    r_list_sec = sec_client.get(f"/patients?q={unique_doc}")
    assert r_list_sec.status_code == 200
    assert f"/patients/{patient.id}" not in r_list_sec.text, "El paciente archivado NO debe tener enlace en el listado activo"
    assert "No se encontraron pacientes" in r_list_sec.text, "El listado activo debe indicar que no se encontraron pacientes"

    r_cons_form = doc_client.get("/consultations/create")
    assert r_cons_form.status_code == 200
    assert f"PacientePrueba ParaArchivar" not in r_cons_form.text, "El paciente archivado NO debe aparecer en el selector de consultas"
    print("  [OK] Paciente oculto de la lista activa y de la selección de consultas.")

    # 5. Seguridad RBAC: Secretaria NO puede restaurar ni borrar permanentemente
    print("\n[5/7] Verificando seguridad RBAC (Secretaria bloqueada)...")
    r_sec_arch_list = sec_client.get("/patients?status=archived")
    assert r_sec_arch_list.status_code == 200
    assert "Vista de Archivados" not in r_sec_arch_list.text, "Secretaria no debe tener acceso a la vista de archivados"

    r_sec_restore = sec_client.post(f"/patients/{patient.id}/restore", follow_redirects=False)
    assert r_sec_restore.status_code == 403, f"Secretaria debe recibir 403 al intentar restaurar (obtuvo {r_sec_restore.status_code})"

    r_sec_del = sec_client.post(f"/patients/{patient.id}/permanent-delete", data={"confirm_text": "ELIMINAR"}, follow_redirects=False)
    assert r_sec_del.status_code == 403, f"Secretaria debe recibir 403 al intentar borrar permanentemente (obtuvo {r_sec_del.status_code})"
    print("  [OK] Seguridad RBAC confirmada: Secretaria bloqueada con HTTP 403 Forbidden.")

    # 6. Gobernanza Admin: Administrador ve archivados y restaura el paciente
    print("\n[6/7] Administrador consulta archivados y restaura el expediente...")
    r_adm_arch = admin_client.get(f"/patients?status=archived&q={unique_doc}")
    assert r_adm_arch.status_code == 200
    assert "Vista de Archivados" in r_adm_arch.text
    assert f"/patients/{patient.id}" in r_adm_arch.text, "El paciente archivado DEBE aparecer en la papelera del Admin"
    assert archive_reason in r_adm_arch.text, "El motivo debe ser visible para el Admin"

    r_adm_restore = admin_client.post(f"/patients/{patient.id}/restore", follow_redirects=False)
    assert r_adm_restore.status_code in [200, 302, 303]

    db.refresh(patient)
    assert patient.is_active is True or patient.is_active == 1, "El paciente debe volver al estado activo"
    assert patient.archived_reason is None, "El motivo de archivo debe limpiarse"

    # Verificar que ahora sí aparece en el listado activo
    r_list_restored = sec_client.get(f"/patients?q={unique_doc}")
    assert f"/patients/{patient.id}" in r_list_restored.text, "El paciente restaurado debe ser visible nuevamente"
    assert "No se encontraron pacientes" not in r_list_restored.text
    print("  [OK] Restauración exitosa por el Administrador. El paciente está activo y visible.")

    # 7. Eliminación permanente definitiva por el Administrador
    print("\n[7/7] Probando eliminación física permanente por el Administrador...")
    # Re-archivar
    sec_client.post(f"/patients/{patient.id}/archive", data={"reason": "Borrado final solicitado"})
    
    # Intentar borrar con texto de confirmación inválido
    r_bad_del = admin_client.post(f"/patients/{patient.id}/permanent-delete", data={"confirm_text": "borrar"}, follow_redirects=False)
    assert r_bad_del.status_code == 400, "Debe rechazar confirmación inválida con 400"

    # Borrado con confirmación 'ELIMINAR'
    r_good_del = admin_client.post(f"/patients/{patient.id}/permanent-delete", data={"confirm_text": "ELIMINAR"}, follow_redirects=False)
    assert r_good_del.status_code in [200, 302, 303]

    # Verificar en base de datos
    deleted_check = db.query(Patient).filter(Patient.id == patient.id).first()
    assert deleted_check is None, "El paciente debe haber sido eliminado completamente de la base de datos"
    print("  [OK] Eliminación permanente completada con éxito. Registro y dependencias purgados.")

    db.close()
    print("\n==================================================================")
    print("¡TODAS LAS PRUEBAS DE ARCHIVO Y GOBERNANZA DE BORRADO PASARON (7/7)!")
    print("==================================================================\n")

if __name__ == "__main__":
    test_patient_archive_and_delete_flow()
