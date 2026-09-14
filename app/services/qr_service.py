import io
import base64
import qrcode
from qrcode.constants import ERROR_CORRECT_M

def generate_patient_qr_base64(patient) -> str:
    """
    Genera un código QR con los datos esenciales del expediente del paciente
    y lo retorna como una cadena Data URI en Base64 para incrustación directa en HTML.
    """
    first_name = getattr(patient, "first_name", "")
    last_name = getattr(patient, "last_name", "")
    doc_id = getattr(patient, "document_id", "N/D")
    blood = getattr(patient, "blood_type", "N/D")
    allergies = getattr(patient, "allergies", "Ninguna") or "Ninguna"
    em_contact = getattr(patient, "emergency_contact_name", "N/D") or "N/D"
    em_phone = getattr(patient, "emergency_contact_phone", "N/D") or "N/D"
    patient_id = getattr(patient, "id", "")

    qr_text = (
        f"SSCP EXPEDIENTE CLÍNICO #{patient_id}\n"
        f"Paciente: {first_name} {last_name}\n"
        f"DNI/Cédula: {doc_id}\n"
        f"Grupo Sanguíneo: {blood}\n"
        f"Alergias: {allergies}\n"
        f"Contacto Emergencia: {em_contact} ({em_phone})"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff") # Slate 900 on white
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64_encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_encoded}"
