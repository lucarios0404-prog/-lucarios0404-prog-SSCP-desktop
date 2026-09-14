# SSCP Desktop - Sistema de Seguimiento para Consultas de Pacientes

Aplicación de escritorio moderna y ligera desarrollada para la gestión médica y clínica en entornos locales sin dependencias externas obligatorias.

---

## 🚀 Características Principales

- **Gestión de Pacientes**: Expedientes médicos, antecedentes clínicos, historial y datos de contacto.
- **Consultas Médicas**: Registro de consultas, notas clínicas, diagnósticos y tratamientos.
- **Citas Médicas**: Programación, estados de citas (programada, atendida, cancelada) y calendario.
- **Signos Vitales**: Monitoreo de presión arterial, frecuencia cardíaca, temperatura, saturación de O2 y peso.
- **Laboratorios y Estudios**: Registro y seguimiento de resultados analíticos de laboratorio.
- **Control de Vacunación**: Esquema y registro de dosis aplicadas a pacientes.
- **Inventario Médico**: Catálogo de insumos/medicamentos, stock y registro de movimientos de entrada/salida.
- **Pagos y Facturación**: Registro de pagos, control de adeudos y balance.
- **Recetas e Informes en PDF**: Generación e impresión directa de recetas médicas oficiales con firma y membrete, e informes clínicos detallados en formato PDF.
- **Sincronización Offline / Online**: Conectividad bidireccional con el servidor central SSCP y exportación/importación de paquetes de datos portátiles (.json) para traslados vía USB.
- **Empaquetado Portable (.exe)**: Ejecutable nativo para Windows compilable con un solo clic (`build.bat`) sin requerir consola ni Python preinstalado.
- **Ajustes y Personalización**: Configuración del consultorio o clínica.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.10+ / FastAPI / Uvicorn
- **Base de Datos**: SQLite (mediante SQLAlchemy ORM y migraciones Alembic)
- **Frontend / Vistas**: Jinja2 Templates + HTML5 / CSS3 / JavaScript
- **Seguridad**: Autenticación JWT con tokens en cookies HTTP y hashing de contraseñas con Bcrypt

---

## 📦 Instalación y Puesta en Marcha

### 1. Requisitos Previos
- Python 3.10 o superior instalado en el sistema.
- Git instalado (opcional, para clonar el repositorio).

### 2. Inicio Rápido en Windows
Simplemente ejecuta el archivo por lotes:
```bat
start.bat
```
El script activará el entorno, levantará el servidor en el puerto 8080 y abrirá automáticamente tu navegador en `http://localhost:8080`.

### 3. Instalación Manual

1. **Crear entorno virtual**:
   ```bash
   python -m venv venv
   ```

2. **Activar entorno virtual**:
   - En Windows (PowerShell):
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - En Windows (CMD):
     ```cmd
     venv\Scripts\activate.bat
     ```
   - En Linux/macOS:
     ```bash
     source venv/bin/activate
     ```

3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Ejecutar migraciones de base de datos** (si es necesario):
   ```bash
   alembic upgrade head
   ```

5. **Crear usuario administrador inicial** (si la base de datos es nueva):
   ```bash
   python scripts/create_admin.py
   ```

6. **Iniciar la aplicación**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8080 --reload
   ```

### 4. Compilar Ejecutable Portable (.exe) para Windows

Para generar la versión portable lista para distribuir sin requerir Python:
```bat
build.bat
```
o mediante script:
```bash
python build_exe.py
```
El archivo ejecutable listo para usar se generará en: `dist/SSCP-Desktop/SSCP-Desktop.exe`.

---

## 🔐 Credenciales Iniciales

- **Usuario**: `admin@sscp.com`
- **Contraseña**: `password123`

*(Se recomienda cambiar las credenciales en el primer inicio de sesión desde el módulo de Ajustes).*

---

## 📁 Estructura del Proyecto

```
sscp-desktop/
├── alembic/              # Scripts y versiones de migración de base de datos
├── alembic.ini           # Configuración de Alembic
├── app/
│   ├── core/            # Configuración, seguridad y dependencias de auth
│   ├── models/          # Modelos SQLAlchemy (Patient, Consultation, Appointment, etc.)
│   ├── routers/         # Rutas y controladores FastAPI
│   ├── schemas/         # Esquemas de validación Pydantic
│   ├── services/        # Lógica de negocio
│   ├── templates/       # Vistas Jinja2 (HTML)
│   └── database.py      # Conexión y sesión de SQLite
├── data/
│   └── sscp.db          # Base de datos SQLite local
├── scripts/             # Scripts utilitarios (admin seed, pruebas de integración)
├── static/              # Archivos estáticos (CSS, JS, imágenes)
├── main.py              # Punto de entrada de la aplicación FastAPI
├── requirements.txt     # Dependencias de Python
└── start.bat            # Script de inicio rápido para Windows
```
