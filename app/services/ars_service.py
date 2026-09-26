"""Catálogo oficial de ARS (Aseguradoras de Riesgos de Salud de República Dominicana)
con logos vectoriales SVG de alta definición, colores institucionales y funciones de ayuda.
"""

ARS_LIST = [
    {
        "id": "privado",
        "name": "Privado / Particular",
        "short_name": "Privado",
        "color": "#64748b",
        "bg_color": "#f1f5f9",
        "border_color": "#cbd5e1",
        "text_color": "#334155",
        "icon": "user-tag",
        "svg": """<svg viewBox="0 0 24 24" fill="none" class="w-4 h-4 inline-block" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10" fill="#64748b"/><path d="M12 7v5l3 3" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>"""
    },
    {
        "id": "senasa_contributivo",
        "name": "SeNaSa (Contributivo)",
        "short_name": "SeNaSa Cont.",
        "color": "#00853f",
        "bg_color": "#ecfdf5",
        "border_color": "#a7f3d0",
        "text_color": "#065f46",
        "icon": "shield-heart",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#00853F"/><path d="M7 16c0-4.97 4.03-9 9-9s9 4.03 9 9-4.03 9-9 9-9-4.03-9-9z" fill="#00A859"/><path d="M11 16l3.5 3.5L21 13" stroke="#ffffff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
    },
    {
        "id": "senasa_subsidiado",
        "name": "SeNaSa (Subsidiado)",
        "short_name": "SeNaSa Sub.",
        "color": "#0284c7",
        "bg_color": "#f0f9ff",
        "border_color": "#bae6fd",
        "text_color": "#0369a1",
        "icon": "shield-heart",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#0284C7"/><path d="M16 6l8 4v7c0 5.25-3.4 10.15-8 11.5-4.6-1.35-8-6.25-8-11.5v-7l8-4z" fill="#38BDF8"/><path d="M12 16l3 3 5-5" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
    },
    {
        "id": "primera_ars",
        "name": "Primera ARS (Grupo Humano)",
        "short_name": "Primera ARS",
        "color": "#0080c9",
        "bg_color": "#f0fdf4",
        "border_color": "#86efac",
        "text_color": "#0369a1",
        "icon": "heart-pulse",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#0080C9"/><path d="M16 8c-4.4 0-8 3.6-8 8 0 5 8 11 8 11s8-6 8-11c0-4.4-3.6-8-8-8z" fill="#00C096"/><circle cx="16" cy="14" r="3" fill="#ffffff"/></svg>"""
    },
    {
        "id": "mapfre_bhd",
        "name": "Mapfre BHD Salud",
        "short_name": "Mapfre BHD",
        "color": "#d3122a",
        "bg_color": "#fef2f2",
        "border_color": "#fecaca",
        "text_color": "#991b1b",
        "icon": "plus-circle",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#D3122A"/><circle cx="16" cy="16" r="9" stroke="#ffffff" stroke-width="2.5"/><path d="M16 11v10M11 16h10" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"/></svg>"""
    },
    {
        "id": "universal",
        "name": "ARS Universal",
        "short_name": "Universal",
        "color": "#0033a0",
        "bg_color": "#eff6ff",
        "border_color": "#bfdbfe",
        "text_color": "#1e40af",
        "icon": "globe-americas",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#0033A0"/><circle cx="16" cy="16" r="9" fill="#0284C7"/><ellipse cx="16" cy="16" rx="9" ry="4" stroke="#ffffff" stroke-width="1.5"/><path d="M16 7v18" stroke="#ffffff" stroke-width="1.5"/></svg>"""
    },
    {
        "id": "monumental",
        "name": "ARS Monumental",
        "short_name": "Monumental",
        "color": "#0a3d62",
        "bg_color": "#f0f4f8",
        "border_color": "#cbd5e1",
        "text_color": "#0a3d62",
        "icon": "landmark",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#0A3D62"/><path d="M8 22h16M16 8l8 5H8l8-5zM11 13v7M16 13v7M21 13v7" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/></svg>"""
    },
    {
        "id": "renacer",
        "name": "ARS Renacer",
        "short_name": "Renacer",
        "color": "#ea580c",
        "bg_color": "#fff7ed",
        "border_color": "#fed7aa",
        "text_color": "#9a3412",
        "icon": "sun",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#EA580C"/><circle cx="16" cy="16" r="6" fill="#FDE047"/><path d="M16 6v3M16 23v3M6 16h3M23 16h3M9 9l2 2M21 21l2 2M9 23l2-2M21 11l2-2" stroke="#FDE047" stroke-width="2" stroke-linecap="round"/></svg>"""
    },
    {
        "id": "simag",
        "name": "ARS Simag",
        "short_name": "Simag",
        "color": "#0d9488",
        "bg_color": "#f0fdfa",
        "border_color": "#99f6e4",
        "text_color": "#115e59",
        "icon": "crosshairs",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#0D9488"/><circle cx="16" cy="16" r="8" stroke="#ffffff" stroke-width="2.5"/><circle cx="16" cy="16" r="3" fill="#ffffff"/></svg>"""
    },
    {
        "id": "yunen",
        "name": "ARS Yunen",
        "short_name": "Yunen",
        "color": "#1e3a8a",
        "bg_color": "#eff6ff",
        "border_color": "#bfdbfe",
        "text_color": "#1e3a8a",
        "icon": "hospital-user",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#1E3A8A"/><path d="M16 8a4 4 0 100 8 4 4 0 000-8zM9 24c0-3.5 3.5-6 7-6s7 2.5 7 6" stroke="#60A5FA" stroke-width="2.5" stroke-linecap="round"/></svg>"""
    },
    {
        "id": "futuro",
        "name": "ARS Futuro",
        "short_name": "Futuro",
        "color": "#7c3aed",
        "bg_color": "#f5f3ff",
        "border_color": "#ddd6fe",
        "text_color": "#5b21b6",
        "icon": "sparkles",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#7C3AED"/><path d="M16 6l3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7z" fill="#A78BFA"/></svg>"""
    },
    {
        "id": "reservas",
        "name": "ARS Reservas (Banreservas)",
        "short_name": "Reservas",
        "color": "#003865",
        "bg_color": "#f8fafc",
        "border_color": "#cbd5e1",
        "text_color": "#003865",
        "icon": "vault",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#003865"/><path d="M16 9l8 4v8l-8 4-8-4v-8l8-4z" stroke="#F59E0B" stroke-width="2.5" fill="#0F172A"/></svg>"""
    },
    {
        "id": "meta_salud",
        "name": "ARS Meta Salud",
        "short_name": "Meta Salud",
        "color": "#16a34a",
        "bg_color": "#f0fdf4",
        "border_color": "#bbf7d0",
        "text_color": "#15803d",
        "icon": "hand-holding-heart",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#16A34A"/><path d="M16 9c2-2 5-2 7 0s2 5 0 7l-7 7-7-7c-2-2-2-5 0-7s5-2 7 0z" fill="#ffffff"/></svg>"""
    },
    {
        "id": "asemap",
        "name": "ARS Asemap",
        "short_name": "Asemap",
        "color": "#2563eb",
        "bg_color": "#eff6ff",
        "border_color": "#bfdbfe",
        "text_color": "#1d4ed8",
        "icon": "shield",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#2563EB"/><path d="M16 7l8 3v7c0 5-3.5 9.5-8 11-4.5-1.5-8-6-8-11v-7l8-3z" stroke="#ffffff" stroke-width="2" fill="#3B82F6"/></svg>"""
    }
]

