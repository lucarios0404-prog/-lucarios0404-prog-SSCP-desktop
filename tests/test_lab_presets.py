import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import app  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.template import ClinicalTemplate  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routers.lab_results import LAB_SEEDED_MARKER_CATEGORY  # noqa: E402


def _doctor_client() -> TestClient:
    client = TestClient(app)
    with SessionLocal() as db:
        user = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        token = create_access_token(data={"email": user.email, "role": user.role})
    client.cookies.set("access_token", f"Bearer {token}")
    return client


def test_lab_presets_seed_create_edit_delete_and_restore_persistence():
    client = _doctor_client()

    # Limpiar plantillas de laboratorio previas en la BD aislada de pruebas
    with SessionLocal() as db:
        db.query(ClinicalTemplate).filter(
            ClinicalTemplate.category.in_(["lab", LAB_SEEDED_MARKER_CATEGORY])
        ).delete(synchronize_session=False)
        db.commit()

    # 1. Al consultar /lab-results/presets se siembran los 11 perfiles de fábrica en SQLite
    r_list = client.get("/lab-results/presets")
    assert r_list.status_code == 200
    data = r_list.json()
    assert data["ok"] is True
    initial_presets = data["presets"]
    assert len(initial_presets) == 11
    titles = [p["name"] for p in initial_presets]
    assert "🩺 Rutina General" in titles
    assert "🤰 1er Trimestre" in titles

    # 2. Crear nueva plantilla personalizada con estudios de checklist + other_tests
    r_create = client.post(
        "/lab-results/presets",
        json={
            "name": "Control Dra. Gómez 'Especial'",
            "tests": ["Hemograma Completo", "TSH", "T4 libre"],
            "other_tests": "Troponina I ultrasensible\nDímero D cuantitativo",
        },
    )
    assert r_create.status_code == 200
    created_payload = r_create.json()
    assert created_payload["ok"] is True
    custom_preset = created_payload["preset"]
    assert custom_preset["name"] == "Control Dra. Gómez 'Especial'"
    assert custom_preset["is_factory"] is False
    assert custom_preset["tests"] == [
        "Hemograma Completo",
        "TSH",
        "T4 libre",
        "Troponina I ultrasensible",
        "Dímero D cuantitativo",
    ]
    custom_id = custom_preset["id"]

    # 3. Editar la plantilla personalizada (cambiar nombre y quitar análisis)
    r_edit_custom = client.post(
        f"/lab-results/presets/{custom_id}/edit",
        json={
            "name": "Control Dra. Gómez Editado",
            "tests": ["Hemograma Completo", "TSH"],
        },
    )
    assert r_edit_custom.status_code == 200
    edited_custom = r_edit_custom.json()["preset"]
    assert edited_custom["name"] == "Control Dra. Gómez Editado"
    assert edited_custom["tests"] == ["Hemograma Completo", "TSH"]

    # 4. Editar un perfil de fábrica (ej. quitar un análisis de Rutina General)
    factory_rutina = next(p for p in initial_presets if "Rutina General" in p["name"])
    r_edit_factory = client.post(
        f"/lab-results/presets/{factory_rutina['id']}/edit",
        json={
            "name": "🩺 Rutina General Personalizada",
            "tests": ["Hemograma Completo", "Exámen de orina", "Glicemia en ayuna"],
        },
    )
    assert r_edit_factory.status_code == 200
    assert r_edit_factory.json()["preset"]["tests"] == [
        "Hemograma Completo",
        "Exámen de orina",
        "Glicemia en ayuna",
    ]

    # 5. Eliminar perfiles de fábrica que el médico NO necesita y verificar que NO reaparecen al recargar
    unwanted_factory = next(p for p in initial_presets if "Reumatológico" in p["name"])
    r_del_factory = client.post(f"/lab-results/presets/{unwanted_factory['id']}/delete")
    assert r_del_factory.status_code == 200
    remaining_ids = [p["id"] for p in r_del_factory.json()["presets"]]
    assert unwanted_factory["id"] not in remaining_ids

    # Recargar /lab-results y /lab-results/presets para confirmar que el eliminado NO vuelve a sembrarse
    r_reload = client.get("/lab-results/presets")
    assert r_reload.status_code == 200
    reloaded_names = [p["name"] for p in r_reload.json()["presets"]]
    assert "🦴 Reumatológico" not in reloaded_names
    assert "Control Dra. Gómez Editado" in reloaded_names

    # 6. Restaurar perfiles de fábrica faltantes conserva las plantillas personalizadas del médico
    r_restore = client.post("/lab-results/presets/restore-defaults")
    assert r_restore.status_code == 200
    restored_names = [p["name"] for p in r_restore.json()["presets"]]
    assert "🦴 Reumatológico" in restored_names
    assert "Control Dra. Gómez Editado" in restored_names

    # 7. Eliminar la plantilla personalizada
    r_del_custom = client.post(f"/lab-results/presets/{custom_id}/delete")
    assert r_del_custom.status_code == 200
    final_names = [p["name"] for p in r_del_custom.json()["presets"]]
    assert "Control Dra. Gómez Editado" not in final_names


def test_clinical_templates_lab_category_and_safe_edit_attributes():
    client = _doctor_client()

    # Verificar que la vista de /lab-results no contiene window.prompt() y renderiza el modal HTML
    r_labs = client.get("/lab-results")
    assert r_labs.status_code == 200
    html_labs = r_labs.text
    assert "modal-lab-preset" in html_labs
    assert "modal-delete-lab-preset" in html_labs
    assert "prompt(" not in html_labs

    # Verificar que /lab-results/create incluye todas las categorías de COMMON_TESTS
    r_create_view = client.get("/lab-results/create")
    assert r_create_view.status_code == 200
    for cat in ("Endocrinología", "Función Renal", "Parasitología"):
        assert f'<option value="{cat}">' in r_create_view.text

    # Verificar que /templates?category=lab muestra las plantillas de laboratorio sin exponer el marcador interno
    r_tpl = client.get("/templates?category=lab")
    assert r_tpl.status_code == 200
    assert "openEditTemplateModalFromBtn(this)" in r_tpl.text
    assert "__lab_presets_seeded_v1__" not in r_tpl.text

    r_api = client.get("/templates/api")
    assert r_api.status_code == 200
    api_titles = [item["title"] for item in r_api.json()]
    assert "__lab_presets_seeded_v1__" not in api_titles
