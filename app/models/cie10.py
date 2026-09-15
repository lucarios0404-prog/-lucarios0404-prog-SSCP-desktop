from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base

class Cie10Code(Base):
    __tablename__ = "cie10_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False, index=True)
    description = Column(String(500), nullable=False, index=True)
    chapter = Column(String(150), nullable=True, index=True)
    is_custom = Column(Boolean, default=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "description": self.description,
            "chapter": self.chapter or "",
            "is_custom": bool(self.is_custom)
        }
