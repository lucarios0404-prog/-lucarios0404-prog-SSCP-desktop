"""
Servicio Unificado de WhatsApp para SSCP Desktop.
Maneja:
1. Limpieza y formateo de números de teléfono internacionales.
2. Renderizado dinámico de plantillas de texto con variables clínicas.
3. Generación de enlaces de 1-clic 'wa.me'.
4. Despacho directo vía Gateway Autónomo cuando está vinculado.
"""
import re
import urllib.parse
from datetime import datetime, date
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.setting import Setting
from app.models.appointment import Appointment
from app.models.patient import Patient
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

class WhatsAppService:
    @staticmethod
    def clean_phone_number(raw_phone: Optional[str], default_country_code: str = "1") -> str:
        """
        Limpia y estandariza un número telefónico a formato internacional E.164 (sin signos + ni guiones).
        Para República Dominicana (809, 829, 849) o números de 10 dígitos, antepone '1'.
        """
        if not raw_phone:
            return ""
            
        digits = re.sub(r"\D", "", raw_phone)
        if not digits:
            return ""

        # Si ya tiene 11 dígitos y empieza por 1 (ej: 18091234567)
        if len(digits) == 11 and digits.startswith("1"):
            return digits

        # Si tiene 10 dígitos (ej: 8091234567, 8291234567, 8491234567)
        if len(digits) == 10:
            return f"{default_country_code}{digits}"

        # Si empieza con código de país como 58, 57, 52, etc. (más de 10 dígitos)
        if len(digits) >= 11:
            return digits

        return f"{default_country_code}{digits}"

    @staticmethod
    def render_template(template_str: str, context: Dict[str, Any]) -> str:
        """
        Reemplaza variables dinámicas con formato {variable} de forma segura.
        """
        if not template_str:
            return ""

        result = template_str
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value or ""))
        return result

    @classmethod
    def get_appointment_context(cls, db: Session, appointment: Appointment) -> Dict[str, Any]:
        """Extrae el diccionario de variables clínicas para una cita dada."""
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
            "motivo": appointment.reason or "Consulta Médica"
        }

    @classmethod
    def build_wa_link(cls, phone: str, message: str) -> str:
        """Construye un enlace directo wa.me seguro."""
        clean_phone = cls.clean_phone_number(phone)
        encoded_text = urllib.parse.quote(message)
        return f"https://wa.me/{clean_phone}?text={encoded_text}"

    @classmethod
    def get_appointment_reminder(cls, db: Session, appointment: Appointment) -> Dict[str, Any]:
        """
        Genera los datos y enlace de recordatorio para una cita.
        """
        setting = db.query(Setting).first()
        template = (setting.whatsapp_template_reminder if setting and setting.whatsapp_template_reminder 
                    else DEFAULT_REMINDER_TEMPLATE)
        
        ctx = cls.get_appointment_context(db, appointment)
        message = cls.render_template(template, ctx)
        
        raw_phone = appointment.patient.phone if appointment.patient else ""
        clean_phone = cls.clean_phone_number(raw_phone)
        wa_link = cls.build_wa_link(clean_phone, message) if clean_phone else ""

        gateway_status = gateway_manager.get_status()

        return {
            "appointment_id": appointment.id,
            "patient_name": ctx["paciente"],
            "raw_phone": raw_phone,
            "clean_phone": clean_phone,
            "message": message,
            "wa_link": wa_link,
            "already_sent": bool(appointment.whatsapp_reminder_sent),
            "sent_at": appointment.whatsapp_reminder_sent_at.strftime("%d/%m/%Y %H:%M") if appointment.whatsapp_reminder_sent_at else None,
            "gateway_connected": gateway_status["is_connected"]
        }

    @classmethod
    def get_waiting_alert(cls, db: Session, appointment: Appointment) -> Dict[str, Any]:
        """
        Genera la alerta para el doctor de que un paciente está en sala de espera.
        """
        setting = db.query(Setting).first()
        template = (setting.whatsapp_template_waiting if setting and setting.whatsapp_template_waiting 
                    else DEFAULT_WAITING_TEMPLATE)
        
        ctx = cls.get_appointment_context(db, appointment)
        message = cls.render_template(template, ctx)
        
        doctor_phone = setting.whatsapp_doctor_phone if setting and setting.whatsapp_doctor_phone else (setting.phone if setting else "")
        clean_phone = cls.clean_phone_number(doctor_phone)
        wa_link = cls.build_wa_link(clean_phone, message) if clean_phone else ""

        return {
            "doctor_phone": clean_phone,
            "message": message,
            "wa_link": wa_link,
            "patient_name": ctx["paciente"],
            "gateway_connected": gateway_manager.get_status()["is_connected"]
        }

    @classmethod
    def dispatch_message(cls, phone: str, message: str, force_manual: bool = False) -> Dict[str, Any]:
        """
        Envía un mensaje:
        - Si el Gateway está conectado y no se fuerza modo manual, se despacha en automático.
        - En caso contrario, provee el enlace directo wa.me para apertura de 1-clic.
        """
        clean_phone = cls.clean_phone_number(phone)
        wa_link = cls.build_wa_link(clean_phone, message) if clean_phone else ""
        gateway_state = gateway_manager.get_status()

        if gateway_state["is_connected"] and not force_manual:
            gw_result = gateway_manager.send_message(clean_phone, message)
            return {
                "success": gw_result.get("success", False),
                "mode": "gateway",
                "phone": clean_phone,
                "message": message,
                "wa_link": wa_link,
                "detail": "Despachado automáticamente por el Gateway de WhatsApp."
            }
        
        return {
            "success": True,
            "mode": "wa_link",
            "phone": clean_phone,
            "message": message,
            "wa_link": wa_link,
            "detail": "Listo para envío manual en WhatsApp (1-clic)."
        }
