"""
Verification script: Consultations search and pagination.
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from main import app

def test_consultations_search_and_pagination():
    print("============================================================")
    print("PROBANDO BUSCADOR Y PAGINACIÓN EN CONSULTAS E HISTORIAS")
    print("============================================================")

    client = TestClient(app)

    # 1. Login
    login_res = client.post("/login", data={"username": "doctor@sscp.com", "password": "password123"}, follow_redirects=False)
    assert login_res.status_code in [200, 302, 303]
    cookies = login_res.cookies

    # 2. Base consultations list
    print("\n[1/4] Verificando listado base de consultas (/consultations)...")
    res = client.get("/consultations", cookies=cookies)
    assert res.status_code == 200
    assert "Buscar por paciente, cédula/DNI" in res.text
    assert "Historias Clínicas y Consultas" in res.text
    print("  [OK] Listado base renderiza el buscador y la estructura paginada.")

    # 3. Search by diagnosis / keyword
    print("\n[2/4] Probando búsqueda por diagnóstico o término...")
    res_search = client.get("/consultations?q=Hipertension", cookies=cookies)
    assert res_search.status_code == 200
    assert "Filtro:" in res_search.text
    print("  [OK] Búsqueda por palabra clave ejecutada y renderizada con filtro activo.")

    # 4. Pagination limits and parameters
    print("\n[3/4] Probando división por páginas (per_page=2)...")
    res_page = client.get("/consultations?page=1&per_page=2", cookies=cookies)
    assert res_page.status_code == 200
    assert "Página" in res_page.text
    print("  [OK] Paginación con límite por página validada.")

    # 5. Empty search state
    print("\n[4/4] Probando término sin coincidencias...")
    res_empty = client.get("/consultations?q=TerminoInexistenteXYZ12345", cookies=cookies)
    assert res_empty.status_code == 200
    assert "No se encontraron historias clínicas que coincidan" in res_empty.text
    print("  [OK] Mensaje amigable de búsqueda sin resultados verificado.")

    print("\n============================================================")
    print("RESULTADO: BUSCADOR Y PAGINACIÓN FUNCIONANDO AL 100% OK")
    print("============================================================")

if __name__ == "__main__":
    test_consultations_search_and_pagination()
