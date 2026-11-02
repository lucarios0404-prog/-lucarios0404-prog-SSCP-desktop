import io
import os
import sys
from pathlib import Path
import json
import re
from datetime import datetime, date
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas as rl_canvas

PRIMARY_COLOR = colors.HexColor("#0f766e") # Teal 700
SECONDARY_COLOR = colors.HexColor("#0d9488") # Teal 600
TEXT_DARK = colors.HexColor("#1e293b") # Slate 800
TEXT_MUTED = colors.HexColor("#64748b") # Slate 500
BG_LIGHT = colors.HexColor("#f8fafc") # Slate 50
BORDER_COLOR = colors.HexColor("#cbd5e1") # Slate 300

def _get_styles():
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "ClinicTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=PRIMARY_COLOR,
    )
    
    subtitle_style = ParagraphStyle(
        "ClinicSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=TEXT_MUTED,
    )
    
    section_title = ParagraphStyle(
        "SectionTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=PRIMARY_COLOR,
        spaceAfter=4,
    )
    
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=TEXT_DARK,
    )
    
    body_bold = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=TEXT_DARK,
    )
    
    rx_style = ParagraphStyle(
        "PrescriptionText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        textColor=TEXT_DARK,
    )
    
    footer_style = ParagraphStyle(
        "FooterText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=TEXT_MUTED,
        alignment=1, # Centered
    )
    
    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "section": section_title,
        "body": body_style,
        "body_bold": body_bold,
        "rx": rx_style,
        "footer": footer_style,
    }

def _format_cedula(doc: str) -> str:
    """Formatea cédula dominicana a 000-0000000-0 si consta de 11 dígitos."""
    if not doc:
        return ""
    clean = re.sub(r"[^0-9a-zA-Z]", "", str(doc).strip())
    if len(clean) == 11 and clean.isdigit():
        return f"{clean[:3]}-{clean[3:10]}-{clean[10]}"
    return str(doc).strip()


def _extract_patient_display_data(patient) -> dict:
    """
    Extrae y formatea de forma ultra-robusta los datos del paciente para reportes y recetas,
    soportando instancias de SQLAlchemy Patient, diccionarios y objetos dinámicos.
    Garantiza que nunca falte la Cédula/DNI, Edad, ARS, ni salgan cadenas vacías o 'None'.
    """
    if not patient:
        return {
            "name": "Paciente General",
            "doc_id": "Sin Cédula Registrada",
            "has_doc": False,
            "age_str": "",
            "birth_date_str": "",
            "gender": "",
            "phone": "No registrado",
            "insurance_badge": "Privado / Particular",
            "allergies": "Ninguna registrada",
            "blood_type": "No registrado"
        }

    # 1. Nombre y Apellido
    fn = getattr(patient, "first_name", None) or (patient.get("first_name") if isinstance(patient, dict) else "") or ""
    ln = getattr(patient, "last_name", None) or (patient.get("last_name") if isinstance(patient, dict) else "") or ""
    nm = getattr(patient, "name", None) or (patient.get("name") if isinstance(patient, dict) else "") or getattr(patient, "full_name", None) or (patient.get("full_name") if isinstance(patient, dict) else "") or ""
    full_name = f"{str(fn).strip()} {str(ln).strip()}".strip() or str(nm).strip() or "Paciente"

    # 2. Cédula / Documento de identidad (búsqueda profunda en múltiples campos)
    raw_doc = (
        getattr(patient, "document_id", None)
        or (patient.get("document_id") if isinstance(patient, dict) else None)
        or getattr(patient, "cedula", None)
        or (patient.get("cedula") if isinstance(patient, dict) else None)
        or getattr(patient, "dni", None)
        or (patient.get("dni") if isinstance(patient, dict) else None)
        or getattr(patient, "id_card", None)
        or (patient.get("id_card") if isinstance(patient, dict) else None)
    )
    raw_doc_str = str(raw_doc).strip() if raw_doc is not None else ""
    if raw_doc_str and raw_doc_str.lower() not in ("none", "null", "n/d", "s/d", ""):
        doc_id = _format_cedula(raw_doc_str)
        has_doc = True
    else:
        pid = getattr(patient, "id", None) or (patient.get("id") if isinstance(patient, dict) else None)
        doc_id = f"Sin Cédula (Exp. #{pid})" if pid else "Sin Cédula Registrada"
        has_doc = False

    # 3. Fecha de nacimiento y cálculo exacto de edad (resuelve date_of_birth y birth_date)
    bdate = (
        getattr(patient, "date_of_birth", None)
        or (patient.get("date_of_birth") if isinstance(patient, dict) else None)
        or getattr(patient, "birth_date", None)
        or (patient.get("birth_date") if isinstance(patient, dict) else None)
    )
    age_str = ""
    birth_date_str = ""
    if bdate:
        try:
            if isinstance(bdate, str):
                bdate = datetime.strptime(str(bdate)[:10], "%Y-%m-%d").date()
            elif isinstance(bdate, datetime):
                bdate = bdate.date()
            birth_date_str = bdate.strftime("%d/%m/%Y")
            td = datetime.now().date()
            age = td.year - bdate.year - ((td.month, td.day) < (bdate.month, bdate.day))
            age_str = f"{age} años"
        except Exception:
            age_str = ""

    # 4. ARS / Seguro Médico
    ins_name = (
        getattr(patient, "insurance_name", None)
        or (patient.get("insurance_name") if isinstance(patient, dict) else None)
        or "Privado / Particular"
    )
    ins_num = (
        getattr(patient, "insurance_number", None)
        or (patient.get("insurance_number") if isinstance(patient, dict) else None)
        or ""
    )
    ins_badge = f"{ins_name} (No. {ins_num})" if ins_num else str(ins_name)

    # 5. Teléfono
    phone = (
        getattr(patient, "phone", None)
        or (patient.get("phone") if isinstance(patient, dict) else None)
        or getattr(patient, "mobile", None)
        or (patient.get("mobile") if isinstance(patient, dict) else None)
        or "No registrado"
    )

    # 6. Alergias
    allergies = (
        getattr(patient, "allergies", None)
        or (patient.get("allergies") if isinstance(patient, dict) else None)
        or "Ninguna registrada"
    )

    # 7. Tipo de Sangre
    blood_type = (
        getattr(patient, "blood_type", None)
        or (patient.get("blood_type") if isinstance(patient, dict) else None)
        or "No registrado"
    )

    # 8. Género
    gender = (
        getattr(patient, "gender", None)
        or (patient.get("gender") if isinstance(patient, dict) else None)
        or ""
    )

    return {
        "name": full_name,
        "doc_id": doc_id,
        "has_doc": has_doc,
        "age_str": age_str,
        "birth_date_str": birth_date_str,
        "gender": gender,
        "phone": phone,
        "insurance_badge": ins_badge,
        "allergies": allergies,
        "blood_type": blood_type
    }


def _get_page_setup(cfg: dict = None):
    """
    Retorna (pagesize, left_margin, right_margin, top_margin, bottom_margin, usable_width)
    basado en la configuración activa de print_config_service.
    """
    if cfg is None:
        try:
            from app.services.print_config_service import get_print_config
            cfg = get_print_config()
        except Exception:
            cfg = {}

    std_margins = cfg.get("standard_margins", {}) if isinstance(cfg, dict) else {}
    top_mm = float(std_margins.get("top", cfg.get("print_margin_top", 15.0)) or 15.0)
    bottom_mm = float(std_margins.get("bottom", cfg.get("print_margin_bottom", 15.0)) or 15.0)
    left_mm = float(std_margins.get("left", cfg.get("print_margin_left", 20.0)) or 20.0)
    right_mm = float(std_margins.get("right", cfg.get("print_margin_right", 15.0)) or 15.0)
    
    paper_size_name = str(std_margins.get("paperSize", cfg.get("print_paper_size", "Letter"))).strip().lower()
    
    if paper_size_name in ("halfletter", "media carta", "halfcarta", "half_letter"):
        try:
            from reportlab.lib.pagesizes import HALF_LETTER as halfletter
            pagesize = halfletter
        except Exception:
            pagesize = (5.5 * inch, 8.5 * inch)
    elif paper_size_name in ("a4",):
        from reportlab.lib.pagesizes import A4
        pagesize = A4
    elif paper_size_name in ("talonario", "custom_talonario"):
        w = float(cfg.get("paper_width_mm", 136.0) or 136.0) * mm
        h = float(cfg.get("paper_height_mm", 217.0) or 217.0) * mm
        pagesize = (w, h)
    else:
        from reportlab.lib.pagesizes import letter
        pagesize = letter
        
    left_margin = left_mm * mm
    right_margin = right_mm * mm
    top_margin = top_mm * mm
    bottom_margin = bottom_mm * mm
    
    page_w, page_h = pagesize
    usable_width = page_w - left_margin - right_margin
    # Proteger contra desbordes si el margen configurado es muy grande
    if usable_width < 2.5 * inch:
        usable_width = page_w - (30 * mm)
        left_margin = 15 * mm
        right_margin = 15 * mm

    return pagesize, left_margin, right_margin, top_margin, bottom_margin, usable_width


def _resolve_doctor_logo(setting=None):
    """
    Resuelve la ruta física del logo médico oficial:
    1. Si el médico cargó un logo propio en settings y existe el archivo físico en disco, lo retorna.
    2. Si no se ha configurado logo personalizado o fue restablecido, retorna el logo oficial por defecto (Dr. Carlos Miguel Heredia Jorge).
    3. Retorna None si no se encuentra ninguno.
    """
    if setting and getattr(setting, "doctor_logo_path", None):
        custom_p = setting.doctor_logo_path
        if custom_p and os.path.isfile(custom_p):
            return custom_p

    base_proj = Path(sys._MEIPASS).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent.parent
    default_logo = base_proj / "static" / "images" / "logo_dr_heredia_bw.png"
    if default_logo.exists():
        return str(default_logo)

    default_alt = base_proj / "static" / "images" / "logo_dr_heredia_bw_transparent.png"
    if default_alt.exists():
        return str(default_alt)

    return None


def _build_letterhead(story: list, styles: dict, setting=None, subtitle_text: str = "", usable_width: float = None) -> None:
    """
    Construye el membrete profesional del consultorio con logo opcional,
    adaptando su ancho exactamente al área imprimible configurada.
    """
    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    phone = getattr(setting, "phone", "") if setting else ""
    email = getattr(setting, "email", "") if setting else ""
    logo_path = _resolve_doctor_logo(setting)

    # Columna derecha: nombre, especialidad, tel
    right_text = f"<b>{doctor_name}</b><br/>{specialty}"
    if phone:
        right_text += f"<br/>Tel: {phone}"
    if email:
        right_text += f"<br/>{email}"
    if subtitle_text:
        right_text += f"<br/><font size=9 color='#0d9488'><b>{subtitle_text}</b></font>"

    right_col = Paragraph(right_text, styles["subtitle"])

    # Columna izquierda: logo (si existe) + nombre de clínica
    if logo_path and os.path.isfile(logo_path):
        try:
            logo_img = Image(logo_path, width=1.1 * inch, height=1.1 * inch)
            logo_img.hAlign = 'LEFT'
            left_content = [
                [logo_img, Paragraph(f"<b>{clinic_name}</b>", styles["title"])]
            ]
            left_table = Table(left_content, colWidths=[1.2 * inch, 2.3 * inch])
            left_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ]))
            left_col = left_table
        except Exception:
            left_col = Paragraph(f"<b>{clinic_name}</b>", styles["title"])
    else:
        left_col = Paragraph(f"<b>{clinic_name}</b>", styles["title"])

    if usable_width is None:
        usable_width = 7.0 * inch

    col1 = usable_width * 0.55
    col2 = usable_width * 0.45
    header_table = Table([[left_col, right_col]], colWidths=[col1, col2])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR, spaceBefore=2, spaceAfter=8))


