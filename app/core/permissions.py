"""
Sistema de Definición y Delimitación de Permisos y Roles para SSCP Desktop.
"""

AVAILABLE_PERMISSIONS = [
    {
        "key": "dashboard",
        "label": "Panel Principal & Métricas",
        "description": "Ver indicadores clave y accesos directos",
        "category": "General"
    },
    {
        "key": "patients",
        "label": "Expediente de Pacientes",
        "description": "Buscar, registrar y consultar fichas de pacientes",
        "category": "Atención"
    },
    {
        "key": "appointments",
        "label": "Gestión de Citas Médicas",
        "description": "Agendar, confirmar, reprogramar y cancelar citas",
        "category": "Atención"
    },
    {
        "key": "consultations",
        "label": "Consultas & Historias Clínicas",
        "description": "Crear y registrar diagnósticos, motivos de consulta y evolución",
        "category": "Clínica"
    },
    {
        "key": "prescriptions",
        "label": "Recetas Médicas Rápidas",
        "description": "Emitir prescripciones de medicamentos y generar PDF oficial",
        "category": "Clínica"
    },
    {
        "key": "templates",
        "label": "Plantillas Clínicas",
        "description": "Gestionar y cargar textos preconfigurados en consultas y recetas",
        "category": "Clínica"
    },
    {
        "key": "licenses",
        "label": "Licencias & Reposos Médicos",
        "description": "Emitir certificados de reposo laboral/escolar en PDF",
        "category": "Clínica"
    },
    {
        "key": "references",
        "label": "Cartas de Referencia Médica",
        "description": "Emitir derivaciones a otros especialistas médicos en PDF",
        "category": "Clínica"
    },
    {
        "key": "labs",
        "label": "Resultados de Laboratorio",
        "description": "Registrar y consultar órdenes e informes analíticos",
        "category": "Clínica"
    },
    {
        "key": "vaccines",
        "label": "Control de Vacunación",
        "description": "Registrar dosis y esquema de inmunizaciones",
        "category": "Clínica"
    },
    {
        "key": "payments",
        "label": "Facturación, Pagos & Caja",
        "description": "Cobro de servicios, emisión de recibos y saldos pendientes",
        "category": "Administración"
    },
    {
        "key": "inventory",
        "label": "Inventario & Insumos",
        "description": "Control de existencias, medicamentos e insumos médicos",
        "category": "Administración"
    },
    {
        "key": "messages",
        "label": "Mensajería Interna",
        "description": "Comunicación interna entre médicos, secretaría y administradores",
        "category": "General"
    },
    {
        "key": "reports",
        "label": "Reportes & Analítica Clínica",
        "description": "Estadísticas epidemiológicas, morbilidad y exportación Excel/CSV",
        "category": "Reportes"
    },
    {
        "key": "settings",
        "label": "Configuración de la Clínica",
        "description": "Datos del consultorio, membrete, dirección y conectividad",
        "category": "Sistema"
    },
    {
        "key": "users",
        "label": "Gestión de Usuarios & Permisos",
        "description": "Crear cuentas, asignar roles y delimitar accesos del personal",
        "category": "Sistema"
    },
    {
        "key": "sync",
        "label": "Sincronización Multi-sede",
        "description": "Administrar sincronización offline/online y red Tailscale",
        "category": "Sistema"
    }
]

DEFAULT_ROLE_PERMISSIONS = {
    "admin": [p["key"] for p in AVAILABLE_PERMISSIONS],
    "doctor": [
        "dashboard",
        "patients",
        "appointments",
        "consultations",
        "prescriptions",
        "templates",
        "licenses",
        "references",
        "labs",
        "vaccines",
        "inventory",
        "messages",
        "reports"
    ],
    "secretaria": [
        "dashboard",
        "patients",
        "appointments",
        "payments",
        "inventory",
        "messages"
    ]
}

ROLE_LABELS = {
    "admin": "Administrador General",
    "doctor": "Médico Especialista",
    "secretaria": "Secretaria / Recepción"
}
