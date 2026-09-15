import io
import os
from datetime import datetime
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
from reportlab.lib.units import inch

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
        
    # Secciones de la consulta
    sections = [
        ("Motivo de Consulta", consultation.reason),
        ("Síntomas / Anamnesis", consultation.symptoms),
        ("Examen Físico", consultation.physical_exam),
        ("Diagnóstico", consultation.diagnosis),
        ("Plan Terapéutico y Tratamiento", consultation.treatment),
        ("Prescripción Médica (Medicamentos)", consultation.prescription),
        ("Notas Clínicas Adicionales", consultation.notes),
    ]
    
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
