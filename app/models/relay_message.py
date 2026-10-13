from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base

class RelayMessage(Base):
    """
    Mensajes del Buzón Relay para sincronización asíncrona entre Doctor, Secretaría y Tablets.
    Permite depositar deltas cuando uno de los dispositivos está apagado y recuperarlos
    inmediatamente cuando se conecta sin importar la red Wi-Fi o si usa datos móviles.
    """
    __tablename__ = "relay_messages"

    id = Column(Integer, primary_key=True, index=True)
    clinic_id = Column(String(64), nullable=False, index=True)
    device_id = Column(String(64), nullable=False, index=True) # "tablet_secretaria", "pc_doctor", etc.
    message_type = Column(String(32), default="delta", index=True) # delta, appointment, payment, patient
    payload_json = Column(Text, nullable=False)
    
    is_delivered = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def to_dict(self):
        import json
        try:
            payload = json.loads(self.payload_json)
        except Exception:
            payload = {}
        return {
            "id": self.id,
            "clinic_id": self.clinic_id,
            "device_id": self.device_id,
            "message_type": self.message_type,
            "payload": payload,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
