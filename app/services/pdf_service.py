import io
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
    
    # 1. Membrete de la Clínica
    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    phone = getattr(setting, "phone", "") if setting else ""
    email = getattr(setting, "email", "") if setting else ""
    address = getattr(setting, "address", "") if setting else ""
    
    header_data = [
        [
            Paragraph(f"<b>{clinic_name}</b>", styles["title"]),
            Paragraph(f"<b>{doctor_name}</b><br/>{specialty}<br/>Tel: {phone}<br/>{email}", styles["subtitle"])
        ]
    ]
    header_table = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR, spaceBefore=4, spaceAfter=12))
    
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
    
    # Membrete
    clinic_name = getattr(setting, "clinic_name", "Centro Médico SSCP") if setting else "Centro Médico SSCP"
    doctor_name = getattr(setting, "doctor_name", "Dr. Especialista") if setting else "Dr. Especialista"
    specialty = getattr(setting, "specialty", "Medicina General") if setting else "Medicina General"
    
    header_data = [
        [
            Paragraph(f"<b>{clinic_name}</b><br/><font size=11 color='#0d9488'>INFORME DE CONSULTA CLÍNICA</font>", styles["title"]),
            Paragraph(f"<b>Médico:</b> {doctor_name}<br/>{specialty}", styles["subtitle"])
        ]
    ]
    h_table = Table(header_data, colWidths=[4.2 * inch, 2.8 * inch])
    story.append(h_table)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR, spaceBefore=2, spaceAfter=10))
    
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
