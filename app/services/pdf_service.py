import io
import os
import json
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

def _build_letterhead(story: list, styles: dict, setting=None, subtitle_text: str = "") -> None:
    """
    Construye el membrete profesional del consultorio con logo opcional.
    Si setting.doctor_logo_path existe y el archivo es accesible, lo incluye.
    """
    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    phone = getattr(setting, "phone", "") if setting else ""
    email = getattr(setting, "email", "") if setting else ""
    logo_path = getattr(setting, "doctor_logo_path", None) if setting else None

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

    header_table = Table([[left_col, right_col]], colWidths=[3.8 * inch, 3.2 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR, spaceBefore=2, spaceAfter=10))


def generate_prescription_pdf(consultation, setting=None) -> io.BytesIO:
    """
    Genera el PDF oficial de Receta Médica (Prescription) con formato médico profesional.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    
    styles = _get_styles()
    story = []

    # 1. Membrete con logo opcional
    _build_letterhead(story, styles, setting, subtitle_text="")

    # Variables adicionales de la consulta
    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    phone = getattr(setting, "phone", "") if setting else ""
    address = getattr(setting, "address", "") if setting else ""

    # 2. Información del Paciente
    patient = getattr(consultation, "patient", None)
    patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Paciente General"
    doc_id = getattr(patient, "document_id", "N/A") if patient else "N/A"
    age_str = ""
    if patient and getattr(patient, "birth_date", None):
        try:
            today = datetime.now().date()
            bdate = patient.birth_date
            age = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
            age_str = f" • Edad: {age} años"
        except Exception:
            pass
            
    consultation_date = consultation.created_at.strftime("%d/%m/%Y %H:%M") if consultation.created_at else datetime.now().strftime("%d/%m/%Y")
    
    patient_info_data = [
        [
            Paragraph(f"<b>Paciente:</b> {patient_name} (ID/DNI: {doc_id}){age_str}", styles["body"]),
            Paragraph(f"<b>Fecha:</b> {consultation_date}", styles["body"])
        ]
    ]
    p_table = Table(patient_info_data, colWidths=[4.8 * inch, 2.2 * inch])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(p_table)
    story.append(Spacer(1, 14))
    
    # 3. Diagnóstico (si existe)
    if consultation.diagnosis:
        story.append(Paragraph("<b>Diagnóstico:</b>", styles["section"]))
        story.append(Paragraph(consultation.diagnosis.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 10))
        
    # 4. Símbolo Rp. y Prescripción Médica
    story.append(Paragraph("<b>Rp. / Medicación y Prescripción</b>", styles["section"]))
    
    rx_content = consultation.prescription or "Sin medicamentos prescritos registrados."
    rx_formatted = rx_content.replace("\n", "<br/>")
    
    rx_table = Table([[Paragraph(rx_formatted, styles["rx"])]], colWidths=[7.0 * inch])
    rx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdfa")), # Teal 50
        ('BOX', (0, 0), (-1, -1), 1, SECONDARY_COLOR),
        ('PADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(rx_table)
    story.append(Spacer(1, 12))
    
    # 5. Indicaciones Generales y Tratamiento (si existe)
    if consultation.treatment:
        story.append(Paragraph("<b>Indicaciones Generales y Cuidados:</b>", styles["section"]))
        story.append(Paragraph(consultation.treatment.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 12))
        
    # 6. Bloque de Firma y Sello Médico (al final de la página)
    story.append(Spacer(1, 30))
    signature_block = [
        [
            Paragraph(f"<font size=8 color='#64748b'>{address}</font>", styles["body"]),
            Paragraph(f"<br/><br/>________________________________________<br/><b>{doctor_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_table = Table(signature_block, colWidths=[3.8 * inch, 3.2 * inch])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(KeepTogether(sig_table))
    
    # 7. Pie de página
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceBefore=4, spaceAfter=6))
    story.append(Paragraph("Documento médico oficial generado desde SSCP Desktop • Validez local", styles["footer"]))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_consultation_report_pdf(consultation, setting=None, vitals=None) -> io.BytesIO:
    """
    Genera el informe clínico detallado de la consulta médica en formato PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    
    styles = _get_styles()
    story = []

    # Membrete con logo opcional
    _build_letterhead(story, styles, setting, subtitle_text="INFORME DE CONSULTA CLÍNICA")

    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"

    # Datos Paciente
    patient = getattr(consultation, "patient", None)
    patient_name = f"{patient.first_name} {patient.last_name}" if patient else "N/A"
    doc_id = getattr(patient, "document_id", "N/A") if patient else "N/A"
    blood_type = getattr(patient, "blood_type", "No registrado") if patient else "No registrado"
    allergies = getattr(patient, "allergies", "Ninguna registrada") if patient else "Ninguna registrada"
    consultation_date = consultation.created_at.strftime("%d/%m/%Y %H:%M") if consultation.created_at else datetime.now().strftime("%d/%m/%Y")
    
    p_data = [
        [
            Paragraph(f"<b>Paciente:</b> {patient_name}", styles["body"]),
            Paragraph(f"<b>DNI/Cédula:</b> {doc_id}", styles["body"]),
            Paragraph(f"<b>Fecha:</b> {consultation_date}", styles["body"]),
        ],
        [
            Paragraph(f"<b>Grupo Sanguíneo:</b> {blood_type}", styles["body"]),
            Paragraph(f"<b>Alergias:</b> <font color='#b91c1c'>{allergies}</font>", styles["body"]),
            Paragraph(f"<b>Consulta ID:</b> #{consultation.id}", styles["body"]),
        ]
    ]
    patient_table = Table(p_data, colWidths=[2.6 * inch, 2.4 * inch, 2.0 * inch])
    patient_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(patient_table)
    story.append(Spacer(1, 12))
    
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
        vt_table = Table(v_data, colWidths=[1.0 * inch] * 7)
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
        ("Motivo de Consulta", consultation.reason),
    ]
    if getattr(consultation, "clinical_history", None) and consultation.clinical_history.strip():
        sections.append(("Historia Clínica / Evolución Médica", consultation.clinical_history))
    else:
        if consultation.symptoms:
            sections.append(("Síntomas / Anamnesis", consultation.symptoms))
        if consultation.physical_exam:
            sections.append(("Examen Físico", consultation.physical_exam))

    if consultation.diagnosis and consultation.diagnosis.strip() and consultation.diagnosis.strip() not in ("Historia Clínica Unificada", "Ver Historia Clínica"):
        sections.append(("Diagnóstico Clínico / CIE-10", consultation.diagnosis))

    sections.extend([
        ("Plan Terapéutico y Tratamiento", consultation.treatment),
        ("Prescripción Médica (Medicamentos)", consultation.prescription),
        ("Notas Clínicas Adicionales", consultation.notes),
    ])

    for title, content in sections:
        if content and content.strip():
            story.append(Paragraph(f"<b>{title}:</b>", styles["section"]))
            story.append(Paragraph(content.replace("\n", "<br/>"), styles["body"]))
            story.append(Spacer(1, 8))
            
    # Firma
    story.append(Spacer(1, 20))
    sig_data = [
        [
            "",
            Paragraph(f"<br/><br/>________________________________________<br/><b>{doctor_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_t = Table(sig_data, colWidths=[4.0 * inch, 3.0 * inch])
    sig_t.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(KeepTogether(sig_t))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_quick_prescription_pdf(patient, prescription_text: str, diagnosis: str = None, setting=None, doctor_name: str = None) -> io.BytesIO:
    """
    Genera el PDF de Receta Rápida (F2) sin necesidad de una consulta médica completa.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
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

    _build_letterhead(story, styles, tmp, subtitle_text="RECETA MÉDICA DIRECTA")

    # Paciente
    p_name = f"{patient.first_name} {patient.last_name}" if patient else "Paciente"
    doc_id = getattr(patient, "document_id", "N/D") if patient else "N/D"
    allergies = getattr(patient, "allergies", "Ninguna") or "Ninguna"
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    p_data = [
        [
            Paragraph(f"<b>Paciente:</b> {p_name} (DNI: {doc_id})", styles["body"]),
            Paragraph(f"<b>Fecha:</b> {now_str}", styles["body"])
        ],
        [
            Paragraph(f"<b>Alergias Conocidas:</b> <font color='#b91c1c'>{allergies}</font>", styles["body"]),
            Paragraph(f"<b>Tipo:</b> Emisión Rápida", styles["body"])
        ]
    ]
    ptable = Table(p_data, colWidths=[4.6 * inch, 2.4 * inch])
    ptable.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(ptable)
    story.append(Spacer(1, 14))

    # Diagnóstico
    if diagnosis and diagnosis.strip():
        story.append(Paragraph("<b>Diagnóstico / Indicación Clínica:</b>", styles["section"]))
        story.append(Paragraph(diagnosis.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 10))

    # Prescripción
    story.append(Paragraph("<b>Rp. / Medicación y Prescripción</b>", styles["section"]))
    rx_fmt = (prescription_text or "Sin prescripción").replace("\n", "<br/>")
    rx_t = Table([[Paragraph(rx_fmt, styles["rx"])]], colWidths=[7.0 * inch])
    rx_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
        ('BOX', (0, 0), (-1, -1), 1, SECONDARY_COLOR),
        ('PADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(rx_t)

    # Firma
    story.append(Spacer(1, 40))
    sig_data = [
        [
            Paragraph(f"<font size=8 color='#64748b'>{address}</font>", styles["body"]),
            Paragraph(f"________________________________________<br/><b>{doc_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_t = Table(sig_data, colWidths=[3.8 * inch, 3.2 * inch])
    sig_t.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'CENTER')]))
    story.append(KeepTogether(sig_t))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_medical_license_pdf(license, setting=None) -> io.BytesIO:
    """
    Genera el Certificado Oficial de Licencia Médica / Reposo Laboral (F5).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = _get_styles()
    story = []

    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    phone = getattr(setting, "phone", "") if setting else ""
    address = getattr(setting, "address", "") if setting else ""

    # Membrete con logo opcional
    _build_letterhead(story, styles, setting, subtitle_text="")

    # Título del Certificado
    title_p = Paragraph("<font size=14 color='#0f766e'><b>CERTIFICADO MÉDICO DE LICENCIA / REPOSO</b></font>", styles["title"])
    story.append(title_p)
    story.append(Spacer(1, 12))

    dest = license.workplace_or_school or "A QUIEN PUEDA INTERESAR"
    story.append(Paragraph(f"<b>Dirigido a:</b> {dest}", styles["body_bold"]))
    story.append(Spacer(1, 12))

    patient = license.patient
    p_name = f"{patient.first_name} {patient.last_name}" if patient else "El paciente"
    doc_id = getattr(patient, "document_id", "N/D") if patient else "N/D"
    start_str = license.start_date.strftime("%d/%m/%Y")
    end_str = license.end_date.strftime("%d/%m/%Y")

    cert_text = (
        f"Por medio de la presente certifico que he examinado clínicamente a <b>{p_name}</b>, "
        f"portador(a) del documento de identidad <b>{doc_id}</b>, diagnosticándole:<br/><br/>"
        f"<b>DIAGNÓSTICO:</b> {license.diagnosis}<br/><br/>"
        f"Por tal motivo, se indica reposo médico por un período de <b>{license.days_rest} día(s)</b>, "
        f"comprendido desde el día <b>{start_str}</b> hasta el día <b>{end_str}</b> inclusive, "
        f"debiendo reincorporarse a sus labores habituales al término del mismo."
    )
    story.append(Paragraph(cert_text, styles["body"]))
    story.append(Spacer(1, 14))

    if license.notes and license.notes.strip():
        story.append(Paragraph(f"<b>Observaciones e Indicaciones Médicas:</b><br/>{license.notes}", styles["body"]))
        story.append(Spacer(1, 14))

    # Fecha y lugar
    today_str = datetime.now().strftime("%d de %B de %Y")
    story.append(Paragraph(f"Expedido para los fines pertinentes en fecha {today_str}.", styles["body"]))
    story.append(Spacer(1, 45))

    # Firma
    sig_data = [
        [
            Paragraph(f"<font size=8 color='#64748b'>{address}</font>", styles["body"]),
            Paragraph(f"________________________________________<br/><b>{doctor_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_t = Table(sig_data, colWidths=[3.8 * inch, 3.2 * inch])
    sig_t.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'CENTER')]))
    story.append(KeepTogether(sig_t))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_medical_reference_pdf(reference, setting=None) -> io.BytesIO:
    """
    Genera la Carta Oficial de Referencia e Interconsulta Médica (F10).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = _get_styles()
    story = []

    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    phone = getattr(setting, "phone", "") if setting else ""
    address = getattr(setting, "address", "") if setting else ""

    # Membrete con logo opcional
    _build_letterhead(story, styles, setting, subtitle_text="")

    story.append(Paragraph("<font size=14 color='#0f766e'><b>CARTA DE REFERENCIA E INTERCONSULTA MÉDICA</b></font>", styles["title"]))
    story.append(Spacer(1, 14))

    patient = reference.patient
    p_name = f"{patient.first_name} {patient.last_name}" if patient else "Paciente"
    doc_id = getattr(patient, "document_id", "N/D") if patient else "N/D"
    allergies = getattr(patient, "allergies", "Ninguna") or "Ninguna"

    ref_info = [
        [
            Paragraph(f"<b>Dirigido a:</b> {reference.referred_to_doctor_or_specialty}", styles["body"]),
            Paragraph(f"<b>Institución:</b> {reference.institution or 'Centro de Referencia'}", styles["body"])
        ],
        [
            Paragraph(f"<b>Paciente:</b> {p_name} (DNI: {doc_id})", styles["body"]),
            Paragraph(f"<b>Alergias:</b> <font color='#b91c1c'>{allergies}</font>", styles["body"])
        ]
    ]
    rtable = Table(ref_info, colWidths=[3.5 * inch, 3.5 * inch])
    rtable.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(rtable)
    story.append(Spacer(1, 14))

    story.append(Paragraph("<b>Motivo de la Derivación:</b>", styles["section"]))
    story.append(Paragraph(reference.reason_for_referral.replace("\n", "<br/>"), styles["body"]))
    story.append(Spacer(1, 10))

    if reference.clinical_summary and reference.clinical_summary.strip():
        story.append(Paragraph("<b>Resumen Clínico y Hallazgos Relevantes:</b>", styles["section"]))
        story.append(Paragraph(reference.clinical_summary.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 10))

    if reference.notes and reference.notes.strip():
        story.append(Paragraph("<b>Notas Adicionales / Exámenes Adjuntos:</b>", styles["section"]))
        story.append(Paragraph(reference.notes.replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 35))
    sig_data = [
        [
            Paragraph(f"<font size=8 color='#64748b'>{address}</font>", styles["body"]),
            Paragraph(f"________________________________________<br/><b>{doctor_name}</b><br/>{specialty}", styles["body"])
        ]
    ]
    sig_t = Table(sig_data, colWidths=[3.8 * inch, 3.2 * inch])
    sig_t.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'CENTER')]))
    story.append(KeepTogether(sig_t))

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

    # --- Fecha de generación ---
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    address = getattr(setting, "address", "") if setting else ""
    currency = getattr(setting, "currency", "RD$") if setting else "RD$"

    story.append(Paragraph(
        f"<font size=8 color='#94a3b8'>Generado el {now_str} • Sistema SSCP Desktop</font>",
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


def generate_talonario_overlay_pdf(patient, prescription_text: str, setting=None) -> io.BytesIO:
    """
    Genera un PDF de posicionamiento exacto para imprimir encima del talonario
    preimpreso del Dr. Carlos M. Heredia (21.7 × 13.6 cm).

    El talonario ya tiene el membrete, el símbolo Rp. y las líneas PACIENTE/EDAD/CED/FECHA.
    Este PDF solo coloca los datos de texto en coordenadas absolutas que coinciden
    con esos campos impresos en el papel físico.

    Coordenadas medidas desde la esquina inferior-izquierda del papel (sistema ReportLab):
        y=0 es el fondo del papel, y=PAGE_H es la parte superior.
    """
    # Tamaño real del talonario en puntos (1mm = 2.8346 pt)
    PAGE_W = 21.7 * mm
    PAGE_H = 13.6 * mm   # <- se ajusta a cm; ReportLab trabaja en puntos (1cm = 28.35pt)

    # Corregido a puntos reales:
    PAGE_W_pt = 217 * mm   # 21.7 cm -> 217 mm -> en puntos
    PAGE_H_pt = 136 * mm   # 13.6 cm -> 136 mm -> en puntos

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W_pt, PAGE_H_pt))

    # ── Datos del paciente ─────────────────────────────────────────────────────
    p = patient
    patient_name = str(f"{p.first_name or ''} {p.last_name or ''}".strip() or "Paciente") if p else "Paciente"
    doc_id = str(getattr(p, "document_id", None) or "N/D")
    today = datetime.now()
    fecha_str = today.strftime("%d/%m/%Y")

    # Calcular edad
    age_str = ""
    birth = getattr(p, "date_of_birth", None) or getattr(p, "birth_date", None)
    if birth:
        try:
            if isinstance(birth, str):
                birth = datetime.strptime(birth, "%Y-%m-%d").date()
            td = today.date() if hasattr(today, "date") else today
            age = td.year - birth.year - ((td.month, td.day) < (birth.month, birth.day))
            age_str = str(age)
        except Exception:
            age_str = ""

    # ── Configuración de fuentes ───────────────────────────────────────────────
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#1e293b"))

    # ── ZONA Rp. — Cuerpo de la prescripción ──────────────────────────────────
    # El área en blanco del talonario va desde ~95mm hasta ~55mm del fondo
    # (medida desde abajo: entre y=55mm y y=95mm del papel de 136mm de alto)
    rx_x = 12 * mm        # margen izquierdo del área Rp.
    rx_y_top = 95 * mm    # posición Y superior del área de prescripción
    rx_line_h = 5 * mm    # interlineado entre líneas de texto
    rx_max_w = PAGE_W_pt - (rx_x + 8 * mm)   # ancho máximo del texto

    c.setFont("Helvetica", 9)
    lines = (prescription_text or "").split("\n")
    y_cursor = rx_y_top
    for line in lines:
        if y_cursor < 57 * mm:   # no sobrepasar la línea PACIENTE
            break
        # Salto de línea automático si la línea es larga
        words = line.split(" ")
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if c.stringWidth(test, "Helvetica", 9) < rx_max_w:
                current_line = test
            else:
                if current_line:
                    c.drawString(rx_x, y_cursor, str(current_line or ""))
                    y_cursor -= rx_line_h
                    if y_cursor < 57 * mm:
                        break
                current_line = word
        if current_line and y_cursor >= 57 * mm:
            c.drawString(rx_x, y_cursor, str(current_line or ""))
            y_cursor -= rx_line_h

    # ── LÍNEA PACIENTE ─────────────────────────────────────────────────────────
    # En el talonario: "PACIENTE: _______________"
    # La línea está a ~22mm del fondo del papel (y=22mm desde abajo)
    c.setFont("Helvetica", 9)
    c.drawString(28 * mm, 22 * mm, str(patient_name or ""))

    # ── LÍNEA EDAD / CED. / FECHA ──────────────────────────────────────────────
    # "EDAD: ___ CED.: ___________________ FECHA: ___________"
    # La línea está a ~12mm del fondo
    c.drawString(15 * mm, 12 * mm, str(age_str or ""))        # valor de EDAD
    c.drawString(50 * mm, 12 * mm, str(doc_id or ""))          # valor de CED.
    c.drawString(140 * mm, 12 * mm, str(fecha_str or ""))      # valor de FECHA

    c.save()
    buffer.seek(0)
    return buffer


def generate_lab_order_pdf(order, setting=None) -> io.BytesIO:
    """
    Genera la Orden / Solicitud Oficial de Estudios de Laboratorio Clínico (Fase 3 v1.2.0).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = _get_styles()
    story = []

    # Membrete con logo opcional
    _build_letterhead(story, styles, setting, subtitle_text="ORDEN DE ANÁLISIS CLÍNICOS")

    story.append(Paragraph("<font size=14 color='#0f766e'><b>SOLICITUD DE ESTUDIOS DE LABORATORIO</b></font>", styles["title"]))
    story.append(Spacer(1, 10))

    patient = order.patient
    p_name = f"{patient.last_name}, {patient.first_name}" if patient else "Paciente"
    doc_id = getattr(patient, "document_id", "Sin DNI") or "Sin DNI"
    allergies = getattr(patient, "allergies", "Ninguna") or "Ninguna"

    # Cálculo o lectura de edad
    age_str = "N/D"
    if patient and getattr(patient, "date_of_birth", None):
        try:
            today = datetime.now().date()
            dob = patient.date_of_birth
            age_val = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            age_str = f"{age_val} años"
        except Exception:
            age_str = "N/D"

    gender = getattr(patient, "gender", "N/D") or "N/D"
    insurance = getattr(patient, "insurance_name", "Privado") or "Privado"
    ins_num = getattr(patient, "insurance_number", "") or ""
    insurance_full = f"{insurance} (No. {ins_num})" if ins_num else insurance

    order_date_str = order.order_date.strftime("%d/%m/%Y") if order.order_date else datetime.now().strftime("%d/%m/%Y")

    # Ficha de identificación del paciente y solicitud
    patient_info = [
        [
            Paragraph(f"<b>Paciente:</b> {p_name}", styles["body"]),
            Paragraph(f"<b>Cédula / DNI:</b> {doc_id}", styles["body"]),
        ],
        [
            Paragraph(f"<b>Edad / Sexo:</b> {age_str} / {gender}", styles["body"]),
            Paragraph(f"<b>ARS / Seguro:</b> {insurance_full}", styles["body"]),
        ],
        [
            Paragraph(f"<b>Fecha de Solicitud:</b> {order_date_str}", styles["body"]),
            Paragraph(f"<b>Alergias Conocidas:</b> <font color='#b91c1c'><b>{allergies}</b></font>", styles["body"]),
        ]
    ]

    p_table = Table(patient_info, colWidths=[3.7 * inch, 3.3 * inch])
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
    story.append(Spacer(1, 14))

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

    # ── COLUMNA 3: SONOGRAFÍA (8 items) ──
    "Pélvica": (95.3, 48.5),
    "Transvaginal": (95.3, 45.4),
    "Sonomamografía": (95.3, 42.4),
    "Obstetricia": (95.3, 39.3),
    "Abdominal": (95.3, 36.2),
    "Genética": (95.3, 33.1),
    "Morfológica": (95.3, 30.1),
    "Perfil hemodinámico": (95.3, 27.0),
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

    El papel físico es VERTICAL (13.6 cm ancho × 21.7 cm alto) y contiene:
      1. Membrete superior del Dr. Carlos M. Heredia y Centro Médico María Dolores (hasta y=162mm).
      2. Zona central para los estudios (y=160mm hasta y=30mm).
      3. Líneas inferiores preimpresas:
         NOMBRE: ____________________________________________________________________ (y=22.0 mm)
         FECHA: ___________    EDAD: ___________    SEXO: ___________                   (y=14.8 mm)
                                            Firma                                       (y=6.6 mm)

    Conforme a las especificaciones del médico:
      - NO imprime casillas [ ], ni [X], ni paréntesis ( ), ni palomitas.
      - Imprime una lista organizada y nítida con cada uno de los estudios solicitados,
        uno debajo de otro, numerados de forma clara y elegante (1., 2., 3.).
      - Hasta 16 estudios en 1 sola columna vertical con interlineado óptimo.
      - Más de 16 estudios en 2 columnas balanceadas.
      - Al pie imprime los datos del paciente alineados exactamente sobre las líneas preimpresas.
    """
    # Dimensiones exactas del talonario vertical (13.6 cm ancho × 21.7 cm alto)
    PAGE_W_pt = 136.0 * mm
    PAGE_H_pt = 217.0 * mm

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W_pt, PAGE_H_pt))

    # ── Datos del paciente ─────────────────────────────────────────────────────
    p = getattr(order, "patient", None)
    if p:
        p_name = f"{getattr(p, 'first_name', '') or ''} {getattr(p, 'last_name', '') or ''}".strip()
        patient_name = p_name if p_name else "Paciente"
        gender_raw = getattr(p, "gender", "") or ""
    else:
        patient_name = "Paciente"
        gender_raw = ""

    # Formateo de sexo (Femenino / Masculino)
    if str(gender_raw).upper() in ("F", "FEMENINO", "FEMALE"):
        gender_str = "Femenino"
    elif str(gender_raw).upper() in ("M", "MASCULINO", "MALE"):
        gender_str = "Masculino"
    else:
        gender_str = str(gender_raw or "")

    # Fecha de la orden
    ord_date = getattr(order, "order_date", None)
    if isinstance(ord_date, (datetime, date)):
        fecha_str = ord_date.strftime("%d/%m/%Y")
    else:
        fecha_str = datetime.now().strftime("%d/%m/%Y")

    # Cálculo de edad
    age_str = ""
    birth = getattr(p, "date_of_birth", None) or getattr(p, "birth_date", None) if p else None
    if birth:
        try:
            if isinstance(birth, str):
                birth = datetime.strptime(birth, "%Y-%m-%d").date()
            td = datetime.now().date()
            age = td.year - birth.year - ((td.month, td.day) < (birth.month, birth.day))
            age_str = f"{age} años"
        except Exception:
            age_str = ""

    # Parsear lista de análisis solicitados
    tests_list = []
    if order and getattr(order, "tests_requested", None):
        try:
            tests_list = json.loads(order.tests_requested)
        except Exception:
            tests_list = [t.strip() for t in str(order.tests_requested).splitlines() if t.strip()]

    # Filtrar vacíos
    tests_list = [str(t).strip() for t in tests_list if str(t).strip()]

    # ── TÍTULO E INDICACIÓN CLÍNICA (ZONA CENTRAL DEL PAPEL VERTICAL) ─────────
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#0f766e"))
    c.drawString(14.0 * mm, 158.0 * mm, "INDICACIÓN DE ESTUDIOS DE LABORATORIO:")

    # Indicación clínica / Diagnóstico presuntivo si existe
    indication = getattr(order, "clinical_indication", None)
    if indication and str(indication).strip():
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(14.0 * mm, 153.0 * mm, "Dx / Indicación:")
        c.setFont("Helvetica", 7.5)
        c.drawString(38.0 * mm, 153.0 * mm, str(indication).strip()[:60])
        y_tests_start = 147.0 * mm
    else:
        y_tests_start = 151.0 * mm

    # ── LISTA DE ESTUDIOS: UNO DEBAJO DE OTRO, BIEN ORGANIZADO Y BONITO ───────
    # Sin palomitas ni cuadritos: Lista numerada limpia y profesional
    total_tests = len(tests_list)
    if total_tests > 0:
        if total_tests <= 16:
            # 1 sola columna vertical espaciosa (uno debajo de otro)
            avail_h = y_tests_start / mm - 33.0
            line_h = min(6.0, max(4.6, avail_h / max(1, total_tests))) * mm
            y_cursor = y_tests_start
            for idx, test in enumerate(tests_list):
                if y_cursor < 32.0 * mm:
                    break
                # Número en negrita teal
                c.setFont("Helvetica-Bold", 8.5)
                c.setFillColor(colors.HexColor("#0f766e"))
                c.drawString(14.0 * mm, y_cursor, f"{idx + 1}.")
                # Nombre del estudio en color slate oscuro
                c.setFont("Helvetica", 8.5)
                c.setFillColor(colors.HexColor("#0f172a"))
                c.drawString(20.0 * mm, y_cursor, str(test)[:56])
                y_cursor -= line_h
        else:
            # 2 columnas balanceadas organizadas una debajo de otra
            per_col = (total_tests + 1) // 2
            avail_h = y_tests_start / mm - 33.0
            line_h = min(4.8, max(3.8, avail_h / per_col)) * mm
            col1_x = 12.0 * mm
            col2_x = 74.0 * mm

            for idx, test in enumerate(tests_list):
                if idx < per_col:
                    col_x = col1_x
                    row_idx = idx
                else:
                    col_x = col2_x
                    row_idx = idx - per_col

                y_pos = y_tests_start - (row_idx * line_h)
                if y_pos < 32.0 * mm:
                    continue

                c.setFont("Helvetica-Bold", 7.5)
                c.setFillColor(colors.HexColor("#0f766e"))
                c.drawString(col_x, y_pos, f"{idx + 1}.")
                c.setFont("Helvetica", 7.5)
                c.setFillColor(colors.HexColor("#0f172a"))
                c.drawString(col_x + 5.0 * mm, y_pos, str(test)[:32])


    # ── PIE DEL TALONARIO: DATOS DEL PACIENTE ─────────────────────────────────
    # 1. NOMBRE: _______________________________________________________________
    # Línea preimpresa a y = 22.0 mm. Se imprime el nombre después de 'NOMBRE:'
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(22.0 * mm, 22.0 * mm, str(patient_name or ""))

    # 2. FECHA: _______________ EDAD: _______________ SEXO: _______________
    # Línea preimpresa a y = 14.8 mm del fondo
    c.setFont("Helvetica", 8.0)
    c.drawString(20.0 * mm, 14.8 * mm, str(fecha_str or ""))
    c.drawString(68.0 * mm, 14.8 * mm, str(age_str or ""))
    c.drawString(108.0 * mm, 14.8 * mm, str(gender_str or ""))

    c.save()
    buffer.seek(0)
    return buffer


