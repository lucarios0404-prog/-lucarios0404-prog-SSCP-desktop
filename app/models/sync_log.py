from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base

class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Tipo: "push", "pull", "offline_export", "offline_import", "ping"
    sync_type = Column(String, nullable=False, index=True)
    # Estado: "success", "failed", "offline"
    status = Column(String, nullable=False, index=True)
    
    records_sent = Column(Integer, default=0)
    records_received = Column(Integer, default=0)
    node_ip = Column(String, nullable=True) # IP del nodo o Tailscale
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
