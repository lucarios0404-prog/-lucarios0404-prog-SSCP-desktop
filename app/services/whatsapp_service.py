"""
Unified WhatsApp Service for SSCP Desktop (1-Clic Real Mode).
Handles:
1. Idempotent E.164 phone normalization & validation.
2. Dynamic clinical template rendering.
3. Safe wa.me 1-Clic link construction and honest dispatch payload generation.
"""
import re
import urllib.parse
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.setting import Setting
from app.models.appointment import Appointment
from app.services.whatsapp_gateway import gateway_manager

DEFAULT_REMINDER_TEMPLATE = (
    "Estimado(a) {paciente}, le recordamos su cita médica con el {doctor} el día {fecha} a las {hora} "
    "en {clinica}. Por favor responda a este mensaje para confirmar su asistencia. ¡Le esperamos!"
)

DEFAULT_WAITING_TEMPLATE = (
    "Dr. {doctor}, el paciente {paciente} ya se encuentra en sala de espera en recepción para su consulta."
)

DEFAULT_FOLLOWUP_TEMPLATE = (
    "Estimado(a) {paciente}, el {doctor} de {clinica} le consulta cómo ha evolucionado con el tratamiento "
    "indicado y le recuerda agendar su cita de control si es necesario."
)

DR_AREA_CODES = ("809", "829", "849")