def generate_prescription_pdf(consultation, setting=None) -> io.BytesIO:
    """
    Genera el PDF oficial de Receta Médica (Prescription) con formato médico profesional,
    respetando exactamente los márgenes y tamaño de papel configurados por el usuario,
    y garantizando que nunca falte la cédula, edad, ARS ni datos del paciente.
    """
    pagesize, left_m, right_m, top_m, bottom_m, usable_w = _get_page_setup()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    
    styles = _get_styles()
    story = []

    # 1. Membrete adaptativo
    _build_letterhead(story, styles, setting, subtitle_text="", usable_width=usable_w)

    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    address = getattr(setting, "address", "") if setting else ""

    # 2. Información del Paciente (Extracción robusta sin campos vacíos ni 'None')
    patient = getattr(consultation, "patient", None)
    p_info = _extract_patient_display_data(patient)
    consultation_date = (
        consultation.created_at.strftime("%d/%m/%Y %H:%M")
        if getattr(consultation, "created_at", None)
        else datetime.now().strftime("%d/%m/%Y")
    )
    
    patient_info_data = [
        [
            Paragraph(f"<b>Paciente:</b> {p_info['name']} &nbsp;•&nbsp; <b>Cédula/DNI:</b> {p_info['doc_id']}", styles["body"]),
            Paragraph(f"<b>Fecha:</b> {consultation_date}", styles["body"])
        ],
        [
            Paragraph(f"<b>Edad:</b> {p_info['age_str'] or 'No registrada'} &nbsp;•&nbsp; <b>Tel:</b> {p_info['phone']}", styles["body"]),
            Paragraph(f"<b>ARS/Cobertura:</b> {p_info['insurance_badge']}", styles["body"])
        ]
    ]

    # Alerta de alergias si existen
    if p_info.get("allergies") and p_info["allergies"].strip().lower() not in ("ninguna", "ninguna registrada", "no", "n/a", "no registrada", ""):
        patient_info_data.append([
            Paragraph(f"<font color='#b91c1c'><b>⚠️ Alergias Conocidas:</b> {p_info['allergies']}</font>", styles["body"]),
            Paragraph(f"<b>Consulta:</b> #{getattr(consultation, 'id', '—')}", styles["body"])
        ])

    p_table = Table(patient_info_data, colWidths=[usable_w * 0.65, usable_w * 0.35])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(p_table)
    story.append(Spacer(1, 10))
    
    # 3. Diagnóstico (si existe)
    if getattr(consultation, "diagnosis", None) and consultation.diagnosis.strip():
        story.append(Paragraph("<b>Diagnóstico:</b>", styles["section"]))
        story.append(Paragraph(consultation.diagnosis.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 8))
        
    # 4. Símbolo Rp. y Prescripción Médica
    story.append(Paragraph("<b>Rp. / Medicación y Prescripción</b>", styles["section"]))
    
    rx_content = consultation.prescription or "Sin medicamentos prescritos registrados."
    rx_formatted = rx_content.replace("\n", "<br/>")
    
    rx_table = Table([[Paragraph(rx_formatted, styles["rx"])]], colWidths=[usable_w])
    rx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdfa")), # Teal 50
        ('BOX', (0, 0), (-1, -1), 1, SECONDARY_COLOR),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(rx_table)
    story.append(Spacer(1, 10))
    
    # 5. Indicaciones Generales y Tratamiento (si existe)
    if getattr(consultation, "treatment", None) and consultation.treatment.strip():
        story.append(Paragraph("<b>Indicaciones Generales y Cuidados:</b>", styles["section"]))
        story.append(Paragraph(consultation.treatment.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 10))
        
    # 6. Bloque de Firma y Sello Médico (compacto y proporcionado para no desbordar)
    story.append(Spacer(1, 14))
    signature_block = [
        [
            Paragraph(f"<font size=8 color='#64748b'>{address}</font>", styles["body"]),
            Paragraph(f"________________________________________<br/><b>{doctor_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_table = Table(signature_block, colWidths=[usable_w * 0.52, usable_w * 0.48])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether(sig_table))
    
    # 7. Pie de página
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceBefore=2, spaceAfter=4))
    story.append(Paragraph("Documento médico oficial generado desde SSCP Desktop • Validez local", styles["footer"]))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_consultation_report_pdf(consultation, setting=None, vitals=None) -> io.BytesIO:
    """
    Genera el informe clínico detallado de la consulta médica en formato PDF,
    respetando la configuración de márgenes y tamaño de papel.
    """
    pagesize, left_m, right_m, top_m, bottom_m, usable_w = _get_page_setup()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    
    styles = _get_styles()
    story = []

    # Membrete con logo opcional
    _build_letterhead(story, styles, setting, subtitle_text="INFORME DE CONSULTA CLÍNICA", usable_width=usable_w)

    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"

    # Datos Paciente extraídos de forma robusta
    patient = getattr(consultation, "patient", None)
    p_info = _extract_patient_display_data(patient)
    consultation_date = (
        consultation.created_at.strftime("%d/%m/%Y %H:%M")
        if getattr(consultation, "created_at", None)
        else datetime.now().strftime("%d/%m/%Y")
    )
    
    p_data = [
        [
            Paragraph(f"<b>Paciente:</b> {p_info['name']}", styles["body"]),
            Paragraph(f"<b>Cédula/DNI:</b> {p_info['doc_id']}", styles["body"]),
            Paragraph(f"<b>Fecha:</b> {consultation_date}", styles["body"]),
        ],
        [
            Paragraph(f"<b>Edad:</b> {p_info['age_str'] or 'No registrada'}", styles["body"]),
            Paragraph(f"<b>ARS/Cobertura:</b> {p_info['insurance_badge']}", styles["body"]),
            Paragraph(f"<b>Consulta ID:</b> #{consultation.id}", styles["body"]),
        ],
        [
            Paragraph(f"<b>Grupo Sanguíneo:</b> {p_info['blood_type']}", styles["body"]),
            Paragraph(f"<b>Alergias:</b> <font color='#b91c1c'>{p_info['allergies']}</font>", styles["body"]),
            Paragraph(f"<b>Teléfono:</b> {p_info['phone']}", styles["body"]),
        ]
    ]
    col_w1 = usable_w * 0.38
    col_w2 = usable_w * 0.34
    col_w3 = usable_w * 0.28
    patient_table = Table(p_data, colWidths=[col_w1, col_w2, col_w3])
    patient_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(patient_table)
    story.append(Spacer(1, 10))
    
    # Signos Vitales (si se proporcionaron)
    if vitals:
        story.append(Paragraph("<b>Signos Vitales Registrados</b>", styles["section"]))
        v_data = [
            ["Peso", "Talla", "T/A (PA)", "F.C.", "Temp.", "Sat O2", "IMC"],
            [
                f"{getattr(vitals, 'weight_kg', 'N/A')} kg",
                f"{getattr(vitals, 'height_cm', 'N/A')} cm",
                f"{getattr(vitals, 'systolic_bp', '-')}/{getattr(vitals, 'diastolic_bp', '-')}",
                f"{getattr(vitals, 'heart_rate', 'N/A')} lpm",
                f"{getattr(vitals, 'temperature_c', 'N/A')} °C",
                f"{getattr(vitals, 'oxygen_saturation', 'N/A')} %",
                f"{getattr(vitals, 'bmi', 'N/A')}",
            ]
        ]
        vt_col = usable_w / 7.0
        vt_table = Table(v_data, colWidths=[vt_col] * 7)
        vt_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(vt_table)
        story.append(Spacer(1, 10))
        
    # Secciones de la consulta adaptadas a Historia Clínica Unificada (v1.2.0)
    sections = [
        ("Motivo de Consulta", getattr(consultation, "reason", "")),
    ]
    if getattr(consultation, "clinical_history", None) and consultation.clinical_history.strip():
        sections.append(("Historia Clínica / Evolución Médica", consultation.clinical_history))
    else:
        if getattr(consultation, "symptoms", None):
            sections.append(("Síntomas / Anamnesis", consultation.symptoms))
        if getattr(consultation, "physical_exam", None):
            sections.append(("Examen Físico", consultation.physical_exam))

    if getattr(consultation, "diagnosis", None) and consultation.diagnosis.strip() and consultation.diagnosis.strip() not in ("Historia Clínica Unificada", "Ver Historia Clínica"):
        sections.append(("Diagnóstico Clínico / CIE-10", consultation.diagnosis))

    sections.extend([
        ("Plan Terapéutico y Tratamiento", getattr(consultation, "treatment", "")),
        ("Prescripción Médica (Medicamentos)", getattr(consultation, "prescription", "")),
        ("Notas Clínicas Adicionales", getattr(consultation, "notes", "")),
    ])

    for title, content in sections:
        if content and str(content).strip():
            story.append(Paragraph(f"<b>{title}:</b>", styles["section"]))
            story.append(Paragraph(str(content).replace("\n", "<br/>"), styles["body"]))
            story.append(Spacer(1, 8))
            
    # Firma
    story.append(Spacer(1, 16))
    sig_data = [
        [
            "",
            Paragraph(f"<br/><br/>________________________________________<br/><b>{doctor_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_t = Table(sig_data, colWidths=[usable_w * 0.55, usable_w * 0.45])
    sig_t.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(KeepTogether(sig_t))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_quick_prescription_pdf(patient, prescription_text: str, diagnosis: str = None, setting=None, doctor_name: str = None) -> io.BytesIO:
    """
    Genera el PDF de Receta Rápida (F2) sin necesidad de una consulta médica completa,
    respetando los márgenes y tamaño de papel configurados en el sistema.
    """
    pagesize, left_m, right_m, top_m, bottom_m, usable_w = _get_page_setup()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    styles = _get_styles()
    story = []

    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doc_name = doctor_name or (getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista")
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    phone = getattr(setting, "phone", "") if setting else ""
    email = getattr(setting, "email", "") if setting else ""
    address = getattr(setting, "address", "") if setting else ""

    # Membrete con logo opcional (para receta rápida usamos un setting temporal)
    class _TmpSetting:
        pass
    tmp = _TmpSetting()
    tmp.clinic_name = clinic_name
    tmp.doctor_name = doc_name
    tmp.specialty = specialty
    tmp.phone = phone
    tmp.email = email
    tmp.doctor_logo_path = getattr(setting, "doctor_logo_path", None) if setting else None

    _build_letterhead(story, styles, tmp, subtitle_text="RECETA MÉDICA DIRECTA", usable_width=usable_w)

    # Paciente con extracción robusta
    p_info = _extract_patient_display_data(patient)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    p_data = [
        [
            Paragraph(f"<b>Paciente:</b> {p_info['name']} &nbsp;•&nbsp; <b>Cédula/DNI:</b> {p_info['doc_id']}", styles["body"]),
            Paragraph(f"<b>Fecha:</b> {now_str}", styles["body"])
        ],
        [
            Paragraph(f"<b>Edad:</b> {p_info['age_str'] or 'No registrada'} &nbsp;•&nbsp; <b>Tel:</b> {p_info['phone']}", styles["body"]),
            Paragraph(f"<b>ARS/Cobertura:</b> {p_info['insurance_badge']}", styles["body"])
        ]
    ]

    if p_info.get("allergies") and p_info["allergies"].strip().lower() not in ("ninguna", "ninguna registrada", "no", "n/a", "no registrada", ""):
        p_data.append([
            Paragraph(f"<font color='#b91c1c'><b>⚠️ Alergias Conocidas:</b> {p_info['allergies']}</font>", styles["body"]),
            Paragraph(f"<b>Tipo:</b> Emisión Rápida", styles["body"])
        ])

    ptable = Table(p_data, colWidths=[usable_w * 0.65, usable_w * 0.35])
    ptable.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(ptable)
    story.append(Spacer(1, 10))

    # Diagnóstico
    if diagnosis and diagnosis.strip():
        story.append(Paragraph("<b>Diagnóstico / Indicación Clínica:</b>", styles["section"]))
        story.append(Paragraph(diagnosis.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 8))

    # Prescripción
    story.append(Paragraph("<b>Rp. / Medicación y Prescripción</b>", styles["section"]))
    rx_fmt = (prescription_text or "Sin prescripción").replace("\n", "<br/>")
    rx_t = Table([[Paragraph(rx_fmt, styles["rx"])]], colWidths=[usable_w])
    rx_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
        ('BOX', (0, 0), (-1, -1), 1, SECONDARY_COLOR),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(rx_t)

    # Firma compacta y proporcionada
    story.append(Spacer(1, 16))
    sig_data = [
        [
            Paragraph(f"<font size=8 color='#64748b'>{address}</font>", styles["body"]),
            Paragraph(f"________________________________________<br/><b>{doc_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_t = Table(sig_data, colWidths=[usable_w * 0.52, usable_w * 0.48])
    sig_t.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'CENTER')]))
    story.append(KeepTogether(sig_t))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_medical_license_pdf(license, setting=None) -> io.BytesIO:
    """
    Genera el Certificado / Licencia Médica Oficial en formato optimizado
    para impresora blanco y negro, con logo invertido centrado, membrete médico
    oficial de Ginecología & Obstetricia, datos del paciente y firma.
    """
    # Certificado / Licencia Médica Oficial en PDF es SIEMPRE en formato Hoja Carta (Letter 8.5 × 11 pulg)
    pagesize = letter
    left_m = 0.85 * inch
    right_m = 0.85 * inch
    top_m = 0.65 * inch
    bottom_m = 0.65 * inch
    page_w, page_h = letter
    usable_w = page_w - left_m - right_m

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    styles = _get_styles()
    story = []

    # 1. LOGO OFICIAL CENTRADO PARA IMPRESIÓN B/N (EN FORMATO GRANDE)
    logo_path = _resolve_doctor_logo(setting)

    if logo_path and os.path.isfile(logo_path):
        try:
            # Proporción exacta 980 x 514 px (1.906 : 1)
            # En Hoja Carta Oficial, el logo centrado sale en tamaño grande (4.8 pulg / 12.2 cm de ancho)
            logo_w = 4.8 * inch
            logo_h = 2.52 * inch
            logo_img = Image(logo_path, width=logo_w, height=logo_h)
            logo_img.hAlign = 'CENTER'
            story.append(logo_img)
            story.append(Spacer(1, 14))
        except Exception:
            pass

    # 2. DESTINATARIO / TÍTULO CENTRADO
    dest = (getattr(license, "workplace_or_school", None) or "A quien pueda interesar").strip()
    dest_style = ParagraphStyle(
        "CertDestTitle",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        alignment=1, # Centrado
        textColor=colors.black,
        spaceAfter=14,
    )
    story.append(Paragraph(f"<b>{dest}</b>", dest_style))
    story.append(Spacer(1, 12))

    # 3. DATOS DEL DOCTOR Y DEL PACIENTE
    patient = getattr(license, "patient", None)
    p_info = _extract_patient_display_data(patient)
    doctor_name = getattr(setting, "doctor_name", "Dr. Carlos Miguel Heredia Jorge") if setting else "Dr. Carlos Miguel Heredia Jorge"
    specialty = getattr(setting, "specialty", "Ginecólogo Obstetra") if setting else "Ginecólogo Obstetra"
    exequatur = getattr(setting, "doctor_exequatur", "165-10") if setting else "165-10"
    cedula = getattr(setting, "doctor_cedula", "001-1418378-3") if setting else "001-1418378-3"

    prefix = "la Sra." if p_info.get("gender", "").lower() in ["f", "femenino"] else "el Sr./la Sra."
    patient_name = p_info["name"]
    doc_id = p_info["doc_id"]
    doc_part = f"ced {doc_id}" if doc_id and doc_id != "Sin documento" else ""

    # 4. CUERPO DE LA CERTIFICACIÓN
    notes_text = (getattr(license, "notes", None) or "").strip()

    body_style = ParagraphStyle(
        "CertBodyText",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=11,
        leading=17,
        alignment=4, # Justificado
        textColor=colors.black,
        spaceAfter=14,
    )

    if notes_text.lower().startswith("yo dr.") or "certifico haber examinado" in notes_text.lower():
        full_cert = notes_text
    else:
        if notes_text:
            narrative = notes_text
        else:
            narrative = (
                f"la cual cursando con un embarazo pre-término, paciente refiere sentirse imposibilitada "
                f"para realizar su jornada actual, con dicho químico y soldadura ya que estas liberan partículas "
                f"al inhalar los gases metales calentados (como el oro, la plata o las aleaciones con níquel) "
                f"liberan partículas microscópicas. La inhalación constante de vapores metálicos puede ser perjudicial "
                f"para el desarrollo fetal, por lo que consideramos que la misma sea colocada en otro lugar dentro "
                f"de la empresa donde pueda desarrollar dichas labores."
            )
        
        full_cert = (
            f"Yo <b>{doctor_name.upper()}</b>, <b>{specialty.upper()}</b> Exequátur <b>{exequatur}</b> "
            f"Cédula # <b>{cedula}</b> Certifico haber examinado a {prefix} <b>{patient_name}</b> "
            f"<b>{doc_part}</b> {narrative}"
        )

    story.append(Paragraph(full_cert, body_style))
    story.append(Spacer(1, 10))

    # 5. DIAGNÓSTICO (Dx)
    diagnosis_val = (getattr(license, "diagnosis", None) or "Embarazo de 28 sem/usl").strip()
    dx_style = ParagraphStyle(
        "CertDx",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.black,
        spaceAfter=14,
    )
    story.append(Paragraph(f"<b>Dx</b> {diagnosis_val}", dx_style))
    story.append(Spacer(1, 14))

    # 6. LUGAR Y FECHA DE EXPEDICIÓN
    created_date = getattr(license, "created_at", None)
    if isinstance(created_date, datetime):
        d_day = created_date.day
        d_year = created_date.year
        months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        d_month = months_es[created_date.month - 1]
    else:
        now = datetime.now()
        d_day = now.day
        d_year = now.year
        months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        d_month = months_es[now.month - 1]

    date_str = f"Se expide la presente certificación en Santo Domingo, DN , {d_day}  {d_month}  {d_year}"
    date_style = ParagraphStyle(
        "CertDate",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.black,
        spaceAfter=25,
    )
    story.append(Paragraph(date_str, date_style))
    story.append(Spacer(1, 35))

    # 7. FIRMA Y SELLO CENTRADA
    sig_style = ParagraphStyle(
        "CertSignature",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        alignment=1, # Centrado
        textColor=colors.black,
    )
    sig_content = [
        Paragraph("____________________________________________", sig_style),
        Spacer(1, 4),
        Paragraph(f"<b>{doctor_name}</b>", sig_style),
        Paragraph(f"<font size=9>{specialty}</font>", sig_style),
        Paragraph(f"<font size=9>Exeq. {exequatur} | Céd. {cedula}</font>", sig_style),
        Spacer(1, 6),
        Paragraph("<font size=9><b>FIRMA Y SELLO</b></font>", sig_style),
    ]
    story.append(KeepTogether(sig_content))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_medical_reference_pdf(reference, setting=None) -> io.BytesIO:
    """
    Genera la Carta Oficial de Referencia e Interconsulta Médica en formato oficial de
    Hoja Completa Carta (Letter 8.5 x 11 pulg), con logo centrado en gran formato B/N,
    encabezado oficial, datos clínicos estructurados y firma y sello médico centrado.
    """
    pagesize = letter
    left_m = 0.85 * inch
    right_m = 0.85 * inch
    top_m = 0.65 * inch
    bottom_m = 0.65 * inch
    page_w, page_h = letter
    usable_w = page_w - left_m - right_m

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    styles = _get_styles()
    story = []

    # 1. LOGO OFICIAL CENTRADO (FORMATO GRANDE 4.8 pulg)
    logo_path = _resolve_doctor_logo(setting)
    if logo_path and os.path.isfile(logo_path):
        try:
            logo_w = 4.8 * inch
            logo_h = 2.52 * inch
            logo_img = Image(logo_path, width=logo_w, height=logo_h)
            logo_img.hAlign = 'CENTER'
            story.append(logo_img)
            story.append(Spacer(1, 10))
        except Exception:
            pass

    # 2. TÍTULO Y DESTINATARIO CENTRADO
    title_style = ParagraphStyle(
        "RefTitle",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        alignment=1, # Centrado
        textColor=colors.black,
        spaceAfter=6,
    )
    story.append(Paragraph("<b>CARTA DE REFERENCIA MÉDICA / INTERCONSULTA</b>", title_style))

    referred_to = (getattr(reference, "referred_to_doctor_or_specialty", "") or "Especialista Tratante").strip()
    institution = (getattr(reference, "institution", "") or "").strip()
    dest_str = f"Dirigido a: <b>{referred_to}</b>"
    if institution:
        dest_str += f" &bull; Institución: <b>{institution}</b>"

    dest_style = ParagraphStyle(
        "RefDestTitle",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        alignment=1, # Centrado
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=12,
    )
    story.append(Paragraph(dest_str, dest_style))
    story.append(Spacer(1, 4))

    # 3. DATOS DEL DOCTOR Y DEL PACIENTE
    patient = getattr(reference, "patient", None)
    p_info = _extract_patient_display_data(patient)
    doctor_name = getattr(setting, "doctor_name", "Dr. Carlos Miguel Heredia Jorge") if setting else "Dr. Carlos Miguel Heredia Jorge"
    specialty = getattr(setting, "specialty", "Ginecólogo Obstetra") if setting else "Ginecólogo Obstetra"
    exequatur = getattr(setting, "doctor_exequatur", "165-10") if setting else "165-10"
    cedula = getattr(setting, "doctor_cedula", "001-1418378-3") if setting else "001-1418378-3"

    prefix = "a la paciente" if p_info.get("gender", "").lower() in ["f", "femenino"] else "al paciente"
    patient_name = p_info["name"]
    doc_id = p_info["doc_id"]
    doc_part = f"Cédula # <b>{doc_id}</b>" if doc_id and doc_id != "Sin documento" else ""
    age_str = f"edad: <b>{p_info['age']}</b>" if p_info.get("age") and p_info['age'] != 'N/D' else ""
    allergies_val = p_info.get("allergies", "")
    allergies_note = f" &bull; Alergias: <b>{allergies_val}</b>" if allergies_val and allergies_val != "Negadas" else ""

    patient_details = ", ".join(filter(bool, [doc_part, age_str]))
    if patient_details:
        patient_details = f"({patient_details}{allergies_note})"

    body_style = ParagraphStyle(
        "RefBodyText",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        alignment=4, # Justificado
        textColor=colors.black,
        spaceAfter=10,
    )

    preamble = (
        f"Yo <b>{doctor_name.upper()}</b>, <b>{specialty.upper()}</b>, Exequátur <b>{exequatur}</b>, "
        f"Cédula # <b>{cedula}</b>, certifico por medio de la presente haber evaluado y referir formalmente "
        f"{prefix} <b>{patient_name}</b> {patient_details}, para su debida valoración e interconsulta médica."
    )
    story.append(Paragraph(preamble, body_style))
    story.append(Spacer(1, 4))

    # 4. SECCIONES CLÍNICAS DESTACADAS
    sec_label_style = ParagraphStyle(
        "RefSecLabel",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.black,
        spaceAfter=3,
    )
    sec_content_style = ParagraphStyle(
        "RefSecContent",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        alignment=4,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )

    # Motivo de la derivación
    reason_txt = (getattr(reference, "reason_for_referral", "") or "").strip().replace("\n", "<br/>")
    story.append(Paragraph("<b>MOTIVO DE LA REFERENCIA / DERIVACIÓN:</b>", sec_label_style))
    story.append(Paragraph(reason_txt or "Valoración especializada.", sec_content_style))

    # Resumen Clínico
    summary_txt = (getattr(reference, "clinical_summary", "") or "").strip().replace("\n", "<br/>")
    if summary_txt:
        story.append(Paragraph("<b>RESUMEN CLÍNICO Y HALLAZGOS RELEVANTES:</b>", sec_label_style))
        story.append(Paragraph(summary_txt, sec_content_style))

    # Notas adicionales
    notes_txt = (getattr(reference, "notes", "") or "").strip().replace("\n", "<br/>")
    if notes_txt:
        story.append(Paragraph("<b>NOTAS ADICIONALES / EXÁMENES ADJUNTOS:</b>", sec_label_style))
        story.append(Paragraph(notes_txt, sec_content_style))

    story.append(Spacer(1, 8))

    # 5. LUGAR Y FECHA DE EXPEDICIÓN
    created_date = getattr(reference, "created_at", None)
    if isinstance(created_date, datetime):
        d_day = created_date.day
        d_year = created_date.year
        months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        d_month = months_es[created_date.month - 1]
    else:
        now = datetime.now()
        d_day = now.day
        d_year = now.year
        months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        d_month = months_es[now.month - 1]

    date_str = f"Se expide la presente carta de referencia en Santo Domingo, D.N., a los {d_day} días del mes de {d_month} del año {d_year}."
    date_style = ParagraphStyle(
        "RefDate",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.black,
        spaceAfter=18,
    )
    story.append(Paragraph(date_str, date_style))
    story.append(Spacer(1, 14))

    # 6. FIRMA Y SELLO CENTRADA
    sig_style = ParagraphStyle(
        "RefSignature",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        alignment=1, # Centrado
        textColor=colors.black,
    )
    sig_content = [
        Paragraph("____________________________________________", sig_style),
        Spacer(1, 4),
        Paragraph(f"<b>{doctor_name}</b>", sig_style),
        Paragraph(f"<font size=9>{specialty}</font>", sig_style),
        Paragraph(f"<font size=9>Exeq. {exequatur} | Céd. {cedula}</font>", sig_style),
        Spacer(1, 5),
        Paragraph("<font size=9><b>FIRMA Y SELLO MÉDICO</b></font>", sig_style),
    ]
    story.append(KeepTogether(sig_content))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_executive_report_pdf(
    setting=None,
    total_patients: int = 0,
    total_consultations: int = 0,
    total_payments: int = 0,
    total_vitals: int = 0,
    total_collected: float = 0.0,
    total_pending: float = 0.0,
    top_diagnoses: list = None,
    gender_counts: dict = None,
    age_groups: dict = None,
    period_str: str = "",
) -> io.BytesIO:
    """
    Genera el Reporte Ejecutivo Clínico en PDF con membrete, KPIs, epidemiología y demografía.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=36,
        bottomMargin=40,
    )
    styles = _get_styles()
    story = []

    # --- Membrete con logo ---
    _build_letterhead(story, styles, setting, subtitle_text="REPORTE EJECUTIVO CLÍNICO")

    # --- Fecha de generación y período ---
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    address = getattr(setting, "address", "") if setting else ""
    currency = getattr(setting, "currency", "RD$") if setting else "RD$"

    header_info = f"Generado el {now_str} • Sistema SSCP Desktop"
    if period_str:
        header_info += f" &bull; <b>Período: {period_str}</b>"

    story.append(Paragraph(
        f"<font size=8 color='#64748b'>{header_info}</font>",
        styles["footer"]
    ))
    story.append(Spacer(1, 14))

    # --- Sección 1: KPIs ---
    story.append(Paragraph("<b>Indicadores Clave del Consultorio</b>", styles["section"]))
    story.append(Spacer(1, 6))

    kpi_data = [
        ["Indicador", "Valor", "Descripción"],
        ["Total de Pacientes", str(total_patients), "Expedientes registrados en el sistema"],
        ["Consultas Médicas", str(total_consultations), "Atenciones clínicas completadas"],
        ["Signos Vitales", str(total_vitals), "Mediciones de control registradas"],
        ["Registros de Pago", str(total_payments), "Transacciones en el sistema"],
        [f"Recaudado ({currency})", f"{total_collected:,.2f}", "Pagos completados"],
        [f"Pendiente por Cobrar ({currency})", f"{total_pending:,.2f}", "Balances no cobrados"],
    ]

    kpi_table = Table(kpi_data, colWidths=[2.2 * inch, 1.4 * inch, 3.4 * inch])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG_LIGHT, colors.white]),
        ("FONTNAME", (0, 5), (1, 6), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 5), (1, 5), colors.HexColor("#059669")),  # verde cobrado
        ("TEXTCOLOR", (1, 6), (1, 6), colors.HexColor("#d97706")),  # ámbar pendiente
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 18))

    # --- Sección 2: Top Diagnósticos ---
    if top_diagnoses:
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceAfter=10))
        story.append(Paragraph("<b>Top Diagnósticos Más Frecuentes</b>", styles["section"]))
        story.append(Spacer(1, 4))

        diag_header = [["Diagnóstico / CIE-10", "Casos", "% del total"]]
        diag_rows = [
            [Paragraph(d["name"], styles["body"]), str(d["count"]), f"{d['percent']}%"]
            for d in top_diagnoses
        ]
        diag_data = diag_header + diag_rows
        diag_table = Table(diag_data, colWidths=[4.4 * inch, 0.8 * inch, 1.8 * inch])
        diag_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG_LIGHT, colors.white]),
        ]))
        story.append(diag_table)
        story.append(Spacer(1, 18))

    # --- Sección 3: Demografía ---
    if gender_counts or age_groups:
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceAfter=10))
        story.append(Paragraph("<b>Distribución Demográfica de Pacientes</b>", styles["section"]))
        story.append(Spacer(1, 6))

        g = gender_counts or {}
        demo_data = [
            ["Género", "Cantidad", "  ", "Grupo Etario", "Cantidad"],
            ["Masculino", str(g.get("male", 0)), "", "Pediátricos (<18)", str((age_groups or {}).get("pediatric", 0))],
            ["Femenino", str(g.get("female", 0)), "", "Jóvenes (18-35)", str((age_groups or {}).get("young_adult", 0))],
            ["Otro / No esp.", str(g.get("other", 0)), "", "Adultos (36-60)", str((age_groups or {}).get("middle_adult", 0))],
            ["", "", "", "Mayores (>60)", str((age_groups or {}).get("senior", 0))],
        ]
        demo_table = Table(demo_data, colWidths=[1.4 * inch, 0.8 * inch, 0.4 * inch, 1.8 * inch, 0.8 * inch])
        demo_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (3, 0), (4, 0), colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (1, -1), 0.4, BORDER_COLOR),
            ("GRID", (3, 0), (4, -1), 0.4, BORDER_COLOR),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ]))
        story.append(demo_table)
        story.append(Spacer(1, 30))

    # --- Firma ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceAfter=8))
    sig_data = [
        [
            Paragraph(f"<font size=8 color='#64748b'>{address}</font>", styles["body"]),
            Paragraph(
                f"<br/><br/>________________________________________<br/>"
                f"<b>{doctor_name}</b><br/>{specialty}",
                styles["body"]
            )
        ]
    ]
    sig_t = Table(sig_data, colWidths=[4.0 * inch, 3.0 * inch])
    sig_t.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "CENTER")]))
    story.append(KeepTogether(sig_t))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Documento generado automáticamente desde SSCP Desktop • Confidencial",
        styles["footer"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_secretary_daily_report_pdf(
    setting=None,
    report_date_str: str = "",
    user_name: str = "Secretaría / Recepción",
    kpis: dict = None,
    payment_methods_breakdown: dict = None,
    entries: list = None,
) -> io.BytesIO:
    """
    Genera el Reporte de Entrada y Recepción Diaria de Secretaría en PDF.
    Documenta el flujo de pacientes, triajes tomados, estado de citas,
    cuadre de caja de recepción y firmas de entrega de turno.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=32,
        bottomMargin=36,
    )
    styles = _get_styles()
    story = []

    kpis = kpis or {}
    currency = kpis.get("currency", "RD$")
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    effective_date = report_date_str or datetime.now().strftime("%d/%m/%Y")

    # Estilos específicos para celdas compactas
    cell_style = ParagraphStyle(
        "SecCellSmall",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=TEXT_DARK,
    )
    cell_bold = ParagraphStyle(
        "SecCellBold",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=TEXT_DARK,
    )
    cell_muted = ParagraphStyle(
        "SecCellMuted",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=TEXT_MUTED,
    )

    # 1. Membrete oficial con logo del doctor / consultorio
    _build_letterhead(story, styles, setting, subtitle_text="REPORTE DIARIO DE ENTRADA Y RECEPCIÓN")

    # 2. Barra de Metadatos del Turno
    meta_data = [
        [
            Paragraph(f"<b>Fecha de Operación:</b> {effective_date}", styles["body"]),
            Paragraph(f"<b>Responsable Recepción:</b> {user_name}", styles["body"]),
            Paragraph(f"<b>Impresión:</b> {now_str}", styles["body"]),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[2.5 * inch, 2.7 * inch, 2.2 * inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 3. Resumen Ejecutivo de Recepción (KPIs del Turno)
    story.append(Paragraph("<b>Resumen Operativo & Cuadre de Caja del Día</b>", styles["section"]))
    story.append(Spacer(1, 4))

    tot_patients = kpis.get("total_patients_admitted", 0)
    tot_appts = kpis.get("total_appointments", 0)
    tot_waiting = kpis.get("waiting_count", 0)
    tot_attended = kpis.get("attended_count", 0)
    tot_vitals = kpis.get("total_vitals", 0)
    tot_collected = kpis.get("total_collected", 0.0)
    tot_pending = kpis.get("total_pending", 0.0)

    kpi_summary = [
        ["Total Entradas / Pacientes", "Citas del Turno", "Triajes / Signos", f"Caja Cobrada ({currency})", f"Saldos Pendientes ({currency})"],
        [
            str(tot_patients),
            f"{tot_appts} (Esperando: {tot_waiting} | Atendidas: {tot_attended})",
            str(tot_vitals),
            f"{tot_collected:,.2f}",
            f"{tot_pending:,.2f}",
        ],
    ]
    kpi_table = Table(kpi_summary, colWidths=[1.4 * inch, 2.0 * inch, 1.2 * inch, 1.4 * inch, 1.4 * inch])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 8.5),
        ("TEXTCOLOR", (3, 1), (3, 1), colors.HexColor("#059669")),  # Verde recaudado
        ("TEXTCOLOR", (4, 1), (4, 1), colors.HexColor("#d97706")),  # Ámbar pendiente
        ("BACKGROUND", (0, 1), (-1, 1), BG_LIGHT),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 8))

    # 3.1 Desglose de Caja por Método de Pago (si existen cobros)
    if payment_methods_breakdown:
        pm_header = ["Método de Pago", "Monto Recaudado"]
        pm_rows = [pm_header]
        for meth, amt in payment_methods_breakdown.items():
            pm_rows.append([meth, f"{currency} {amt:,.2f}"])
        pm_table = Table(pm_rows, colWidths=[2.2 * inch, 1.6 * inch])
        pm_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ]))
        story.append(pm_table)
        story.append(Spacer(1, 8))

    # 4. Tabla Detallada de Entradas y Recepción
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceAfter=8))
    story.append(Paragraph("<b>Registro Detallado de Pacientes & Entradas del Día</b>", styles["section"]))
    story.append(Spacer(1, 4))

    table_headers = [
        "Hora",
        "Paciente / Documento",
        "Tipo / Motivo",
        "Estado",
        "Triaje (Signos Vitales)",
        "Cobro / Recibo",
    ]

    detail_rows = [table_headers]

    if entries and len(entries) > 0:
        for ent in entries:
            time_val = ent.get("time", "-")
            p_name = ent.get("patient_name", "Sin nombre")
            p_doc = ent.get("document_id", "")
            p_phone = ent.get("phone", "")
            patient_cell = f"<b>{p_name}</b>"
            if p_doc:
                patient_cell += f"<br/><font size=7 color='#64748b'>Doc: {p_doc}</font>"
            if p_phone:
                patient_cell += f"<br/><font size=7 color='#64748b'>Tel: {p_phone}</font>"

            entry_type = ent.get("entry_type", "Atención")
            reason = ent.get("reason", "")
            type_cell = f"<b>{entry_type}</b>"
            if reason:
                type_cell += f"<br/><font size=7 color='#475569'>{reason[:50]}</font>"

            status_val = ent.get("status", "-")
            vitals_val = ent.get("vitals", "Sin registro")
            pay_val = ent.get("payment", "Sin cobro")

            detail_rows.append([
                Paragraph(time_val, cell_bold),
                Paragraph(patient_cell, cell_style),
                Paragraph(type_cell, cell_style),
                Paragraph(f"<b>{status_val}</b>", cell_style),
                Paragraph(vitals_val, cell_muted),
                Paragraph(pay_val, cell_muted),
            ])
    else:
        detail_rows.append([
            Paragraph("-", cell_style),
            Paragraph("No se registraron entradas de pacientes en esta fecha.", cell_style),
            Paragraph("-", cell_style),
            Paragraph("-", cell_style),
            Paragraph("-", cell_style),
            Paragraph("-", cell_style),
        ])

    detail_table = Table(
        detail_rows,
        colWidths=[0.65 * inch, 1.65 * inch, 1.55 * inch, 0.85 * inch, 1.40 * inch, 1.30 * inch]
    )
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 24))

    # 5. Bloque de Firmas y Validación de Turno
    doctor_name = getattr(setting, "doctor_name", "Médico Director") if setting else "Médico Director"
    sig_content = [
        [
            Paragraph(
                f"<br/><br/>________________________________________<br/>"
                f"<b>{user_name}</b><br/>"
                f"<font size=8 color='#64748b'>Firma Secretaria / Recepción<br/>Responsable de Turno y Arqueo</font>",
                styles["body"]
            ),
            Paragraph(
                f"<br/><br/>________________________________________<br/>"
                f"<b>{doctor_name}</b><br/>"
                f"<font size=8 color='#64748b'>Firma y Sello Médico / Administración<br/>Visto Bueno y Recibido Conforme</font>",
                styles["body"]
            ),
        ]
    ]
    sig_table = Table(sig_content, colWidths=[3.7 * inch, 3.7 * inch])
    sig_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(KeepTogether(sig_table))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"SSCP Desktop • Comprobante Oficial de Recepción y Cuadre de Turno • Generado {now_str}",
        styles["footer"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _get_calibrated_talonario_params(cfg: dict = None):
    """
    Obtiene las dimensiones y la función de conversión de coordenadas calibradas
    para el talonario preimpreso de 13.6 × 21.7 cm (Media Carta Vertical).
    """
    if not cfg:
        try:
            from app.services.print_config_service import get_print_config
            cfg = get_print_config()
        except Exception:
            cfg = {}

    page_w_mm = float(cfg.get("paper_width_mm", 136.0) or 136.0)
    page_h_mm = float(cfg.get("paper_height_mm", 217.0) or 217.0)
    fields = cfg.get("fields", {}) if isinstance(cfg.get("fields"), dict) else {}

    def to_rl_y(y_top_mm: float, font_size_pt: float) -> float:
        # En CSS top: y_mm coloca la parte superior de la caja.
        # ReportLab dibuja en la línea base (baseline) desde el fondo:
        cap_h_mm = font_size_pt * 0.3528 * 0.82
        y_bottom_mm = page_h_mm - (float(y_top_mm) + cap_h_mm)
        return y_bottom_mm * mm

    return page_w_mm, page_h_mm, fields, to_rl_y


def _draw_talonario_patient_footer(c, patient, fields: dict, to_rl_y, custom_date_str: str = None):
    """
    Dibuja los datos del paciente alineados exactamente sobre las líneas físicas
    preimpresas inferiores del talonario (PACIENTE, EDAD, CED., FECHA).
    """
    p_info = _extract_patient_display_data(patient)
    patient_name = p_info["name"]
    doc_id = p_info["doc_id"] if p_info["has_doc"] else (f"Exp. #{getattr(patient, 'id', '')}" if getattr(patient, 'id', None) else "S/D")
    age_str = p_info["age_str"]
    fecha_str = custom_date_str or datetime.now().strftime("%d/%m/%Y")

    # 1. Línea PACIENTE (preimpresa a ~178.5 mm desde arriba)
    f_p = fields.get("patient_name", {})
    p_x = float(f_p.get("x", 28.0)) * mm
    p_size = float(f_p.get("fontSize", 10.5))
    p_y = to_rl_y(float(f_p.get("y", 178.5)), p_size)
    c.setFont("Helvetica-Bold", p_size)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(p_x, p_y, str(patient_name))

    # 2. Línea EDAD / CED. / FECHA (preimpresa a ~187.0 mm desde arriba)
    f_age = fields.get("age", {})
    age_size = float(f_age.get("fontSize", 10.0))
    c.setFont("Helvetica", age_size)
    c.drawString(float(f_age.get("x", 16.0)) * mm, to_rl_y(float(f_age.get("y", 187.0)), age_size), str(age_str))

    f_id = fields.get("id_card", {})
    id_size = float(f_id.get("fontSize", 10.0))
    c.setFont("Helvetica", id_size)
    c.drawString(float(f_id.get("x", 52.0)) * mm, to_rl_y(float(f_id.get("y", 187.0)), id_size), str(doc_id))

    f_dt = fields.get("date", {})
    dt_size = float(f_dt.get("fontSize", 10.0))
    c.setFont("Helvetica", dt_size)
    c.drawString(float(f_dt.get("x", 102.0)) * mm, to_rl_y(float(f_dt.get("y", 187.0)), dt_size), str(fecha_str))


def generate_talonario_overlay_pdf(patient, prescription_text: str, setting=None, patient_instructions: str = None) -> io.BytesIO:
    """
    Genera un PDF de posicionamiento exacto para imprimir encima del talonario
    preimpreso del Dr. Carlos M. Heredia (13.6 × 21.7 cm, Media Carta Vertical).
    Utiliza las coordenadas y márgenes calibrados de print_config_service.
    """
    page_w_mm, page_h_mm, fields, to_rl_y = _get_calibrated_talonario_params()

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(page_w_mm * mm, page_h_mm * mm))

    # ── Datos del paciente en el pie preimpreso ───────────────────────────────
    _draw_talonario_patient_footer(c, patient, fields, to_rl_y)

    # ── ZONA Rp. — Cuerpo de la prescripción e indicaciones para el paciente ───
    f_rx = fields.get("medications", {})
    rx_x = float(f_rx.get("x", 16.0)) * mm
    rx_font_size = float(f_rx.get("fontSize", 9.5))
    rx_y_top = to_rl_y(float(f_rx.get("y", 72.0)), rx_font_size)
    rx_max_w = float(f_rx.get("width", 108.0)) * mm
    rx_line_h = rx_font_size * 0.3528 * 1.45 * mm
    pat_y = float(fields.get("patient_name", {}).get("y", 178.5))
    stop_y_bottom = to_rl_y(pat_y - 8.0, rx_font_size)

    # Combinar prescripción con indicaciones del paciente (si existen en la consulta)
    full_body = (prescription_text or "").strip()
    if patient_instructions and patient_instructions.strip():
        if full_body:
            full_body += "\n\nINDICACIONES:\n" + patient_instructions.strip()
        else:
            full_body = "INDICACIONES:\n" + patient_instructions.strip()

    c.setFont("Helvetica", rx_font_size)
    c.setFillColor(colors.HexColor("#1e293b"))

    y_cursor = rx_y_top
    for raw_line in full_body.splitlines():
        if y_cursor < stop_y_bottom:
            break

        line = raw_line.rstrip()
        if not line:
            y_cursor -= (rx_line_h * 0.7)
            continue

        is_heading = line.startswith("INDICACIONES:") or line.startswith("Rp.")
        if is_heading:
            c.setFont("Helvetica-Bold", rx_font_size)
            c.setFillColor(colors.HexColor("#0f766e"))
        else:
            c.setFont("Helvetica", rx_font_size)
            c.setFillColor(colors.HexColor("#0f172a"))

        words = line.split(" ")
        current_chunk = ""
        for word in words:
            test_line = f"{current_chunk} {word}".strip()
            if c.stringWidth(test_line, "Helvetica", rx_font_size) < rx_max_w:
                current_chunk = test_line
            else:
                if current_chunk:
                    c.drawString(rx_x, y_cursor, current_chunk)
                    y_cursor -= rx_line_h
                    if y_cursor < stop_y_bottom:
                        break
                current_chunk = word
        if current_chunk and y_cursor >= stop_y_bottom:
            c.drawString(rx_x, y_cursor, current_chunk)
            y_cursor -= rx_line_h

    c.save()
    buffer.seek(0)
    return buffer


