import sys
from pathlib import Path
import json

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.routers.lab_results import LAB_PANELS
from app.services.pdf_service import (
    TALONARIO_LAB_COORDS,
    _NORMALIZED_LAB_COORDS,
    _normalize_lab_test_name,
    generate_lab_order_pdf,
    generate_lab_order_talonario_pdf
)

class MockPatient:
    id = 1
    first_name = "María"
    last_name = "Pérez"
    document_id = "001-1234567-8"
    gender = "F"
    birth_date = None
    age = 32

class MockDoctor:
    id = 1
    name = "Dr. Carlos M. Heredia"
    specialty = "Ginecología y Obstetricia"

class MockLabOrder:
    id = 999
    order_date = None
    patient = MockPatient()
    doctor = MockDoctor()
    clinical_indication = "Evaluación ecográfica e imagenología integral"
    notes = "Presentarse con vejiga llena para estudio pélvico."
    tests_requested = json.dumps([
        "Sonografía Pélvica",
        "Sonografía Transvaginal",
        "Sonografía Abdominal",
        "Sonografía Obstétrica",
        "Sonografía Morfológica",
        "Sonografía Genética",
        "Sonografía Perfil Hemodinámico",
        "Sonografía Doppler Placentario",
        "Sonomamografía",
        "Radiografía Pélvica",
        "Tomografía Abdominal",
        "Tomografía Pélvica",
    ])

def test_sonografia_configuration():
    print("=" * 60)
    print("VERIFICANDO PANEL Y ESTUDIOS DE SONOGRAFÍA E IMÁGENES")
    print("=" * 60)

    sono_panel = next((p for p in LAB_PANELS if p["category"] == "Sonografía"), None)
    assert sono_panel is not None, "Error: No se encontró el panel de Sonografía en LAB_PANELS"
    print(f"Panel encontrado: '{sono_panel['category']}' con {len(sono_panel['tests'])} estudios.")

    expected_tests = [
        "Sonografía Pélvica",
        "Sonografía Transvaginal",
        "Sonografía Abdominal",
        "Sonografía Obstétrica",
        "Sonografía Morfológica",
        "Sonografía Genética",
        "Sonografía Perfil Hemodinámico",
        "Sonografía Doppler Placentario",
        "Sonomamografía",
        "Radiografía Pélvica",
        "Tomografía Abdominal",
        "Tomografía Pélvica",
    ]

    assert len(sono_panel["tests"]) == 12, f"Se esperaban 12 estudios, se encontraron {len(sono_panel['tests'])}"

    for test in expected_tests:
        assert test in sono_panel["tests"], f"Estudio faltante en panel: {test}"
        print(f"  [OK] {test}")

    print("\nVerificando normalización y coordenadas en TALONARIO_LAB_COORDS...")
    for test in expected_tests:
        norm = _normalize_lab_test_name(test)
        assert norm in _NORMALIZED_LAB_COORDS, f"No se encontró coordenada normalizada para: {test} ({norm})"
        print(f"  [OK Coords] '{test}' -> norm '{norm}' -> {_NORMALIZED_LAB_COORDS[norm]}")

    print("\nProbando generación de PDF Carta (Full)...")
    order = MockLabOrder()
    pdf_full = generate_lab_order_pdf(order)
    content_full = pdf_full.getvalue()
    assert content_full.startswith(b"%PDF-"), "El PDF Carta no es válido"
    assert len(content_full) > 2000, "El PDF Carta es demasiado corto"
    print(f"  [OK] PDF Carta generado exitosamente ({len(content_full)} bytes).")

    print("\nProbando generación de PDF Talonario (13.6 x 21.7 cm)...")
    pdf_talo = generate_lab_order_talonario_pdf(order)
    content_talo = pdf_talo.getvalue()
    assert content_talo.startswith(b"%PDF-"), "El PDF Talonario no es válido"
    assert len(content_talo) > 2000, "El PDF Talonario es demasiado corto"
    print(f"  [OK] PDF Talonario generado exitosamente ({len(content_talo)} bytes).")

    print("\n" + "=" * 60)
    print("TODAS LAS PRUEBAS DE VERIFICACIÓN PASARON EXITOSAMENTE (100%)")
    print("=" * 60)

if __name__ == "__main__":
    test_sonografia_configuration()
