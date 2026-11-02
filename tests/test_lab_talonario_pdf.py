import json
from datetime import datetime
from app.services.pdf_service import generate_lab_order_talonario_pdf
from app.models.patient import Patient
from app.models.lab_order import LabOrder

def test_lab_order_talonario_pdf_generation_dynamic():
    patient = Patient(
        id=1,
        first_name="María",
        last_name="González",
        document_id="001-9876543-2",
        date_of_birth=datetime(1992, 5, 14)
    )

    # Caso 1: 8 analíticas (menos de 10 -> todas en columna 1)
    tests_8 = ["Hemograma", "Orina", "Glicemia", "Creatinina", "Urea", "Acido Urico", "Colesterol", "Trigliceridos"]
    order_8 = LabOrder(
        id=101,
        patient_id=1,
        patient=patient,
        order_date=datetime.now(),
        tests_requested=json.dumps(tests_8),
        clinical_indication="Chequeo rutina"
    )
    pdf_buf_8 = generate_lab_order_talonario_pdf(order_8)
    assert pdf_buf_8 is not None
    assert pdf_buf_8.getbuffer().nbytes > 1000

    # Caso 2: 11 analíticas (más de 10 -> columna 1 con 10 y columna 2 con 1)
    tests_11 = tests_8 + ["Falcemia", "TORCH IgG - IgM", "VDRL"]
    order_11 = LabOrder(
        id=102,
        patient_id=1,
        patient=patient,
        order_date=datetime.now(),
        tests_requested=json.dumps(tests_11),
        clinical_indication="Control prenatal"
    )
    pdf_buf_11 = generate_lab_order_talonario_pdf(order_11)
    assert pdf_buf_11 is not None
    assert pdf_buf_11.getbuffer().nbytes > 1000