def generate_medical_license_talonario_pdf(license_obj, setting=None) -> io.BytesIO:
    """
    Genera un PDF de posicionamiento exacto para imprimir una Licencia Médica / Certificado
    de Reposo sobre la misma hoja física del talonario preimpreso (13.6 × 21.7 cm).
    """
    page_w_mm, page_h_mm, fields, to_rl_y = _get_calibrated_talonario_params()

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(page_w_mm * mm, page_h_mm * mm))

    # Pie del talonario
    start_d_str = license_obj.start_date.strftime("%d/%m/%Y") if getattr(license_obj, "start_date", None) else datetime.now().strftime("%d/%m/%Y")
    _draw_talonario_patient_footer(c, getattr(license_obj, "patient", None), fields, to_rl_y, custom_date_str=start_d_str)

    # Cuerpo de la Licencia en el área central útil del talonario
    f_rx = fields.get("medications", {})
    rx_x = float(f_rx.get("x", 16.0)) * mm
    rx_max_w = float(f_rx.get("width", 108.0)) * mm
    y_cursor = to_rl_y(float(f_rx.get("y", 72.0)), 10.0)
    pat_y = float(fields.get("patient_name", {}).get("y", 178.5))
    stop_y_bottom = to_rl_y(pat_y - 8.0, 10.0)

    # Título distintivo de la certificación médica
    c.setFont("Helvetica-Bold", 10.0)
    c.setFillColor(colors.HexColor("#0f766e"))
    c.drawString(rx_x, y_cursor, "CERTIFICADO MÉDICO")
    y_cursor -= 5.5 * mm

    # Formateo de fechas
    end_d_str = license_obj.end_date.strftime("%d/%m/%Y") if license_obj.end_date else ""
    periodo_str = f"Del {start_d_str} al {end_d_str}" if end_d_str else f"A partir de {start_d_str}"

    sections = [
        ("DIAGNÓSTICO:", str(license_obj.diagnosis or "Evaluación médica general")),
        ("DÍAS DE REPOSO:", f"{license_obj.days_rest} días ({periodo_str})"),
    ]
    if license_obj.workplace_or_school:
        sections.append(("DIRIGIDO A:", str(license_obj.workplace_or_school)))
    if license_obj.notes:
        sections.append(("RECOMENDACIONES:", str(license_obj.notes)))

    c.setFont("Helvetica", 8.5)
    line_h = 4.2 * mm

    for label, text in sections:
        if y_cursor < stop_y_bottom:
            break
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(colors.HexColor("#0f766e"))
        c.drawString(rx_x, y_cursor, label)
        y_cursor -= line_h

        c.setFont("Helvetica", 8.5)
        c.setFillColor(colors.HexColor("#1e293b"))
        for raw_line in text.splitlines():
            words = raw_line.split(" ")
            chunk = ""
            for w in words:
                test = f"{chunk} {w}".strip()
                if c.stringWidth(test, "Helvetica", 8.5) < rx_max_w:
                    chunk = test
                else:
                    if chunk:
                        c.drawString(rx_x + 2.0 * mm, y_cursor, chunk)
                        y_cursor -= line_h
                        if y_cursor < stop_y_bottom:
                            break
                    chunk = w
            if chunk and y_cursor >= stop_y_bottom:
                c.drawString(rx_x + 2.0 * mm, y_cursor, chunk)
                y_cursor -= line_h
        y_cursor -= 1.5 * mm

    c.save()
    buffer.seek(0)
    return buffer


