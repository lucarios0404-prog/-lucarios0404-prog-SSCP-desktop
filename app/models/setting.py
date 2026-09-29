from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
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

    # Rol de Estación y Topología de Red (v1.2.0)
    station_role = Column(String, default="doctor_principal")  # doctor_principal, secretaria
    central_station_url = Column(String, nullable=True)        # URL / IP del nodo central o Tailscale

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

    # Configuración de Impresión Personalizada por Estación / Médico (v1.2.0)
    print_margin_top = Column(Float, default=15.0)       # en milímetros
    print_margin_bottom = Column(Float, default=15.0)    # en milímetros
    print_margin_left = Column(Float, default=20.0)      # en milímetros
    print_margin_right = Column(Float, default=15.0)     # en milímetros
    print_paper_size = Column(String, default="Letter")  # Letter, A4, Legal, HalfLetter
    
    # Modo de Impresión y Calibración de Talonario Preimpreso (Drag & Drop)
    print_mode = Column(String, default="preprinted")    # preprinted (talonario de imprenta), standard (hoja en blanco)
    print_template_config = Column(Text, nullable=True)  # JSON con coordenadas X, Y, W, H, fontSize de cada campo

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