def get_all_ars():
    """Retorna la lista completa de ARS disponibles."""
    return ARS_LIST

def find_ars(name_or_id: str):
    """Busca y retorna los metadatos de una ARS por nombre o id."""
    if not name_or_id:
        return ARS_LIST[0] # Privado
    
    clean = name_or_id.strip().lower()
    for item in ARS_LIST:
        if clean == item["id"].lower() or clean == item["name"].lower() or clean == item["short_name"].lower():
            return item
        if clean in item["name"].lower() or item["short_name"].lower() in clean:
            return item
    
    # Si no coincide exactamente, retornar formato genérico pero elegante
    return {
        "id": "custom",
        "name": name_or_id.strip(),
        "short_name": name_or_id.strip()[:15],
        "color": "#475569",
        "bg_color": "#f8fafc",
        "border_color": "#e2e8f0",
        "text_color": "#334155",
        "icon": "id-card",
        "svg": """<svg viewBox="0 0 32 32" class="w-4 h-4 inline-block" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="32" height="32" rx="7" fill="#475569"/><path d="M10 12h12M10 16h8M10 20h5" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/></svg>"""
    }

def render_ars_badge_html(name_or_id: str, affiliate_number: str = None) -> str:
    """Genera el código HTML del badge con el logo de la ARS para Jinja2 / frontend."""
    info = find_ars(name_or_id)
    aff_text = f"""<span class="text-[10px] opacity-75 font-mono ml-1">#{affiliate_number}</span>""" if affiliate_number else ""
    return f"""<span class="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-xl text-xs font-bold shadow-xs border" style="background-color: {info['bg_color']}; color: {info['text_color']}; border-color: {info['border_color']};">{info['svg']}<span>{info['short_name']}</span>{aff_text}</span>"""
