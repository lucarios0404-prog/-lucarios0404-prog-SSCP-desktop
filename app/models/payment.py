from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    
    service_name = Column(String, default="Consulta Médica General")
    amount = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    
    # Estados: "paid" (Cobrado), "pending" (Pendiente), "cancelled" (Anulado)
    status = Column(String, default="paid", index=True)
    
    # Métodos: "cash" (Efectivo), "card" (Tarjeta), "transfer" (Transferencia), "insurance" (Seguro Médico)
    payment_method = Column(String, default="cash")
    receipt_number = Column(String, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    sede_origen = Column(String, default="local")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient", backref="payments")
    appointment = relationship("Appointment", backref="payments")
    created_by = relationship("User", foreign_keys=[created_by_id])