class WhatsAppService:
    @staticmethod
    def clean_phone_number(raw_phone: Optional[str], default_country_code: str = "1") -> str:
        """
        Idempotently normalizes a phone number to E.164 digits (without '+' or separators).
        - Strips leading '00' international exit prefix when length > 10.
        - Prepends '1' only to 10-digit Dominican Republic numbers (809, 829, 849).
        - Preserves valid 10..15-digit international numbers.
        - Rejects (<10 or >15 digits) by returning "".
        """
        if not raw_phone:
            return ""

        digits = re.sub(r"\D", "", str(raw_phone))
        if not digits:
            return ""

        if digits.startswith("00") and len(digits) > 10:
            digits = digits[2:]

        if len(digits) == 10 and digits[:3] in DR_AREA_CODES:
            return f"{default_country_code}{digits}"

        if 10 <= len(digits) <= 15:
            return digits

        return ""

    @staticmethod
    def is_valid_phone(raw_phone: Optional[str]) -> bool:
        """Returns True when the phone normalizes cleanly to a usable E.164 target."""
        return bool(WhatsAppService.clean_phone_number(raw_phone))

    @staticmethod
    def render_template(template_str: str, context: Dict[str, Any]) -> str:
        """Safely substitutes {variable} placeholders without format-string injection."""
        if not template_str:
            return ""

        result = template_str
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value or ""))
        return result

    @classmethod
    def get_appointment_context(
        cls,
        db: Session,
        appointment: Appointment,
        setting: Optional[Setting] = None,
    ) -> Dict[str, Any]:
        """Extracts clinical template variables for a given appointment."""
        if setting is None:
            setting = db.query(Setting).first()
        patient = appointment.patient

        clinic_name = setting.clinic_name if setting and setting.clinic_name else "Centro Médico SSCP"
        doctor_name = setting.doctor_name if setting and setting.doctor_name else "Dr. Especialista"
        address = setting.address if setting and setting.address else ""
        phone = setting.phone if setting and setting.phone else ""

        patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Paciente"
        date_formatted = appointment.date.strftime("%d/%m/%Y") if appointment.date else ""
        time_formatted = appointment.start_time.strftime("%I:%M %p") if appointment.start_time else ""

        return {
            "paciente": patient_name,
            "doctor": doctor_name,
            "fecha": date_formatted,
            "hora": time_formatted,
            "clinica": clinic_name,
            "direccion": address,
            "telefono_clinica": phone,
            "motivo": appointment.reason or "Consulta Médica",
        }

    @classmethod
    def build_wa_link(cls, phone: Optional[str], message: str = "") -> str:
        """Builds a strict HTTPS wa.me link with full percent-encoding (including '/')."""
        clean_phone = cls.clean_phone_number(phone)
        if not clean_phone:
            return ""
        encoded_text = urllib.parse.quote(message or "", safe="")
        return f"https://wa.me/{clean_phone}?text={encoded_text}"

    @classmethod
    def get_appointment_reminder(
        cls,
        db: Session,
        appointment: Appointment,
        setting: Optional[Setting] = None,
        gateway_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generates reminder text, validated phone fields, and 1-Clic link for an appointment."""
        if setting is None:
            setting = db.query(Setting).first()
        template = (
            setting.whatsapp_template_reminder
            if setting and setting.whatsapp_template_reminder
            else DEFAULT_REMINDER_TEMPLATE
        )

        ctx = cls.get_appointment_context(db, appointment, setting=setting)
        message = cls.render_template(template, ctx)

        raw_phone = appointment.patient.phone if appointment.patient and appointment.patient.phone else ""
        clean_phone = cls.clean_phone_number(raw_phone)
        valid_phone = bool(clean_phone)
        wa_link = cls.build_wa_link(clean_phone, message) if valid_phone else ""

        if gateway_status is None:
            gateway_status = gateway_manager.get_status()

        return {
            "appointment_id": appointment.id,
            "patient_name": ctx["paciente"],
            "raw_phone": raw_phone,
            "clean_phone": clean_phone,
            "valid_phone": valid_phone,
            "message": message,
            "wa_link": wa_link,
            "already_sent": bool(appointment.whatsapp_reminder_sent),
            "sent_at": (
                appointment.whatsapp_reminder_sent_at.strftime("%d/%m/%Y %H:%M")
                if appointment.whatsapp_reminder_sent_at
                else None
            ),
            "gateway_connected": bool(gateway_status.get("is_connected", False)),
            "mode": "wa_link",
        }

    @classmethod
    def get_waiting_alert(cls, db: Session, appointment: Appointment) -> Dict[str, Any]:
        """Generates the WhatsApp alert link to notify the doctor that the patient arrived."""
        setting = db.query(Setting).first()
        template = (
            setting.whatsapp_template_waiting
            if setting and setting.whatsapp_template_waiting
            else DEFAULT_WAITING_TEMPLATE
        )

        ctx = cls.get_appointment_context(db, appointment)
        message = cls.render_template(template, ctx)

        doctor_phone = (
            setting.whatsapp_doctor_phone
            if setting and setting.whatsapp_doctor_phone
            else (setting.phone if setting else "")
        )
        clean_phone = cls.clean_phone_number(doctor_phone)
        valid_phone = bool(clean_phone)
        wa_link = cls.build_wa_link(clean_phone, message) if valid_phone else ""

        return {
            "doctor_phone": clean_phone,
            "clean_phone": clean_phone,
            "valid_phone": valid_phone,
            "message": message,
            "wa_link": wa_link,
            "patient_name": ctx["paciente"],
            "gateway_connected": False,
            "mode": "wa_link",
        }

    @classmethod
    def get_followup_message(cls, db: Session, appointment: Appointment) -> Dict[str, Any]:
        """Generates a post-consultation follow-up 1-Clic link for a patient."""
        setting = db.query(Setting).first()
        template = (
            setting.whatsapp_template_followup
            if setting and setting.whatsapp_template_followup
            else DEFAULT_FOLLOWUP_TEMPLATE
        )

        ctx = cls.get_appointment_context(db, appointment)
        message = cls.render_template(template, ctx)

        raw_phone = appointment.patient.phone if appointment.patient and appointment.patient.phone else ""
        clean_phone = cls.clean_phone_number(raw_phone)
        valid_phone = bool(clean_phone)
        wa_link = cls.build_wa_link(clean_phone, message) if valid_phone else ""

        return {
            "appointment_id": appointment.id,
            "patient_name": ctx["paciente"],
            "raw_phone": raw_phone,
            "clean_phone": clean_phone,
            "valid_phone": valid_phone,
            "message": message,
            "wa_link": wa_link,
            "mode": "wa_link",
        }

    @classmethod
    def dispatch_message(cls, phone: str, message: str, force_manual: bool = True) -> Dict[str, Any]:
        """
        Generates an honest 1-Clic WhatsApp link without faking background delivery.
        """
        clean_phone = cls.clean_phone_number(phone)
        if not clean_phone:
            return {
                "success": False,
                "mode": "wa_link",
                "phone": "",
                "clean_phone": "",
                "wa_link": "",
                "error": "Número telefónico inválido o incompleto (mínimo 10 dígitos, ej: 809-555-0199).",
            }

        wa_link = cls.build_wa_link(clean_phone, message)
        return {
            "success": True,
            "mode": "wa_link",
            "phone": clean_phone,
            "clean_phone": clean_phone,
            "message": message,
            "wa_link": wa_link,
            "detail": "Enlace WhatsApp 1-Clic listo para abrir.",
        }