def generate_medical_reference_talonario_pdf(reference_obj, setting=None) -> io.BytesIO:
    """
    Genera un PDF de posicionamiento exacto para imprimir una Carta de Referencia / Interconsulta
    sobre la misma hoja física del talonario preimpreso (13.6 × 21.7 cm).
    """
    page_w_mm, page_h_mm, fields, to_rl_y = _get_calibrated_talonario_params()

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(page_w_mm * mm, page_h_mm * mm))

    # Pie del talonario
    ref_d_str = reference_obj.created_at.strftime("%d/%m/%Y") if reference_obj.created_at else datetime.now().strftime("%d/%m/%Y")
    _draw_talonario_patient_footer(c, reference_obj.patient, fields, to_rl_y, custom_date_str=ref_d_str)

    # Cuerpo de la Referencia en el área central útil del talonario
    f_rx = fields.get("medications", {})
    rx_x = float(f_rx.get("x", 16.0)) * mm
    rx_max_w = float(f_rx.get("width", 108.0)) * mm
    y_cursor = to_rl_y(float(f_rx.get("y", 72.0)), 10.0)
    stop_y_bottom = to_rl_y(float(fields.get("patient_name", {}).get("y", 178.5)) - 4.0, 10.0)

    # Título distintivo de la referencia
    c.setFont("Helvetica-Bold", 10.0)
    c.setFillColor(colors.HexColor("#0f766e"))
    c.drawString(rx_x, y_cursor, "CARTA DE REFERENCIA / INTERCONSULTA")
    y_cursor -= 5.5 * mm

    sections = [
        ("DIRIGIDO A:", str(reference_obj.referred_to_doctor_or_specialty or "Especialista tratante")),
    ]
    if reference_obj.institution:
        sections.append(("INSTITUCIÓN / CENTRO:", str(reference_obj.institution)))
    sections.append(("MOTIVO DE REFERENCIA:", str(reference_obj.reason_for_referral or "")))
    if reference_obj.clinical_summary:
        sections.append(("RESUMEN CLÍNICO:", str(reference_obj.clinical_summary)))
    if reference_obj.notes:
        sections.append(("NOTAS ADICIONALES:", str(reference_obj.notes)))

    c.setFont("Helvetica", 8.5)
    line_h = 4.2 * mm

    for label, text in sections:
        if y_cursor < stop_y_bottom:
            break
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(colors.HexColor("#0f766e"))
        c.drawString(rx_x, y_cursor, label)
        y_cursor -= line_h

        c.setFont("Helvetica", 8.5)
        c.setFillColor(colors.HexColor("#1e293b"))
        for raw_line in text.splitlines():
            words = raw_line.split(" ")
            chunk = ""
            for w in words:
                test = f"{chunk} {w}".strip()
                if c.stringWidth(test, "Helvetica", 8.5) < rx_max_w:
                    chunk = test
                else:
                    if chunk:
                        c.drawString(rx_x + 2.0 * mm, y_cursor, chunk)
                        y_cursor -= line_h
                        if y_cursor < stop_y_bottom:
                            break
                    chunk = w
            if chunk and y_cursor >= stop_y_bottom:
                c.drawString(rx_x + 2.0 * mm, y_cursor, chunk)
                y_cursor -= line_h
        y_cursor -= 1.5 * mm

    c.save()
    buffer.seek(0)
    return buffer



