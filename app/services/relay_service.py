import json
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc

from app.models.relay_message import RelayMessage
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.payment import Payment
from app.models.setting import Setting
from app.routers.payments import generate_receipt_number

class RelayService:
    DEFAULT_CLINIC_ID = "dr_carlos_heredia"

    @classmethod
    def get_clinic_id(cls, db: Session) -> str:
        """
        Obtiene el identificador único del consultorio para el buzón.
        Si es otro doctor, toma su canal personalizado o su nombre sanitizado
        (ej: 'dr_manuel_ramirez', 'dra_laura_gomez'), permitiendo que cada
        médico tenga su buzón 100% independiente en la nube.
        """
        try:
            setting = db.query(Setting).first()
            if setting and getattr(setting, "relay_channel_id", None) and setting.relay_channel_id.strip():
                return setting.relay_channel_id.strip()
            if setting and setting.doctor_name and setting.doctor_name.strip() not in ("Dr. Especialista", "Dr. Carlos Heredia"):
                import re
                import unicodedata
                norm = unicodedata.normalize('NFKD', setting.doctor_name.strip()).encode('ASCII', 'ignore').decode('utf-8').lower()
                raw = re.sub(r'[^a-zA-Z0-9_\-]+', '_', norm).strip('_')
                if raw:
                    return f"dr_{raw}" if not raw.startswith("dr") else raw
        except Exception:
            pass
        return cls.DEFAULT_CLINIC_ID


    @staticmethod
    def push_message(
        db: Session,
        clinic_id: str,
        device_id: str,
        payload: Dict[str, Any],
        message_type: str = "delta"
    ) -> RelayMessage:
        """Deposita un paquete en el buzón relay."""
        payload_str = json.dumps(payload, ensure_ascii=False)
        msg = RelayMessage(
            clinic_id=clinic_id.strip(),
            device_id=device_id.strip(),
            message_type=message_type,
            payload_json=payload_str,
            is_delivered=False
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    @staticmethod
    def pull_messages(
        db: Session,
        clinic_id: str,
        since_iso: Optional[str] = None,
        exclude_device_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Recupera los mensajes pendientes del buzón."""
        query = db.query(RelayMessage).filter(RelayMessage.clinic_id == clinic_id.strip())

        if since_iso:
            try:
                since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
                query = query.filter(RelayMessage.created_at > since_dt)
            except Exception:
                pass

        if exclude_device_id:
            query = query.filter(RelayMessage.device_id != exclude_device_id.strip())

        messages = query.order_by(RelayMessage.created_at.asc()).limit(limit).all()
        return [m.to_dict() for m in messages]

    @staticmethod
    def reconcile_incoming_delta(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reconcilia en la base de datos local los datos recibidos de otro dispositivo
        (ej: citas y pacientes anotados por la secretaria a las 7:00 AM).
        """
        patients_data = payload.get("patients", [])
        appts_data = payload.get("appointments", [])
        payments_data = payload.get("payments", [])

        stats = {
            "processed_patients": 0,
            "processed_appointments": 0,
            "processed_payments": 0,
            "patient_map": {}
        }

        # 1. Reconciliar Pacientes
        for p_item in patients_data:
            doc = (p_item.get("document_id") or "").strip() or None
            fn = (p_item.get("first_name") or "").strip()
            ln = (p_item.get("last_name") or "").strip()
            phone = (p_item.get("phone") or "").strip() or None
            uuid = p_item.get("client_uuid") or p_item.get("uuid") or p_item.get("patient_uuid")

            existing = None
            if doc:
                existing = db.query(Patient).filter(Patient.document_id == doc).first()
            if not existing and phone:
                existing = db.query(Patient).filter(Patient.phone == phone).first()
            if not existing and fn and ln:
                existing = db.query(Patient).filter(
                    Patient.first_name.ilike(fn),
                    Patient.last_name.ilike(ln)
                ).first()

            if existing:
                assigned_id = existing.id
                # Actualizar teléfono o seguro si faltaba
                if not existing.phone and phone:
                    existing.phone = phone
                if not existing.insurance_name and p_item.get("insurance_name"):
                    existing.insurance_name = p_item.get("insurance_name")
                db.commit()
            else:
                new_p = Patient(
                    first_name=fn or "Paciente",
                    last_name=ln or "",
                    document_id=doc,
                    phone=phone,
                    insurance_name=p_item.get("insurance_name") or "Privado",
                    insurance_number=p_item.get("insurance_number"),
                    allergies=p_item.get("allergies"),
                    sede_origen="import_consulta_practica", # Conservar coherencia del consultorio
                    is_active=True
                )
                db.add(new_p)
                db.commit()
                db.refresh(new_p)
                assigned_id = new_p.id

            stats["processed_patients"] += 1
            if uuid:
                stats["patient_map"][uuid] = assigned_id

        # 2. Reconciliar Citas
        for a_item in appts_data:
            pid = a_item.get("patient_id")
            p_uuid = a_item.get("patient_client_uuid") or a_item.get("patient_uuid")
            if not pid and p_uuid:
                pid = stats["patient_map"].get(p_uuid)

            if not pid:
                # Si no hay ID, buscar paciente por nombre
                p_name = a_item.get("patient_name") or a_item.get("patient_display_name")
                if p_name:
                    p_match = db.query(Patient).filter(Patient.first_name.ilike(f"%{p_name.strip()}%")).first()
                    if p_match:
                        pid = p_match.id

            if not pid:
                continue

            # Fechas y Horas
            try:
                date_str = str(a_item.get("date") or a_item.get("appointment_date") or "")[:10]
                a_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                a_date = date.today()

            try:
                time_str = str(a_item.get("start_time") or a_item.get("appointment_time") or "")[:5]
                t_parts = time_str.split(":")
                a_time = time(int(t_parts[0]), int(t_parts[1]))
            except Exception:
                a_time = time(8, 0)

            # Idempotencia: evitar duplicar cita existente para el mismo paciente en la misma fecha y hora
            existing_appt = db.query(Appointment).filter(
                Appointment.patient_id == pid,
                Appointment.date == a_date,
                Appointment.start_time == a_time
            ).first()

            if existing_appt:
                if a_item.get("status"):
                    existing_appt.status = a_item.get("status")
                db.commit()
            else:
                new_a = Appointment(
                    patient_id=pid,
                    date=a_date,
                    start_time=a_time,
                    reason=a_item.get("reason") or "Consulta General",
                    status=a_item.get("status") or "Pendiente",
                    price=float(a_item.get("price") or 0.0),
                    queue_number=a_item.get("queue_number")
                )
                db.add(new_a)
                db.commit()

            stats["processed_appointments"] += 1

        # 3. Reconciliar Pagos
        for pay_item in payments_data:
            pid = pay_item.get("patient_id")
            if not pid:
                continue
            amt = float(pay_item.get("amount") or pay_item.get("total") or 0.0)
            receipt = pay_item.get("receipt_number") or generate_receipt_number()

            # Evitar duplicar recibo
            existing_pay = db.query(Payment).filter(Payment.receipt_number == receipt).first()
            if existing_pay:
                if pay_item.get("status"):
                    existing_pay.status = pay_item.get("status")
                db.commit()
            else:
                new_pay = Payment(
                    patient_id=pid,
                    service_name=pay_item.get("service_name") or "Consulta Médica",
                    amount=amt,
                    total=amt,
                    discount=0.0,
                    status=pay_item.get("status") or "paid",
                    receipt_number=receipt,
                    payment_method=pay_item.get("payment_method") or "cash"
                )
                db.add(new_pay)
                db.commit()

            stats["processed_payments"] += 1

        return stats

    @staticmethod
    def purge_old_messages(db: Session, days: int = 14) -> int:
        """Limpia mensajes de más de 14 días para mantener la base liviana."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = db.query(RelayMessage).filter(RelayMessage.created_at < cutoff).delete()
        db.commit()
        return deleted

    CLOUD_RELAY_URL = "https://sscp.laxarusdevs.com"

    @classmethod
    def pull_from_cloud(
        cls,
        db: Session,
        clinic_id: Optional[str] = None,
        cloud_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Consulta el buzón Cloud Relay en Internet público y reconcilia
        cualquier cita o paciente depositado por la tablet cuando la PC
        estaba apagada o en una red diferente (sin Wi-Fi / sin VPN).
        """
        import requests
        cid = clinic_id or cls.get_clinic_id(db)
        base = (cloud_url or cls.CLOUD_RELAY_URL).rstrip("/")
        endpoint = f"{base}/api/relay/{cid}/pull"

        stats = {
            "success": False,
            "pulled_messages": 0,
            "processed_patients": 0,
            "processed_appointments": 0,
            "processed_payments": 0,
            "error": None
        }

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SSCP-Desktop/1.3.0",
                "Accept": "application/json"
            }
            res = requests.get(endpoint, headers=headers, timeout=6)
            if res.status_code != 200:
                stats["error"] = f"HTTP {res.status_code}"
                return stats


            data = res.json()
            messages = data.get("messages", [])
            stats["pulled_messages"] = len(messages)

            for m in messages:
                msg_id = m.get("id")
                # Deduplicación: verificar si este mensaje de la nube ya fue procesado
                if msg_id:
                    existing = db.query(RelayMessage).filter(
                        RelayMessage.clinic_id == cid,
                        RelayMessage.device_id == f"cloud_{msg_id}"
                    ).first()
                    if existing:
                        continue

                payload = m.get("payload", {})
                reconcile_res = cls.reconcile_incoming_delta(db, payload)
                stats["processed_patients"] += reconcile_res.get("processed_patients", 0)
                stats["processed_appointments"] += reconcile_res.get("processed_appointments", 0)
                stats["processed_payments"] += reconcile_res.get("processed_payments", 0)

                # Registrar mensaje procesado para no duplicarlo en futuros pulls
                if msg_id:
                    marker = RelayMessage(
                        clinic_id=cid,
                        device_id=f"cloud_{msg_id}",
                        message_type="cloud_delta",
                        payload_json=json.dumps({"reconciled": True, "at": datetime.utcnow().isoformat()}),
                        is_delivered=True
                    )
                    db.add(marker)
                    db.commit()

            stats["success"] = True
            return stats
        except Exception as e:
            stats["error"] = str(e)
            return stats

