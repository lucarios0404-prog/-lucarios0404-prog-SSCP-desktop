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
from app.models.user import User
from app.routers.payments import generate_receipt_number

class RelayService:
    DEFAULT_CLINIC_ID = "dr_cristian_garcia"

    @classmethod
    def get_clinic_id(cls, db: Session) -> str:
        """
        Obtiene el identificador único del consultorio para el buzón.
        Si hay un canal configurado y no es el antiguo valor de prueba, lo usa.
        Si no, deriva el canal automáticamente a partir del nombre del doctor o clínica.
        """
        try:
            setting = db.query(Setting).first()
            if setting and getattr(setting, "relay_channel_id", None) and setting.relay_channel_id.strip():
                ch = setting.relay_channel_id.strip().lower()
                if ch != "dr_carlos_heredia":
                    return ch
            if setting and setting.doctor_name and setting.doctor_name.strip() and setting.doctor_name.strip() != "Dr. Carlos Heredia":
                import re
                import unicodedata
                norm = unicodedata.normalize('NFKD', setting.doctor_name.strip()).encode('ASCII', 'ignore').decode('utf-8').lower()
                raw = re.sub(r'[^a-zA-Z0-9_\-]+', '_', norm).strip('_')
                if raw:
                    prefix = "dra_" if "dra" in norm else "dr_"
                    return raw if (raw.startswith("dr_") or raw.startswith("dra_")) else f"{prefix}{raw}"
            if setting and setting.clinic_name and setting.clinic_name.strip():
                import re
                import unicodedata
                norm = unicodedata.normalize('NFKD', setting.clinic_name.strip()).encode('ASCII', 'ignore').decode('utf-8').lower()
                raw = re.sub(r'[^a-zA-Z0-9_\-]+', '_', norm).strip('_')
                if raw:
                    return f"clinica_{raw}"
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

        # 0. Reconciliar Cierre de Jornada (close_day) si vino desde Móvil o Tablet
        close_day_info = payload.get("close_day")
        if close_day_info:
            target_date_str = str(close_day_info.get("date") or date.today().isoformat())[:10]
            try:
                c_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except Exception:
                c_date = date.today()
            pending_candidates = db.query(Appointment).filter(
                Appointment.date <= c_date,
                Appointment.status.in_(["En Espera", "Pendiente", "Confirmada", "En Consulta"])
            ).all()
            for cand in pending_candidates:
                cand.status = "Completada"
            db.commit()

        # 0.1 Reconciliar Actualización Unitaria de Estado (status_update)
        target_aid = payload.get("appointment_id") or (payload.get("status_update", {}).get("appointment_id") if isinstance(payload.get("status_update"), dict) else None)
        new_status = payload.get("status") or (payload.get("status_update", {}).get("status") if isinstance(payload.get("status_update"), dict) else None)
        if target_aid and new_status:
            appt = db.query(Appointment).filter(Appointment.id == target_aid).first()
            if appt:
                appt.status = new_status
                db.commit()

        # 0.2 Reconciliar Cierre de Jornada (close_day)
        if "close_day" in payload:
            close_info = payload.get("close_day", {})
            c_date_str = close_info.get("date") or date.today().strftime("%Y-%m-%d")
            try:
                c_date = datetime.strptime(c_date_str, "%Y-%m-%d").date()
            except Exception:
                c_date = date.today()
            q_close = db.query(Appointment).filter(
                Appointment.date <= c_date,
                Appointment.status.in_(["En Espera", "Pendiente", "Confirmada", "En Consulta"])
            )
            for a_close in q_close.all():
                a_close.status = "Completada"
            db.commit()

        # Resolver médico responsable asignado para toda la reconciliación
        setting = db.query(Setting).first()
        station_doc = None
        if setting and setting.doctor_name:
            station_doc = db.query(User).filter(User.name.ilike(f"%{setting.doctor_name}%"), User.role == "doctor").first()
        if not station_doc:
            station_doc = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
        target_doc_id = station_doc.id if station_doc else 2

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
                    doctor_id=target_doc_id,
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
            p_name = (a_item.get("patient_name") or a_item.get("patient_display_name") or "").strip()
            p_phone = (a_item.get("patient_phone") or "").strip()
            p_uuid = a_item.get("patient_client_uuid") or a_item.get("patient_uuid")

            pid = None
            if p_uuid and p_uuid in stats["patient_map"]:
                pid = stats["patient_map"][p_uuid]

            candidate_pid = a_item.get("patient_id")
            if not pid and candidate_pid:
                cand_p = db.query(Patient).filter(Patient.id == candidate_pid).first()
                if cand_p:
                    # Si la cita trae un nombre real y el paciente local tiene un nombre distinto,
                    # se trata de una colisión con un ID local de la tablet
                    if p_name and p_name.lower() not in ["", "paciente"]:
                        full_name = f"{cand_p.first_name} {cand_p.last_name}".strip().lower()
                        first_word = p_name.split()[0].lower()
                        if first_word in full_name:
                            pid = cand_p.id
                        else:
                            pid = None  # Colisión de ID -> resolver por nombre o crear paciente
                    else:
                        pid = cand_p.id

            if not pid:
                p_match = None
                if p_phone and len(p_phone) >= 7:
                    clean_phone = "".join(filter(str.isdigit, p_phone))[-7:]
                    cand_match = db.query(Patient).filter(Patient.phone.like(f"%{clean_phone}%")).first()
                    if cand_match:
                        # Si hay un nombre específico en la cita, verificar que coincida con el paciente del teléfono
                        if p_name and p_name.lower() not in ["", "paciente"]:
                            cand_full = f"{cand_match.first_name} {cand_match.last_name}".strip().lower()
                            first_p = p_name.split()[0].lower()
                            if first_p in cand_full:
                                p_match = cand_match
                        else:
                            p_match = cand_match

                if not p_match and p_name and p_name.lower() != "paciente":
                    name_parts = p_name.split()
                    if len(name_parts) >= 2:
                        p_match = db.query(Patient).filter(
                            Patient.first_name.ilike(f"%{name_parts[0]}%"),
                            Patient.last_name.ilike(f"%{name_parts[1]}%")
                        ).first()
                    if not p_match:
                        p_match = db.query(Patient).filter(
                            Patient.first_name.ilike(f"%{p_name}%")
                        ).first()

                if p_match:
                    pid = p_match.id
                elif p_name and p_name.lower() != "paciente":
                    parts = p_name.split(maxsplit=1)
                    f_name = parts[0]
                    l_name = parts[1] if len(parts) > 1 else ""
                    new_p = Patient(
                        doctor_id=target_doc_id,
                        first_name=f_name,
                        last_name=l_name,
                        phone=p_phone or None,
                        document_id=None,
                        insurance_name=a_item.get("insurance_name") or "Privado",
                        insurance_number=a_item.get("insurance_number"),
                        sede_origen="tablet_sync",
                        is_active=True
                    )
                    db.add(new_p)
                    db.commit()
                    db.refresh(new_p)
                    pid = new_p.id

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

            # Idempotencia: evitar duplicar cita existente en la misma fecha y hora
            existing_appt = db.query(Appointment).filter(
                Appointment.patient_id == pid,
                Appointment.date == a_date,
                Appointment.start_time == a_time
            ).first()

            if not existing_appt:
                # Si ya existía una cita en esa fecha y hora asignada erróneamente por colisión de ID, corregirla
                existing_appt = db.query(Appointment).filter(
                    Appointment.date == a_date,
                    Appointment.start_time == a_time
                ).first()
                if existing_appt:
                    existing_appt.patient_id = pid
                    db.commit()

            if existing_appt:
                if a_item.get("status"):
                    existing_appt.status = a_item.get("status")
                if a_item.get("queue_number"):
                    existing_appt.queue_number = int(a_item.get("queue_number"))
                if a_item.get("reason"):
                    existing_appt.reason = a_item.get("reason")
                if a_item.get("price") is not None:
                    existing_appt.price = float(a_item.get("price") or 0.0)
                db.commit()
            else:
                q_num = a_item.get("queue_number")
                if q_num:
                    try:
                        q_num = int(q_num)
                    except Exception:
                        q_num = None
                # Si el turno ya está ocupado en la base de datos para esa fecha, asignar el siguiente número secuencial
                if not q_num or db.query(Appointment).filter(Appointment.date == a_date, Appointment.queue_number == q_num).first():
                    from app.routers.appointments import assign_next_queue_number
                    q_num = assign_next_queue_number(db, a_date)

                new_a = Appointment(
                    patient_id=pid,
                    doctor_id=target_doc_id,
                    date=a_date,
                    start_time=a_time,
                    reason=a_item.get("reason") or "Consulta General",
                    status=a_item.get("status") or "En Espera",
                    price=float(a_item.get("price") or 0.0),
                    queue_number=q_num,
                    notes=a_item.get("notes") or "",
                    service_id=a_item.get("service_id")
                )
                db.add(new_a)
                db.commit()

            stats["processed_appointments"] += 1

        # 3. Reconciliar Pagos
        for pay_item in payments_data:
            pid = pay_item.get("patient_id")
            appt_id = pay_item.get("appointment_id")
            if not pid and appt_id:
                appt_obj = db.query(Appointment).filter(Appointment.id == appt_id).first()
                if appt_obj:
                    pid = appt_obj.patient_id

            if not pid or not db.query(Patient).filter(Patient.id == pid).first():
                p_match = db.query(Patient).first()
                if p_match:
                    pid = p_match.id
                else:
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
                    appointment_id=appt_id,
                    service_name=pay_item.get("service_name") or "Consulta Médica",
                    amount=amt,
                    total=amt,
                    discount=0.0,
                    status=pay_item.get("status") or "paid",
                    receipt_number=receipt,
                    payment_method=pay_item.get("payment_method") or "cash",
                    insurance_name=pay_item.get("insurance_name") or "Privado",
                    service_id=pay_item.get("service_id"),
                    notes=pay_item.get("notes") or ""
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
            "new_messages": 0,
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
            res = requests.get(endpoint, headers=headers, timeout=10.0)
            if res.status_code != 200:
                stats["error"] = f"HTTP {res.status_code}"
                return stats

            data = res.json()
            messages = data.get("messages", [])
            stats["pulled_messages"] = len(messages)

            for m in messages:
                msg_id = m.get("id")
                m_type = m.get("message_type")
                if m_type in ["station_profile", "station_snapshot"]:
                    continue

                # Deduplicación: verificar si este mensaje de la nube ya fue procesado
                if msg_id:
                    existing = db.query(RelayMessage).filter(
                        RelayMessage.clinic_id == cid,
                        RelayMessage.device_id == f"cloud_{msg_id}"
                    ).first()
                    if existing:
                        continue

                stats["new_messages"] += 1

                payload = m.get("payload", {})
                if not payload:
                    continue

                if m_type == "status_update":
                    appt_id = payload.get("appointment_id")
                    st = payload.get("status")
                    if appt_id and str(appt_id).lower() != "undefined" and st:
                        appt = db.query(Appointment).filter(Appointment.id == int(appt_id)).first() if str(appt_id).isdigit() else None
                        if appt:
                            appt.status = st
                            db.commit()
                else:
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

    @classmethod
    def sync_station_profile_to_cloud(
        cls,
        db: Session,
        clinic_id: Optional[str] = None,
        cloud_url: Optional[str] = None
    ) -> bool:
        """Notifica al buzón Cloud Relay los datos del consultorio (doctor, especialidad, clínica)."""
        import requests
        try:
            import requests
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                detected_ip = s.getsockname()[0]
            except Exception:
                detected_ip = "127.0.0.1"
            finally:
                s.close()

            # Detectar IP Tailscale (rango 100.x.x.x) si está activa
            tailscale_ip = None
            try:
                for info in socket.getaddrinfo(socket.gethostname(), None):
                    ip = info[4][0]
                    if ip.startswith("100.") and not ip.endswith(".0") and not ip.endswith(".255"):
                        tailscale_ip = ip
                        break
            except Exception:
                pass

            cid = clinic_id or cls.get_clinic_id(db)
            setting = db.query(Setting).first()
            if not setting:
                return False
            base = (cloud_url or cls.CLOUD_RELAY_URL).rstrip("/")
            endpoint = f"{base}/api/relay/{cid}/push"
            profile = {
                "doctor_name": setting.doctor_name or "Médico Especialista",
                "specialty": setting.specialty or "Consulta General",
                "clinic_name": setting.clinic_name or "Centro Médico SSCP",
                "sede_name": setting.sede_name or "Sede Central",
                "pairing_code": cid.upper().replace("_", "-"),
                "local_ip": detected_ip,
                "local_url": f"http://{detected_ip}:8080",
                "tailscale_ip": tailscale_ip,
                "tailscale_url": f"http://{tailscale_ip}:8080" if tailscale_ip else None,
                "updated_at": datetime.utcnow().isoformat()
            }
            payload = {
                "device_id": "pc_doctor_desktop",
                "message_type": "station_profile",
                "data": profile
            }
            res = requests.post(endpoint, json=payload, timeout=2.5)
            return res.status_code == 200
        except Exception:
            return False

    @classmethod
    def push_snapshot_to_cloud(
        cls,
        db: Session,
        clinic_id: Optional[str] = None,
        cloud_url: Optional[str] = None
    ) -> bool:
        """
        Envía un snapshot de las citas y pacientes de hoy al buzón Cloud Relay
        para que la tablet o teléfono en 4G/red externa tenga la agenda idéntica a la PC.
        """
        import requests
        try:
            cid = clinic_id or cls.get_clinic_id(db)
            base = (cloud_url or cls.CLOUD_RELAY_URL).rstrip("/")
            endpoint = f"{base}/api/relay/{cid}/push"

            # Resolver médico responsable de esta estación para aislar estrictamente pacientes y citas
            setting = db.query(Setting).first()
            station_doc = None
            if setting and setting.doctor_name:
                clean_doc_name = (setting.doctor_name or "").replace("Dr. ", "").replace("Dra. ", "").replace("Dr ", "").replace("Dra ", "").strip()
                if clean_doc_name:
                    station_doc = db.query(User).filter(User.name.ilike(f"%{clean_doc_name}%"), User.role == "doctor").first()
            if not station_doc:
                station_doc = db.query(User).filter(User.role == "doctor", User.is_active == True).first()
            target_doc_id = station_doc.id if station_doc else None

            from sqlalchemy import or_

            target_date = date.today()
            appts_q = db.query(Appointment).filter(Appointment.date == target_date)
            if target_doc_id:
                appts_q = appts_q.filter(or_(Appointment.doctor_id == target_doc_id, Appointment.doctor_id.is_(None)))
            appts = appts_q.order_by(Appointment.start_time.asc()).all()

            # Respaldo de seguridad: si no se encontraron citas con el filtro del doctor,
            # pero existen citas hoy en la base de datos local, no enviar lista vacía.
            if not appts:
                total_today = db.query(Appointment).filter(Appointment.date == target_date).count()
                if total_today > 0:
                    appts = db.query(Appointment).filter(Appointment.date == target_date).order_by(Appointment.start_time.asc()).all()

            stats = {
                "total": len(appts),
                "waiting": sum(1 for a in appts if a.status == "En Espera"),
                "in_consultation": sum(1 for a in appts if a.status == "En Consulta"),
                "completed": sum(1 for a in appts if a.status in ["Atendida", "Completada", "Listo"]),
                "pending": sum(1 for a in appts if a.status in ["Pendiente", "Confirmada"]),
            }

            appts_data = []
            for a in appts:
                p = a.patient
                p_name = f"{p.first_name} {p.last_name}".strip() if p else "Paciente"
                is_paid = bool(a.payments and any(py.status == "paid" for py in a.payments))
                appts_data.append({
                    "id": a.id,
                    "patient_id": a.patient_id,
                    "patient_name": p_name,
                    "patient_phone": p.phone if p else "",
                    "reason": a.reason or "Consulta Médica",
                    "date": a.date.strftime("%Y-%m-%d"),
                    "start_time": a.start_time.strftime("%H:%M") if a.start_time else "09:00",
                    "end_time": a.end_time.strftime("%H:%M") if a.end_time else "",
                    "status": a.status,
                    "queue_number": a.queue_number or 1,
                    "service_id": a.service_id or 1,
                    "service_name": a.service.name if a.service else "Consulta Médica",
                    "service_color": a.service.color if a.service else "#3b82f6",
                    "price": float(a.price or (a.service.price if a.service else 0)),
                    "insurance_name": p.insurance_name if p and p.insurance_name else "Privado / Particular",
                    "insurance_number": p.insurance_number if p and p.insurance_number else "",
                    "is_paid": is_paid,
                    "payment_status": "paid" if is_paid else "pending",
                    "notes": a.notes or "",
                })

            appt_patient_ids = [a.patient_id for a in appts if a.patient_id]
            patients_q = db.query(Patient).filter(or_(Patient.id.in_(appt_patient_ids), Patient.is_active != False, Patient.is_active.is_(None)))
            if target_doc_id:
                patients_q = patients_q.filter(or_(Patient.doctor_id == target_doc_id, Patient.doctor_id.is_(None)))
            patients = patients_q.order_by(Patient.id.desc()).limit(10000).all()
            if not patients:
                patients = db.query(Patient).order_by(Patient.id.desc()).limit(10000).all()
            patients_data = [
                {
                    "id": p.id,
                    "first_name": p.first_name,
                    "last_name": p.last_name,
                    "name": f"{p.first_name} {p.last_name}".strip(),
                    "document_id": p.document_id or "",
                    "phone": p.phone or "",
                    "insurance_name": p.insurance_name or "Privado / Particular",
                    "insurance_number": p.insurance_number or "",
                    "allergies": getattr(p, "allergies", "") or "",
                    "notes": getattr(p, "notes", "") or getattr(p, "address", "") or "",
                    "display": f"{p.first_name} {p.last_name} ({p.document_id or 'S/D'}) - Tel: {p.phone or 'S/T'}"
                }
                for p in patients
            ]

            # Incluir catálogo de servicios médicos para selección en la app móvil
            from app.models.service import Service
            from app.models.consultation import Consultation
            from app.models.payment import Payment

            services = db.query(Service).filter(Service.is_active == True).all()
            services_data = [
                {
                    "id": s.id,
                    "name": s.name,
                    "price": float(s.price or 0),
                    "category": getattr(s, "category", "Consulta") or "Consulta",
                    "color": getattr(s, "color", "#3b82f6") or "#3b82f6",
                    "is_active": s.is_active
                }
                for s in services
            ]

            # Consultas recientes para reportes e historial en móvil/tablet
            consultations = db.query(Consultation).order_by(Consultation.created_at.desc()).limit(300).all()
            consultations_data = [
                {
                    "id": c.id,
                    "patient_id": c.patient_id,
                    "patient_name": f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Paciente",
                    "doctor_name": c.doctor.name if c.doctor else (setting.doctor_name if setting and setting.doctor_name else "Dr. Cristian García"),
                    "reason": c.reason or "Consulta Médica",
                    "diagnosis": c.diagnosis or "Consulta General",
                    "treatment": c.treatment or "",
                    "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "",
                    "date": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
                    "time": c.created_at.strftime("%H:%M") if c.created_at else ""
                }
                for c in consultations
            ]

            # Pagos recientes para cuadre en móvil/tablet
            payments = db.query(Payment).order_by(Payment.created_at.desc()).limit(300).all()
            payments_data = [
                {
                    "id": py.id,
                    "patient_id": py.patient_id,
                    "patient_name": f"{py.patient.first_name} {py.patient.last_name}" if py.patient else "Paciente",
                    "amount": float(py.total if py.total is not None and py.total > 0 else (py.amount or 0.0)),
                    "payment_method": py.payment_method or "Efectivo",
                    "status": "Pagado" if py.status in ["paid", "Completado"] else "Pendiente",
                    "receipt_number": py.receipt_number or f"REC-{py.id:04d}",
                    "created_at": py.created_at.strftime("%Y-%m-%d %H:%M:%S") if py.created_at else "",
                    "date": py.created_at.strftime("%Y-%m-%d") if py.created_at else "",
                    "time": py.created_at.strftime("%H:%M") if py.created_at else "",
                    "notes": py.notes or ""
                }
                for py in payments
            ]

            payload = {
                "device_id": "pc_doctor_desktop",
                "message_type": "station_snapshot",
                "data": {
                    "date": target_date.strftime("%Y-%m-%d"),
                    "stats": stats,
                    "appointments": appts_data,
                    "patients": patients_data,
                    "services": services_data,
                    "consultations": consultations_data,
                    "payments": payments_data,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }

            headers = {
                "User-Agent": "Mozilla/5.0 SSCP-Desktop",
                "Content-Type": "application/json"
            }
            res = requests.post(endpoint, json=payload, headers=headers, timeout=15.0)
            return res.status_code == 200
        except Exception as e:
            import logging
            logging.getLogger("uvicorn.error").warning(f"Error al enviar snapshot al Cloud Relay: {e}")
            return False

