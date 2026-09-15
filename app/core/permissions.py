"""
Sistema de Definición y Delimitación de Permisos y Roles para SSCP Desktop.
Los permisos se gestionan dinámicamente desde la BD (permissions_catalog).
Las constantes abajo sirven como seed inicial si la BD está vacía.
"""

# ── Seed inicial: se carga en BD al primer arranque ──────────────────────────
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
        "key": "print_prescriptions",
        "label": "Imprimir Recetas Médicas",
        "description": "Descargar e imprimir prescripciones médicas emitidas en PDF",
        "category": "Atención"
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
        "print_prescriptions",
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
        "print_prescriptions",
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


# ── Funciones DB-backed (con fallback a constantes) ─────────────────────────

def get_available_permissions(db=None) -> list[dict]:
    """
    Retorna los permisos activos desde la BD.
    Si db es None o la tabla está vacía, usa las constantes como fallback.
    """
    if db is None:
        return AVAILABLE_PERMISSIONS

    try:
        from app.models.permission_catalog import PermissionCatalog
        records = (
            db.query(PermissionCatalog)
            .filter(PermissionCatalog.is_active == True)
            .order_by(PermissionCatalog.category, PermissionCatalog.sort_order, PermissionCatalog.id)
            .all()
        )
        if not records:
            return AVAILABLE_PERMISSIONS
        return [
            {
                "key": r.key,
                "label": r.label,
                "description": r.description or "",
                "category": r.category,
            }
            for r in records
        ]
    except Exception:
        return AVAILABLE_PERMISSIONS


def get_all_permissions(db=None) -> list[dict]:
    """
    Retorna TODOS los permisos (activos e inactivos) desde la BD, para el panel de gestión.
    Incluye el campo is_active e id para gestión administrativa.
    """
    if db is None:
        return [dict(p, id=None, is_active=True) for p in AVAILABLE_PERMISSIONS]

    try:
        from app.models.permission_catalog import PermissionCatalog
        records = (
            db.query(PermissionCatalog)
            .order_by(PermissionCatalog.category, PermissionCatalog.sort_order, PermissionCatalog.id)
            .all()
        )
        if not records:
            return [dict(p, id=None, is_active=True) for p in AVAILABLE_PERMISSIONS]
        return [
            {
                "id": r.id,
                "key": r.key,
                "label": r.label,
                "description": r.description or "",
                "category": r.category,
                "sort_order": r.sort_order,
                "is_active": r.is_active,
            }
            for r in records
        ]
    except Exception:
        return [dict(p, id=None, is_active=True) for p in AVAILABLE_PERMISSIONS]


def get_permissions_by_category(db=None) -> dict[str, list[dict]]:
    """
    Retorna los permisos activos agrupados por Área/Categoría.
    """
    perms = get_all_permissions(db)
    grouped: dict[str, list] = {}
    for p in perms:
        cat = p["category"]
        grouped.setdefault(cat, []).append(p)
    return grouped


def seed_permissions_if_empty(db) -> None:
    """
    Inserta los permisos del catálogo estático en la BD si la tabla está vacía.
    Idempotente: no duplica si ya existen registros.
    """
    try:
        from app.models.permission_catalog import PermissionCatalog
        count = db.query(PermissionCatalog).count()
        if count > 0:
            return

        for idx, perm in enumerate(AVAILABLE_PERMISSIONS):
            record = PermissionCatalog(
                key=perm["key"],
                label=perm["label"],
                description=perm.get("description", ""),
                category=perm["category"],
                sort_order=idx,
                is_active=True,
            )
            db.add(record)
        db.commit()
        print(f"[Permissions Seed] {len(AVAILABLE_PERMISSIONS)} permisos cargados en la BD correctamente.")
    except Exception as e:
        print(f"[Permissions Seed] Aviso: {e}")
        db.rollback()


# ── Caché de permisos inactivos para validación en tiempo real ───────────────
_INACTIVE_PERMISSIONS_CACHE = None


def get_inactive_permission_keys(db=None) -> set[str]:
    """
    Retorna el conjunto de claves de permisos que han sido desactivados globalmente.
    Usa caché en memoria para no penalizar el rendimiento en cada verificación de permisos.
    """
    global _INACTIVE_PERMISSIONS_CACHE
    if _INACTIVE_PERMISSIONS_CACHE is not None:
        return _INACTIVE_PERMISSIONS_CACHE

    try:
        from app.models.permission_catalog import PermissionCatalog
        if db is not None:
            inactive = db.query(PermissionCatalog.key).filter(PermissionCatalog.is_active == False).all()
        else:
            from app.database import SessionLocal
            with SessionLocal() as session:
                inactive = session.query(PermissionCatalog.key).filter(PermissionCatalog.is_active == False).all()
        _INACTIVE_PERMISSIONS_CACHE = {r[0] for r in inactive}
    except Exception:
        _INACTIVE_PERMISSIONS_CACHE = set()

    return _INACTIVE_PERMISSIONS_CACHE


def invalidate_permissions_cache() -> None:
    """
    Invalida el caché cuando el administrador crea, edita, activa/desactiva o elimina un permiso.
    """
    global _INACTIVE_PERMISSIONS_CACHE
    _INACTIVE_PERMISSIONS_CACHE = None

