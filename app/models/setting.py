from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    clinic_name = Column(String, default="Centro Médico SSCP")
    doctor_name = Column(String, default="Dr. Especialista")
    specialty = Column(String, default="Medicina General")
    phone = Column(String, default="809-555-0199")
    email = Column(String, default="contacto@sscp.local")
    address = Column(Text, default="Av. Principal #100, Santo Domingo")
    currency = Column(String, default="RD$")
    sede_name = Column(String, default="Sede Central")
    tailscale_ip = Column(String, nullable=True)
    sync_interval_minutes = Column(Integer, default=5)
    doctor_logo_path = Column(String, nullable=True)  # Ruta local del logo/membrete del doctor

    # Integración WhatsApp (1-Clic + Gateway Autónomo)
    whatsapp_doctor_phone = Column(String, nullable=True)  # Teléfono del médico para avisos de sala de espera
    whatsapp_auto_send = Column(Boolean, default=False)    # Habilitar envíos automáticos en background
    whatsapp_auto_hour = Column(String, default="08:30")   # Hora matutina de envío automático
    whatsapp_template_reminder = Column(
        Text, 
        default="Estimado(a) {paciente}, le recordamos su cita médica con el {doctor} el día {fecha} a las {hora} en {clinica}. Por favor responda a este mensaje para confirmar su asistencia."
    )
    whatsapp_template_waiting = Column(
        Text, 
        default="Dr. {doctor}, el paciente {paciente} ya se encuentra en sala de espera en recepción para su consulta."
    )
    whatsapp_template_followup = Column(
        Text, 
        default="Estimado(a) {paciente}, el {doctor} de {clinica} le consulta cómo ha evolucionado con el tratamiento indicado y le recuerda su cita de control."
    )
    whatsapp_gateway_status = Column(String, default="disconnected")  # disconnected, connecting, connected
    whatsapp_connected_phone = Column(String, nullable=True)          # Número vinculado al gateway

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
