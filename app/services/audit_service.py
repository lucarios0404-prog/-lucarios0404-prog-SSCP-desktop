import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.audit_log import ClinicalAuditLog

class AuditService:
    @staticmethod
    def log_change(
        db: Session,
        entity_type: str,
        entity_id: int,
        action: str,
        summary: str,
        patient_id: int = None,
        user_id: int = None,
        old_data: dict = None,
        new_data: dict = None
    ) -> ClinicalAuditLog:
        """
        Registra una entrada inmutable de trazabilidad y auditoría médica (F13).
        """
        changes = None
        if old_data or new_data:
            diff = {}
            if old_data and new_data:
                for k in set(list(old_data.keys()) + list(new_data.keys())):
                    val_old = str(old_data.get(k, ""))
                    val_new = str(new_data.get(k, ""))
                    if val_old != val_new:
                        diff[k] = {"before": val_old, "after": val_new}
            elif new_data:
                diff = {"created": new_data}
            changes = json.dumps(diff, ensure_ascii=False)

        audit_entry = ClinicalAuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            patient_id=patient_id,
            user_id=user_id or 1,
            action=action,
            summary=summary,
            changes_json=changes
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        return audit_entry

    @staticmethod
    def get_logs_for_patient(db: Session, patient_id: int, limit: int = 50) -> list:
        return db.query(ClinicalAuditLog).filter(
            ClinicalAuditLog.patient_id == patient_id
        ).order_by(ClinicalAuditLog.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_logs_for_entity(db: Session, entity_type: str, entity_id: int) -> list:
        return db.query(ClinicalAuditLog).filter(
            ClinicalAuditLog.entity_type == entity_type,
            ClinicalAuditLog.entity_id == entity_id
        ).order_by(ClinicalAuditLog.created_at.desc()).all()
