import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

def clean_tags():
    print("Iniciando limpieza de etiquetas técnicas (F...) en plantillas...")
    html_files = list(TEMPLATES_DIR.rglob("*.html"))
    modified_count = 0
    total_replacements = 0

    for file_path in html_files:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # 1. Casos específicos con texto interno
        content = content.replace("(F1: Atajos Rápidos)", "(Atajos Rápidos)")
        content = content.replace("(F3: Queda constancia en registro de auditoría)", "(Queda constancia en registro de auditoría)")
        content = content.replace("(Fase 6)", "")

        # 2. Casos con puntuación pegada
        content = re.sub(r'\s*\(F\d+\):', ':', content)
        content = re.sub(r'\s*\(F\d+\)!', '!', content)
        content = re.sub(r'\s*\(F\d+\)\.', '.', content)

        # 3. Casos generales con espacio previo: " (F12)" -> ""
        content = re.sub(r'[ \t]+\(F\d+\)', '', content)

        # 4. Casos restantes "(F12)" -> ""
        content = re.sub(r'\(F\d+\)', '', content)

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            modified_count += 1
            print(f"  -> Modificado: {file_path.relative_to(BASE_DIR)}")

    print(f"\nLimpieza completada: {modified_count} archivos actualizados.")

if __name__ == "__main__":
    clean_tags()