def generate_lab_order_pdf(order, setting=None) -> io.BytesIO:
    """
    Genera la Orden / Solicitud Oficial de Estudios de Laboratorio Clínico (Fase 3 v1.2.0),
    respetando los márgenes configurados.
    """
    pagesize, left_m, right_m, top_m, bottom_m, usable_w = _get_page_setup()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    styles = _get_styles()
    story = []

    # Membrete con logo opcional
    _build_letterhead(story, styles, setting, subtitle_text="ORDEN DE ANÁLISIS CLÍNICOS", usable_width=usable_w)

    story.append(Paragraph("<font size=14 color='#0f766e'><b>SOLICITUD DE ESTUDIOS DE LABORATORIO</b></font>", styles["title"]))
    story.append(Spacer(1, 10))

    patient = getattr(order, "patient", None)
    p_info = _extract_patient_display_data(patient)
    order_date_str = order.order_date.strftime("%d/%m/%Y") if getattr(order, "order_date", None) else datetime.now().strftime("%d/%m/%Y")

    # Ficha de identificación del paciente y solicitud
    patient_info = [
        [
            Paragraph(f"<b>Paciente:</b> {p_info['name']}", styles["body"]),
            Paragraph(f"<b>Cédula / DNI:</b> {p_info['doc_id']}", styles["body"]),
        ],
        [
            Paragraph(f"<b>Edad / Sexo:</b> {p_info['age_str'] or 'N/D'} / {p_info['gender'] or 'N/D'}", styles["body"]),
            Paragraph(f"<b>ARS / Seguro:</b> {p_info['insurance_badge']}", styles["body"]),
        ],
        [
            Paragraph(f"<b>Fecha de Solicitud:</b> {order_date_str}", styles["body"]),
            Paragraph(f"<b>Alergias Conocidas:</b> <font color='#b91c1c'><b>{p_info['allergies']}</b></font>", styles["body"]),
        ]
    ]

    p_table = Table(patient_info, colWidths=[usable_w * 0.52, usable_w * 0.48])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(p_table)
    story.append(Spacer(1, 12))

    # Indicación clínica / Diagnóstico presuntivo
    if order.clinical_indication and order.clinical_indication.strip():
        story.append(Paragraph("<b>Indicación Clínica / Diagnóstico Presuntivo:</b>", styles["section"]))
        story.append(Paragraph(order.clinical_indication.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 12))

    # Lista de análisis requeridos
    story.append(Paragraph("<b>Análisis y Pruebas Solicitadas:</b>", styles["section"]))

    raw_tests = order.tests_requested or ""
    tests_list = []
    if raw_tests.startswith("["):
        try:
            import json
            parsed = json.loads(raw_tests)
            if isinstance(parsed, list):
                tests_list = [str(t).strip() for t in parsed if str(t).strip()]
        except Exception:
            pass

    if not tests_list:
        tests_list = [line.strip("- •* \t") for line in raw_tests.replace(";", "\n").replace(",", "\n").split("\n") if line.strip()]

    if tests_list:
        half = (len(tests_list) + 1) // 2
        col1 = tests_list[:half]
        col2 = tests_list[half:]

        test_rows = []
        for i in range(max(len(col1), len(col2))):
            t1 = col1[i] if i < len(col1) else ""
            t2 = col2[i] if i < len(col2) else ""
            idx1 = i + 1
            idx2 = i + len(col1) + 1
            p1 = Paragraph(f"<font color='#0f766e'><b>{idx1}.</b></font>&nbsp; <font color='#0f172a'><b>{t1}</b></font>", styles["body"]) if t1 else ""
            p2 = Paragraph(f"<font color='#0f766e'><b>{idx2}.</b></font>&nbsp; <font color='#0f172a'><b>{t2}</b></font>", styles["body"]) if t2 else ""
            test_rows.append([p1, p2])

        t_table = Table(test_rows, colWidths=[3.5 * inch, 3.5 * inch])
        t_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
        ]))
        story.append(t_table)
    else:
        story.append(Paragraph("<i>Ver indicaciones clínicas adjuntas.</i>", styles["body"]))

    story.append(Spacer(1, 14))

    # Instrucciones de preparación para el paciente
    if order.notes and order.notes.strip():
        story.append(Paragraph("<b>Instrucciones de Preparación:</b>", styles["section"]))
        prep_table = Table([[Paragraph(order.notes.replace("\n", "<br/>"), styles["body"])]], colWidths=[7.0 * inch])
        prep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#fcd34d")),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(prep_table)
        story.append(Spacer(1, 14))

    # Firma y sello del médico
    story.append(Spacer(1, 24))
    doc_name = getattr(order.doctor, "name", "Dr. Especialista") if order.doctor else "Dr. Especialista"
    signature_block = [
        [Paragraph("", styles["body"]), Paragraph("____________________________________", styles["footer"])],
        [Paragraph("", styles["body"]), Paragraph(f"<b>{doc_name}</b>", styles["footer"])],
        [Paragraph("", styles["body"]), Paragraph("Firma y Sello del Médico Tratante", styles["footer"])],
        [Paragraph("", styles["body"]), Paragraph(f"Exequátur / Registro Profesional", styles["footer"])],
    ]
    sig_table = Table(signature_block, colWidths=[3.8 * inch, 3.2 * inch])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(KeepTogether([sig_table]))

    doc.build(story)
    buffer.seek(0)
    return buffer


