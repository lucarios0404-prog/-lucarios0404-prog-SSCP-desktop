import re
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from app.models.patient import Patient

class PatientService:
    @staticmethod
    def normalize_doc(doc: str) -> str:
        if not doc:
            return ""
        return re.sub(r"[^0-9a-zA-Z]", "", doc).upper()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        if not phone:
            return ""
        digits = re.sub(r"[^0-9]", "", phone)
        # Tomar los últimos 8 dígitos si hay más
        return digits[-8:] if len(digits) >= 8 else digits

    @staticmethod
    def find_potential_duplicates(
        db: Session,
        first_name: str,
        last_name: str,
        document_id: str = None,
        phone: str = None,
        exclude_id: int = None,
        threshold: float = 0.75
    ) -> list:
        """
        Detector Inteligente de Pacientes Duplicados (F9) mediante comparación difusa y verificación cruzada.
        """
        target_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".lower()
        clean_target_doc = PatientService.normalize_doc(document_id)
        clean_target_phone = PatientService.normalize_phone(phone)

        query = db.query(Patient)
        if exclude_id:
            query = query.filter(Patient.id != exclude_id)
        
        candidates = query.all()
        matches = []

        for p in candidates:
            score = 0
            reasons = []

            # 1. Chequeo por Cédula / Documento
            clean_cand_doc = PatientService.normalize_doc(p.document_id)
            if clean_target_doc and clean_cand_doc and clean_target_doc == clean_cand_doc:
                score = 100
                reasons.append("Documento de identidad idéntico")

            # 2. Chequeo por Teléfono
            clean_cand_phone = PatientService.normalize_phone(p.phone)
            if clean_target_phone and clean_cand_phone and clean_target_phone == clean_cand_phone:
                phone_score = 90
                if phone_score > score:
                    score = phone_score
                reasons.append("Mismo número telefónico")

            # 3. Chequeo por Similitud de Nombres (Levenshtein / SequenceMatcher)
            cand_name = f"{(p.first_name or '').strip()} {(p.last_name or '').strip()}".lower()
            if target_name and cand_name:
                ratio = SequenceMatcher(None, target_name, cand_name).ratio()
                if ratio >= threshold:
                    name_score = int(ratio * 100)
                    if name_score > score:
                        score = name_score
                    reasons.append(f"Similitud de nombre ({name_score}%)")

            if score >= int(threshold * 100):
                matches.append({
                    "id": p.id,
                    "name": f"{p.first_name} {p.last_name}",
                    "document_id": p.document_id or "Sin documento",
                    "phone": p.phone or "Sin teléfono",
                    "score": score,
                    "reasons": reasons,
                    "reason_text": ", ".join(reasons)
                })

        # Ordenar de mayor a menor probabilidad de duplicado
        matches.sort(key=lambda m: m["score"], reverse=True)
        return matches
