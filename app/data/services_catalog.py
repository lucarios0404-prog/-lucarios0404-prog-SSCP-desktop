from sqlalchemy.orm import Session
from app.models.service import Service

# Catálogo oficial extraído directamente de la tablet de la clínica
INITIAL_SERVICES = [
    {"name": "Base liq Genius priv", "price": 5000.0, "color": "#9333ea", "category": "Laboratorio / Patología"},
    {"name": "Vacuna VPH", "price": 15500.0, "color": "#eab308", "category": "Vacunas"},
    {"name": "Base líquida", "price": 3500.0, "color": "#0ea5e9", "category": "Laboratorio / Patología"},
    {"name": "Base líquida privad", "price": 4500.0, "color": "#06b6d4", "category": "Laboratorio / Patología"},
    {"name": "Base líquida Genius", "price": 4000.0, "color": "#a855f7", "category": "Laboratorio / Patología"},
    {"name": "Biopsia", "price": 2000.0, "color": "#78350f", "category": "Procedimientos"},
    {"name": "Biopsia priv.", "price": 4500.0, "color": "#1e293b", "category": "Procedimientos"},
    {"name": "Colpo+bio priv.", "price": 7000.0, "color": "#ea580c", "category": "Procedimientos"},
    {"name": "Colposcopia+biopsia", "price": 5000.0, "color": "#d97706", "category": "Procedimientos"},
    {"name": "Cons+pap", "price": 2500.0, "color": "#ec4899", "category": "Consultas"},
    {"name": "Cons+pap privado", "price": 3500.0, "color": "#14b8a6", "category": "Consultas"},
    {"name": "Consulta", "price": 1000.0, "color": "#22c55e", "category": "Consultas"},
    {"name": "Consulta 50%", "price": 500.0, "color": "#3b82f6", "category": "Consultas"},
    {"name": "Consulta bola", "price": 0.0, "color": "#ef4444", "category": "Consultas"},
    {"name": "Consulta prenatal", "price": 1000.0, "color": "#f43f5e", "category": "Consultas"},
    {"name": "Consulta privada", "price": 2000.0, "color": "#dc2626", "category": "Consultas"},
    {"name": "Cribaje total", "price": 14000.0, "color": "#881337", "category": "Estudios Especiales"},
    {"name": "Diu", "price": 3000.0, "color": "#facc15", "category": "Planificación Familiar"},
    {"name": "Diu plata mini", "price": 5000.0, "color": "#10b981", "category": "Planificación Familiar"},
    {"name": "Implante", "price": 5000.0, "color": "#15803d", "category": "Planificación Familiar"},
    {"name": "Inyección", "price": 1500.0, "color": "#84cc16", "category": "Procedimientos"},
    {"name": "Resultados", "price": 500.0, "color": "#f97316", "category": "Revisiones"},
    {"name": "Resultados WhatsApp", "price": 0.0, "color": "#10b981", "category": "Revisiones"},
    {"name": "Retiro de metodo", "price": 2000.0, "color": "#eab308", "category": "Planificación Familiar"},
    {"name": "Retiro de sutura", "price": 500.0, "color": "#0f766e", "category": "Procedimientos"},
    {"name": "Seguimiento", "price": 0.0, "color": "#0f172a", "category": "Consultas"},
    {"name": "Tratamiento", "price": 0.0, "color": "#b91c1c", "category": "Procedimientos"},
]

def seed_services_if_empty(db: Session):
    """Pobla los servicios iniciales del talonario si la tabla está vacía o agrega los faltantes."""
    existing_count = db.query(Service).count()
    if existing_count == 0:
        for s in INITIAL_SERVICES:
            srv = Service(
                name=s["name"],
                price=s["price"],
                color=s["color"],
                category=s["category"],
                is_active=True
            )
            db.add(srv)
        db.commit()
        print(f"[Seed Services] Se crearon {len(INITIAL_SERVICES)} servicios iniciales del talonario.")
    else:
        # Asegurar que no falte ninguno de los 27
        added = 0
        for s in INITIAL_SERVICES:
            exists = db.query(Service).filter(Service.name == s["name"]).first()
            if not exists:
                srv = Service(
                    name=s["name"],
                    price=s["price"],
                    color=s["color"],
                    category=s["category"],
                    is_active=True
                )
                db.add(srv)
                added += 1
        if added > 0:
            db.commit()
            print(f"[Seed Services] Se agregaron {added} servicios faltantes al talonario.")