# ── MAPA DE COORDENADAS: TALONARIO PREIMPRESO DE ANÁLISIS (DR. CARLOS M. HEREDIA) ──
# Dimensiones reales del papel físico: 13.6 cm ancho × 21.7 cm alto (Media Carta Vertical)
# Coordenadas (x, y) en milímetros medidas desde la esquina inferior izquierda (origen ReportLab)
TALONARIO_LAB_COORDS = {
    # ── COLUMNA 1: HEMATOLOGIA (12 items) ──
    "Hemograma Completo": (10.6, 149.8),
    "Tipificación Sanguínea": (10.6, 146.5),
    "Eritrosedimentación": (10.6, 143.4),
    "TPT": (10.6, 140.2),
    "PT": (10.6, 137.0),
    "Tiempo de Coagulación": (10.6, 133.8),
    "Retracción de Coágulo": (10.6, 129.1),
    "Reconteo de Plaquetas": (10.6, 125.8),
    "Investigación de Células Falciformes": (10.6, 122.7),
    "Investigación de Células Falciformes (Falcemia)": (10.6, 122.7),
    "Falcemia": (10.6, 122.7),
    "Células Falciformes": (10.6, 122.7),
    "Electroforesis de Hb": (10.6, 119.4),
    "Fibrinógeno": (10.6, 116.3),
    "Dímero D": (10.6, 113.3),

    # ── COLUMNA 1: UROANALISIS (6 items) ──
    "Exámen de orina": (10.6, 106.8),
    "Albuminuria": (10.6, 103.5),
    "Prueba de embarazo de orina": (10.6, 99.0),
    "Cetonuria": (10.6, 95.7),
    "Glucosuria": (10.6, 92.6),
    "Calcio Urinario en 24h": (10.6, 89.3),

    # ── COLUMNA 1: MICROBIOLOGÍA (6 items) ──
    "Coprológico": (10.6, 78.3),
    "Urocultivo": (10.6, 73.5),
    "Hemocultivo": (10.6, 70.5),
    "Coprocultivo": (10.6, 65.5),
    "Cultivo Secreción Vaginal": (10.6, 62.5),
    "Baciloscopía": (10.6, 59.2),

    # ── COLUMNA 1: INMUNOLOGÍA (9 items) ──
    "Anticuerpo DNA": (10.6, 48.1),
    "Hepatitis A": (10.6, 41.7),
    "Hepatitis B": (10.6, 38.6),
    "Hepatitis C": (10.6, 35.4),
    "HIV": (10.6, 32.2),
    "Prueba de Tuberculina": (10.6, 27.5),
    "Varicela IgM - IgG": (10.6, 24.2),
    "Influenza A H1 N1 IgG - IgM": (10.6, 21.2),
    "Chikungunya IgG - IgM": (10.6, 17.9),

    # ── COLUMNA 2: SEROLOGÍA (17 items) ──
    "V.D.R.L.": (55.1, 149.8),
    "Anticuerpos Febriles": (55.1, 146.5),
    "Toxoplasmosis IgG - IgM": (55.1, 143.4),
    "Dengue IgG - IgM": (55.1, 140.2),
    "FTA. ABS": (55.1, 137.0),
    "ANA": (72.2, 137.0),
    "PCR": (55.1, 133.8),
    "ASO": (55.1, 130.6),
    "Factor Reumatoide": (55.1, 127.4),
    "P.C.R.": (55.1, 124.2),
    "Monotest": (55.1, 121.0),
    "Test de Coombs Directo": (55.1, 117.8),
    "Test de Coombs Indirecto": (55.1, 114.6),
    "Test Clamidia IgG - IgM": (55.1, 111.4),
    "TORCH IgG - IgM": (55.1, 108.2),
    "Herpes tipo 1 IgG - IgM": (55.1, 105.0),
    "Herpes Tipo 2 IgG - IgM": (55.1, 101.8),

    # ── COLUMNA 2: QUIMICA SANGUINEA (33 items) ──
    "Glicemia en ayuna": (55.1, 95.7),
    "Glicemia Post Pandrial": (55.1, 92.6),
    "Hemoglobina Glicosilada": (55.1, 89.3),
    "Curva": (55.1, 87.2),
    "Curva 3h": (69.8, 87.2),
    "Curva 5h": (81.8, 87.2),
    "Curva Insulina": (55.1, 84.1),
    "Acido Urico": (55.1, 80.9),
    "Colesterol Total": (55.1, 77.8),
    "HDL": (55.1, 74.6),
    "LDL": (67.1, 74.6),
    "VLDL": (79.2, 74.6),
    "Trigliceridos": (55.1, 71.4),
    "SGOT": (55.1, 68.3),
    "SGPT": (55.1, 65.1),
    "Bilirrubina": (55.1, 61.9),
    "Fosfatasa Alcalina": (55.1, 58.8),
    "Bun": (55.1, 55.6),
    "Creatinina": (55.1, 52.4),
    "Proteinas totales": (55.1, 49.3),
    "Albumina": (55.1, 46.1),
    "Electrolitos": (55.1, 43.0),
    "Hierro": (55.1, 39.8),
    "Gases Arteriales": (55.1, 36.6),
    "Ferretina Serica": (55.1, 33.5),
    "Calcio Serico": (55.1, 30.3),
    "B12": (55.1, 27.2),
    "Vitamina B12": (55.1, 27.2),
    "Acido Folico": (55.1, 24.0),
    "Fosforo Sérico": (55.1, 20.8),
    "Vitamina D": (55.1, 17.7),
    "PCR COVID -19": (55.1, 14.5),
    "PCR COVID - 19": (55.1, 14.5),
    "IGG COVID - 19": (55.1, 11.4),
    "IGM COVID - 19": (55.1, 8.2),

    # ── COLUMNA 3: PRUEBAS ESPECIALES (33 items) ──
    "T3": (95.3, 149.8),
    "T3 libre": (118.5, 149.8),
    "T4": (95.3, 146.5),
    "T4 libre": (118.5, 146.5),
    "TSH": (95.3, 143.4),
    "LH": (95.3, 140.2),
    "FSH": (95.3, 137.0),
    "Prolactina": (95.3, 133.8),
    "Estrógenos Totales": (95.3, 130.6),
    "Estradiol": (95.3, 127.4),
    "Estriol": (118.5, 127.4),
    "Progesterona": (95.3, 124.2),
    "Progesterona dia": (95.3, 121.0),
    "Androstenediona": (95.3, 117.8),
    "Testosterona total": (95.3, 114.6),
    "Testosterona libre": (95.3, 111.4),
    "DHEA - S": (95.3, 108.2),
    "BHCG cualitativa": (95.3, 105.0),
    "BHCG cuantitativa": (95.3, 101.8),
    "Inhibina": (95.3, 98.7),
    "Alfa Feto Proteína (AFP)": (95.3, 95.5),
    "CA19-9": (95.3, 92.3),
    "CA 19-9": (95.3, 92.3),
    "CA 125": (95.3, 89.2),
    "CA 15-3": (95.3, 86.0),
    "CEA": (95.3, 82.8),
    "HE4": (95.3, 79.7),
    "Osteocalcina": (95.3, 76.5),
    "Fosfatasa Alcalina Osea": (95.3, 73.4),
    "PTH intacto": (95.3, 70.2),
    "C-Telopeptido": (95.3, 67.0),
    "N-Telopeptido en Orina": (95.3, 63.9),
    "Hormona Antimulleriana": (95.3, 60.7),
    "Hormona Antimuleriana": (95.3, 60.7),
    "PAPP-A": (95.3, 57.5),

    # ── COLUMNA 3: SONOGRAFÍA E IMÁGENES (12 items y variantes) ──
    "Pélvica": (95.3, 48.5),
    "Sonografía Pélvica": (95.3, 48.5),
    "Sonografia Pelvica": (95.3, 48.5),

    "Transvaginal": (95.3, 45.4),
    "Sonografía Transvaginal": (95.3, 45.4),
    "Sonografia Transvaginal": (95.3, 45.4),

    "Sonomamografía": (95.3, 42.4),
    "Sonomamografia": (95.3, 42.4),
    "Sonografía Mamaria": (95.3, 42.4),
    "Sonografia Mamaria": (95.3, 42.4),

    "Obstetricia": (95.3, 39.3),
    "Sonografía Obstétrica": (95.3, 39.3),
    "Sonografia Obstetrica": (95.3, 39.3),
    "Sonografía Obstetricia": (95.3, 39.3),
    "Sonografia Obstetricia": (95.3, 39.3),

    "Abdominal": (95.3, 36.2),
    "Sonografía Abdominal": (95.3, 36.2),
    "Sonografia Abdominal": (95.3, 36.2),

    "Genética": (95.3, 33.1),
    "Sonografía Genética": (95.3, 33.1),
    "Sonografia Genetica": (95.3, 33.1),

    "Morfológica": (95.3, 30.1),
    "Sonografía Morfológica": (95.3, 30.1),
    "Sonografia Morfologica": (95.3, 30.1),

    "Perfil hemodinámico": (95.3, 27.0),
    "Perfil hemodinamico": (95.3, 27.0),
    "Sonografía Perfil Hemodinámico": (95.3, 27.0),
    "Sonografia Perfil Hemodinamico": (95.3, 27.0),

    "Doppler placentario": (95.3, 23.9),
    "Doppler Placentario": (95.3, 23.9),
    "Sonografía Doppler Placentario": (95.3, 23.9),
    "Sonografia Doppler Placentario": (95.3, 23.9),

    "Radiografía pélvica": (95.3, 20.8),
    "Radiografía Pélvica": (95.3, 20.8),
    "Radiografia Pelvica": (95.3, 20.8),

    "Tomografía abdominal": (95.3, 17.7),
    "Tomografía Abdominal": (95.3, 17.7),
    "Tomografia Abdominal": (95.3, 17.7),

    "Tomografía pelvica": (95.3, 14.6),
    "Tomografía Pélvica": (95.3, 14.6),
    "Tomografia Pelvica": (95.3, 14.6),
}


