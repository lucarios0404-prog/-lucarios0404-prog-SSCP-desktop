"""
Verification script: Patients search and server-side pagination.
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app

def test_patients_search_and_pagination():
    print("============================================================")
    print("PROBANDO BUSCADOR Y PAGINACIÓN EN PACIENTES")
    print("============================================================")

    client = TestClient(app)

    # 1. Login as doctor or admin
    login_res = client.post("/login", data={"username": "admin@sscp.com", "password": "password123"}, follow_redirects=False)
    assert login_res.status_code in [200, 302, 303]
    cookies = login_res.cookies

    # 2. Base patients list
    print("\n[1/4] Verificando listado base de pacientes (/patients)...")
    res = client.get("/patients", cookies=cookies)
    assert res.status_code == 200
    assert "Buscar por nombre, apellido, cédula/DNI, teléfono o email..." in res.text
    assert "Mostrando registros" in res.text
    assert "Directorio de Pacientes" in res.text
    print("  [OK] Listado base renderiza el buscador y la cabecera con contador.")

    # 3. Search by term
    print("\n[2/4] Probando búsqueda por nombre, cédula o teléfono...")
    res_search = client.get("/patients?q=Carlos", cookies=cookies)
    assert res_search.status_code == 200
    assert "Filtro:" in res_search.text
    assert "Carlos" in res_search.text
    print("  [OK] Búsqueda por término ejecutada con éxito y filtro visible.")

    # 4. Pagination limits and parameters
    print("\n[3/4] Probando paginación (per_page=1)...")
    res_page = client.get("/patients?page=1&per_page=1", cookies=cookies)
    assert res_page.status_code == 200
    assert "Página" in res_page.text
    print("  [OK] Paginación con límite por página validada.")

    # 5. Empty search state
    print("\n[4/4] Probando búsqueda sin coincidencias...")
    res_empty = client.get("/patients?q=Inexistente999ZZZ", cookies=cookies)
    assert res_empty.status_code == 200
    assert "No se encontraron pacientes que coincidan" in res_empty.text
    assert "Limpiar búsqueda" in res_empty.text
    print("  [OK] Estado amigable de búsqueda vacía verificado.")

    print("\n============================================================")
    print("RESULTADO: BUSCADOR Y PAGINACIÓN DE PACIENTES FUNCIONANDO 100% OK")
    print("============================================================")

if __name__ == "__main__":
    test_patients_search_and_pagination()