def _normalize_lab_test_name(test_name: str) -> str:
    """Normaliza un nombre de análisis para buscar en el diccionario de coordenadas."""
    if not test_name:
        return ""
    s = test_name.lower().strip()
    for a, b in [('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n'), ('-', ' '), ('.', '')]:
        s = s.replace(a, b)
    return " ".join(s.split())


# Diccionario normalizado generado una sola vez para búsqueda O(1)
_NORMALIZED_LAB_COORDS = {
    _normalize_lab_test_name(k): coords for k, coords in TALONARIO_LAB_COORDS.items()
}


def generate_lab_order_talonario_pdf(order, setting=None) -> io.BytesIO:
    """
    Genera un PDF de posicionamiento exacto para imprimir la Solicitud de Laboratorios
    sobre el talonario preimpreso VERTICAL del Dr. Carlos M. Heredia (13.6 × 21.7 cm, Media Carta Vertical).

    Utiliza las coordenadas y márgenes calibrados de print_config_service:
      - Membrete y símbolo Rp superior respetados (inicia en y <= 140 mm).
      - Si hay 6 o más estudios, los divide automáticamente en 2 columnas balanceadas
        para aprovechar el ancho del papel y no invadir el pie ni el membrete.
      - Al pie imprime los datos del paciente alineados exactamente sobre las líneas físicas preimpresas
        (PACIENTE, EDAD, CED., FECHA) mediante _draw_talonario_patient_footer.
    """
    page_w_mm, page_h_mm, fields, to_rl_y = _get_calibrated_talonario_params()

    PAGE_W_pt = page_w_mm * mm
    PAGE_H_pt = page_h_mm * mm

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W_pt, PAGE_H_pt))

    # ── Datos del paciente en el pie preimpreso ───────────────────────────────
    p = getattr(order, "patient", None)
    ord_date = getattr(order, "order_date", None)
    if isinstance(ord_date, (datetime, date)):
        fecha_str = ord_date.strftime("%d/%m/%Y")
    else:
        fecha_str = datetime.now().strftime("%d/%m/%Y")

    _draw_talonario_patient_footer(c, p, fields, to_rl_y, custom_date_str=fecha_str)

    # Parsear lista de análisis solicitados
    tests_list = []
    if order and getattr(order, "tests_requested", None):
        try:
            tests_list = json.loads(order.tests_requested)
        except Exception:
            tests_list = [t.strip() for t in str(order.tests_requested).splitlines() if t.strip()]

    # Filtrar vacíos
    tests_list = [str(t).strip() for t in tests_list if str(t).strip()]
    total_tests = len(tests_list)

    # ── TÍTULO E INDICACIÓN CLÍNICA (CALIBRADO CON EL CUERPO DEL TALONARIO) ────
    f_body = fields.get("medications", {}) if isinstance(fields, dict) else {}
    body_x = float(f_body.get("x", 16.0))
    body_y_top = float(f_body.get("y", 72.0))

    # Título dinámico según la coordenada Y configurada (evita colisión con Rp y membrete)
    y_title = to_rl_y(body_y_top + 2.0, 8.5)
    col1_x = body_x * mm
    col2_x = (body_x + 58.0) * mm

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#0f766e"))
    c.drawString(col1_x, y_title, "INDICACIÓN DE ESTUDIOS DE LABORATORIO:")

    # Indicación clínica / Diagnóstico presuntivo si existe
    indication = getattr(order, "clinical_indication", None)
    if indication and str(indication).strip():
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(col1_x, y_title - 5.0 * mm, "Dx / Indicación:")
        c.setFont("Helvetica", 7.5)
        c.drawString(col1_x + 23.0 * mm, y_title - 5.0 * mm, str(indication).strip()[:55])
        y_tests_start = y_title - 11.0 * mm
    else:
        y_tests_start = y_title - 7.0 * mm

    # Límite inferior dinámico basado en la posición del pie del paciente
    pat_y_top = float(fields.get("patient_name", {}).get("y", 178.5)) if isinstance(fields, dict) and "patient_name" in fields else 178.5
    stop_y_bottom = to_rl_y(pat_y_top - 6.0, 8.0)

    # ── LISTA DE ESTUDIOS: LLENADO DINÁMICO (MÍNIMO 10 EN COLUMNA IZQUIERDA ANTES DE INICIAR DERECHA) ───
    if total_tests > 0:
        THRESHOLD_COL1 = 10
        if total_tests <= THRESHOLD_COL1:
            per_col1 = total_tests
        else:
            per_col1 = max(THRESHOLD_COL1, (total_tests + 1) // 2)

        line_h = 5.2 * mm

        for idx, test in enumerate(tests_list):
            if idx < per_col1:
                col_x = col1_x
                row_idx = idx
            else:
                col_x = col2_x
                row_idx = idx - per_col1

            y_pos = y_tests_start - (row_idx * line_h)
            if y_pos < stop_y_bottom:
                continue

            c.setFont("Helvetica-Bold", 8.0)
            c.setFillColor(colors.HexColor("#0f766e"))
            c.drawString(col_x, y_pos, f"{idx + 1}.")
            c.setFont("Helvetica", 8.0)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawString(col_x + 6.0 * mm, y_pos, str(test)[:34])

    c.save()
    buffer.seek(0)
    return buffer


def generate_insurance_preauthorization_pdf(auth_obj, setting=None) -> io.BytesIO:
    """
    Genera el Formulario Oficial Unificado de Historia Clínica y Pre-Autorización
    para compañías aseguradoras (ARS SeNaSa, Humano, Universal, Mapfre, etc.)
    en formato HOJA CARTA (Letter 8.5 × 11 pulg) conforme a los estándares de la Rep. Dominicana.
    """
    # Pre-Autorizaciones e Historias Clínicas para ARS son SIEMPRE en formato Hoja Carta (Letter 8.5 × 11 pulg)
    pagesize = letter
    left_m = 18 * mm
    right_m = 18 * mm
    top_m = 15 * mm
    bottom_m = 15 * mm
    page_w, page_h = letter
    usable_w = page_w - left_m - right_m
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    styles = _get_styles()
    story = []

    def _s_esc(val):
        if val is None:
            return ""
        return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _s_multiline(val):
        if val is None:
            return ""
        escaped = str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return escaped.replace("\r\n", "<br/>").replace("\n", "<br/>")

    # Membrete superior del médico y clínica
    ars_raw = str(getattr(auth_obj, "ars_name", "SEGURO NACIONAL DE SALUD (SeNaSa)") or "SEGURO NACIONAL DE SALUD (SeNaSa)").upper()
    ars_title = _s_esc(ars_raw)
    _build_letterhead(story, styles, setting, subtitle_text=f"SOLICITUD DE COBERTURA • {ars_title}", usable_width=usable_w)

    # Título Principal del Formulario
    title_html = f"<font size=12 color='#0f766e'><b>{ars_title}</b></font><br/>" \
                 f"<font size=11 color='#1e293b'><b>HISTORIA CLÍNICA &amp; SOLICITUD DE PRE-AUTORIZACIÓN</b></font><br/>" \
                 f"<font size=8 color='#64748b'><i>(Para fines de solicitud de procedimientos, cirugías electivas y estudios especiales)</i></font>"
    story.append(Paragraph(title_html, ParagraphStyle("FormHeader", parent=styles["body"], alignment=1, leading=14)))
    story.append(Spacer(1, 8))

    patient = getattr(auth_obj, "patient", None)
    p_info = _extract_patient_display_data(patient)

    # Formateo de fecha de solicitud
    req_date = getattr(auth_obj, "request_date", None)
    if isinstance(req_date, (datetime, date)):
        fecha_str = req_date.strftime("%d/%m/%Y")
    else:
        fecha_str = datetime.now().strftime("%d/%m/%Y")

    # Datos del Afiliado / Póliza
    nss_val = _s_esc(getattr(auth_obj, "affiliate_nss", None) or "N/D")
    card_val = _s_esc(getattr(auth_obj, "affiliate_card_number", None) or p_info.get("insurance_badge", "N/D"))
    contr_val = _s_esc(getattr(auth_obj, "contract_number", None) or "N/D")
    plan_val = _s_esc(getattr(auth_obj, "plan_type", None) or "Básico")
    center_val = _s_esc(getattr(auth_obj, "health_center", None) or (getattr(setting, "clinic_name", "Centro Médico") if setting else "Centro Médico"))
    traffic_acc = "SÍ" if getattr(auth_obj, "is_traffic_accident", False) else "NO"

    # ── BLOQUE 1: DATOS GENERALES DEL AFILIADO Y SEGURO ────────────────────────
    sec_cell_style = ParagraphStyle("SecTitle", parent=styles["body"], fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=colors.HexColor("#0f766e"))
    lbl_style = ParagraphStyle("FieldLbl", parent=styles["body"], fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#475569"))
    val_style = ParagraphStyle("FieldVal", parent=styles["body"], fontName="Helvetica", fontSize=8.0, leading=10, textColor=colors.HexColor("#0f172a"))
    val_bold = ParagraphStyle("FieldValBold", parent=styles["body"], fontName="Helvetica-Bold", fontSize=8.0, leading=10, textColor=colors.HexColor("#0f172a"))

    p_table_data = [
        [
            Paragraph("<b>I. DATOS DEL AFILIADO Y PÓLIZA</b>", sec_cell_style),
            Paragraph(f"<b>Fecha Solicitud:</b> {fecha_str}", lbl_style),
            Paragraph(f"<b>Accidente de Tránsito:</b> <b>{traffic_acc}</b>", lbl_style),
        ],
        [
            Paragraph(f"<b>Nombre del Afiliado:</b><br/>{_s_esc(p_info['name'])}", val_bold),
            Paragraph(f"<b>Cédula / DNI:</b><br/>{_s_esc(p_info['doc_id'])}", val_style),
            Paragraph(f"<b>NSS (Seguridad Social):</b><br/>{nss_val}", val_style),
        ],
        [
            Paragraph(f"<b>No. Carnet / Póliza:</b><br/>{card_val}", val_style),
            Paragraph(f"<b>Contrato No. / Plan:</b><br/>{contr_val} • {plan_val}", val_style),
            Paragraph(f"<b>Edad / Sexo:</b><br/>{_s_esc(p_info['age_str'] or 'N/D')} / {_s_esc(p_info['gender'] or 'N/D')}", val_style),
        ],
        [
            Paragraph(f"<b>Teléfonos:</b><br/>{_s_esc(p_info['phone'])}", val_style),
            Paragraph(f"<b>Centro donde se realizará:</b><br/>{center_val}", val_style),
            Paragraph(f"<b>Alergias Conocidas:</b><br/><font color='#b91c1c'>{_s_esc(p_info['allergies'])}</font>", val_style),
        ]
    ]

    p_table = Table(p_table_data, colWidths=[usable_w * 0.40, usable_w * 0.32, usable_w * 0.28])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('SPAN', (0, 0), (0, 0)),
    ]))
    story.append(p_table)
    story.append(Spacer(1, 6))

    # ── BLOQUE 2: HISTORIA DE LA ENFERMEDAD ACTUAL & SÍNTOMAS ─────────────────
    onset_date = _s_esc(getattr(auth_obj, "symptoms_onset_date", None) or "No especificado")
    cur_history = getattr(auth_obj, "current_illness_history", None) or "Sin registro de cuadro clínico actual."

    illness_data = [
        [
            Paragraph("<b>II. HISTORIA DE LA ENFERMEDAD ACTUAL</b>", sec_cell_style),
            Paragraph(f"<b>¿Desde qué fecha iniciaron los síntomas?:</b> <b>{onset_date}</b>", lbl_style),
        ],
        [
            Paragraph(_s_multiline(cur_history), val_style),
            Paragraph("", val_style),
        ]
    ]
    illness_table = Table(illness_data, colWidths=[usable_w * 0.60, usable_w * 0.40])
    illness_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.HexColor("#e2e8f0")),
        ('SPAN', (0, 1), (1, 1)),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(illness_table)
    story.append(Spacer(1, 6))

    # ── BLOQUE 3: ANTECEDENTES Y ESTUDIOS ESPECIALES (2 COLUMNAS) ──────────────
    pers_fam = getattr(auth_obj, "personal_family_history", None) or "Sin antecedentes relevantes reportados."
    labs_studies = getattr(auth_obj, "diagnostic_tests", None) or "Ver resultados anexos al expediente."

    ant_data = [
        [
            Paragraph("<b>III. ANTECEDENTES PERSONALES Y FAMILIARES</b>", sec_cell_style),
            Paragraph("<b>IV. LABORATORIOS Y ESTUDIOS REALIZADOS</b>", sec_cell_style),
        ],
        [
            Paragraph(_s_multiline(pers_fam), val_style),
            Paragraph(_s_multiline(labs_studies), val_style),
        ]
    ]
    ant_table = Table(ant_data, colWidths=[usable_w * 0.50, usable_w * 0.50])
    ant_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(ant_table)
    story.append(Spacer(1, 6))

    # ── BLOQUE 4: DIAGNÓSTICOS (PRESUNTIVO Y DEFINITIVO CIE-10) ───────────────
    dx_pres = getattr(auth_obj, "presumptive_diagnosis", None) or "En estudio"
    dx_def = getattr(auth_obj, "definitive_diagnosis", None) or "Sin diagnóstico definitivo registrado"
    sec_dx = getattr(auth_obj, "secondary_diagnoses", None) or ""

    dx_rows = [
        [
            Paragraph("<b>V. DIAGNÓSTICOS CLÍNICOS</b>", sec_cell_style),
            Paragraph("", val_style)
        ],
        [
            Paragraph("<b>Diagnóstico Presuntivo:</b>", lbl_style),
            Paragraph(_s_esc(dx_pres), val_bold),
        ],
        [
            Paragraph("<b>Diagnóstico Definitivo (CIE-10):</b>", lbl_style),
            Paragraph(f"<font color='#0f766e'><b>{_s_esc(dx_def)}</b></font>", val_bold),
        ]
    ]
    if sec_dx and str(sec_dx).strip():
        dx_rows.append([
            Paragraph("<b>Otros Diagnósticos:</b>", lbl_style),
            Paragraph(_s_multiline(str(sec_dx)).replace("<br/>", " • "), val_style),
        ])

    dx_table = Table(dx_rows, colWidths=[usable_w * 0.30, usable_w * 0.70])
    dx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('SPAN', (0, 0), (1, 0)),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(dx_table)
    story.append(Spacer(1, 6))

    # ── BLOQUE 5: PROCEDIMIENTOS SOLICITADOS (CÓDIGOS SIMON / CUPS) ────────────
    story.append(Paragraph("<b>VI. NOMBRE DEL (LOS) PROCEDIMIENTO(S) SOLICITADO(S)</b>", sec_cell_style))
    story.append(Spacer(1, 2))

    # Parsear procedimientos desde JSON o texto
    raw_proc = getattr(auth_obj, "procedures_json", None) or ""
    proc_list = []
    if raw_proc and str(raw_proc).strip().startswith("["):
        try:
            parsed = json.loads(raw_proc)
            if isinstance(parsed, list):
                proc_list = parsed
        except Exception:
            pass

    if not proc_list and raw_proc:
        for idx, line in enumerate(str(raw_proc).splitlines()):
            if line.strip():
                proc_list.append({"code": "", "procedure": line.strip()})

    proc_table_rows = [
        [
            Paragraph("<b>Item</b>", lbl_style),
            Paragraph("<b>Código SIMON / CUP</b>", lbl_style),
            Paragraph("<b>Descripción del Procedimiento / Cirugía</b>", lbl_style),
        ]
    ]

    if proc_list:
        for idx, item in enumerate(proc_list):
            c_code = _s_esc(item.get("code", "") if isinstance(item, dict) else "")
            c_name = _s_esc(item.get("procedure", "") if isinstance(item, dict) else str(item))
            proc_table_rows.append([
                Paragraph(f"{idx + 1}.", val_bold),
                Paragraph(f"<font color='#0f766e'><b>{c_code or '---'}</b></font>", val_bold),
                Paragraph(str(c_name), val_style),
            ])
    else:
        proc_table_rows.append([
            Paragraph("1.", val_bold),
            Paragraph("---", val_style),
            Paragraph("Procedimiento clínico conforme a indicación médica adjunta.", val_style),
        ])

    proc_table = Table(proc_table_rows, colWidths=[usable_w * 0.08, usable_w * 0.27, usable_w * 0.65])
    proc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(proc_table)
    story.append(Spacer(1, 6))

    # ── BLOQUE 6: TRATAMIENTO Y OBSERVACIONES ──────────────────────────────────
    treatment_val = getattr(auth_obj, "treatment_plan", None) or ""
    notes_val = getattr(auth_obj, "notes", None) or ""

    if (treatment_val and str(treatment_val).strip()) or (notes_val and str(notes_val).strip()):
        tx_data = [
            [Paragraph("<b>VII. TRATAMIENTO PROPUESTO Y OBSERVACIONES</b>", sec_cell_style)],
        ]
        comb_tx = ""
        if str(treatment_val).strip():
            comb_tx += f"<b>Plan Terapéutico:</b> {_s_multiline(str(treatment_val).strip())}<br/>"
        if str(notes_val).strip():
            comb_tx += f"<b>Observaciones:</b> {_s_multiline(str(notes_val).strip())}"
        tx_data.append([Paragraph(comb_tx, val_style)])

        tx_table = Table(tx_data, colWidths=[usable_w])
        tx_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(tx_table)
        story.append(Spacer(1, 8))

    # ── BLOQUE 7: FIRMA Y SELLO DEL MÉDICO TRATANTE ────────────────────────────
    doc_user = getattr(auth_obj, "doctor", None)
    doc_name = _s_esc(getattr(doc_user, "name", None) or (getattr(setting, "doctor_name", "Dr. Carlos M. Heredia") if setting else "Dr. Carlos M. Heredia"))
    doc_spec = _s_esc(getattr(doc_user, "specialty", None) or (getattr(setting, "specialty", "Ginecología y Obstetricia") if setting else "Ginecología y Obstetricia"))
    doc_code = _s_esc(getattr(auth_obj, "doctor_code", None) or (getattr(setting, "exequatur", "24241") if setting else "24241"))

    sig_data = [
        [
            Paragraph(f"<b>Fecha de Emisión:</b> {fecha_str}<br/><b>Centro:</b> {center_val}", val_style),
            Paragraph("____________________________________________<br/>"
                      f"<b>{doc_name}</b><br/>"
                      f"<font size=7.5 color='#475569'>{doc_spec}</font><br/>"
                      f"<font size=7.5 color='#0f766e'><b>Exequátur / Cód. Médico: {doc_code}</b></font><br/>"
                      "<font size=7 color='#64748b'>Firma y Sello del Médico Tratante</font>",
                      ParagraphStyle("SigBlock", parent=styles["body"], alignment=1, leading=10))
        ]
    ]
    sig_table = Table(sig_data, colWidths=[usable_w * 0.45, usable_w * 0.55])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(KeepTogether([sig_table]))

    doc.build(story)
    buffer.seek(0)
    return buffer



