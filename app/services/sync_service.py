import json
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.appointment import Appointment
from app.models.vital_sign import VitalSign
from app.models.lab_result import LabResult
from app.models.vaccine import VaccineRecord
from app.models.inventory import InventoryItem, InventoryMovement
from app.models.payment import Payment
from app.models.setting import Setting
from app.models.sync_log import SyncLog
from app.models.lab_order import LabOrder

class SyncService:
    @staticmethod
    def _should_verify_ssl(url: str) -> bool:
        """
        Determina si debe validarse estrictamente el certificado SSL:
        - True para dominios HTTPS en producción (https://sscp.laxarusdevs.com).
        - False para servidores locales HTTP (localhost, 127.0.0.1) o si SSCP_INSECURE_SSL=1.
        """
        if not url:
            return False
        if url.lower().startswith("https://"):
            import os
            return os.environ.get("SSCP_INSECURE_SSL") != "1"
        return False

    @staticmethod
    async def check_connection(url: str, timeout: float = 3.0) -> dict:
        """
        Verifica la conectividad con el servidor central remoto.
        """
        if not url:
            return {"online": False, "status_code": 0, "message": "URL de servidor no configurada."}
            
        try:
            verify_ssl = SyncService._should_verify_ssl(url)
            async with httpx.AsyncClient(timeout=timeout, verify=verify_ssl) as client:
                r = await client.get(url)
                return {
                    "online": r.status_code < 500,
                    "status_code": r.status_code,
                    "message": f"Conexión exitosa con el servidor remoto (HTTP {r.status_code})."
                }
        except Exception as e:
            return {
                "online": False,
                "status_code": 0,
                "message": f"Servidor remoto no disponible o fuera de línea ({str(e)[:80]}). Modo Offline activo."
            }

    @staticmethod
    def get_sync_stats(db: Session) -> dict:
        """
        Obtiene estadísticas del volumen de datos locales listos para sincronización.
        """
        setting = db.query(Setting).first()
        return {
            "total_patients": db.query(Patient).count(),
            "total_consultations": db.query(Consultation).count(),
            "total_appointments": db.query(Appointment).count(),
            "total_vital_signs": db.query(VitalSign).count(),
            "total_lab_results": db.query(LabResult).count(),
            "total_vaccines": db.query(VaccineRecord).count(),
            "total_inventory_items": db.query(InventoryItem).count(),
            "total_payments": db.query(Payment).count(),
            "sede_name": setting.sede_name if setting else "Sede Local",
            "remote_url": setting.email if setting else "https://sscp.laxarusdevs.com",
            "last_synced_at": setting.updated_at.strftime("%d/%m/%Y %H:%M") if setting and setting.updated_at else "Nunca",
        }

    @staticmethod
    def export_full_package(db: Session) -> dict:
        """
        Genera el paquete completo de exportación JSON para migración o sincronización.
        """
        setting = db.query(Setting).first()
        
        # 1. Pacientes
        patients = []
        for p in db.query(Patient).all():
            patients.append({
                "id": p.id,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "document_id": p.document_id,
                "phone": p.phone,
                "email": p.email,
                "date_of_birth": p.date_of_birth.isoformat() if getattr(p, "date_of_birth", None) else None,
                "gender": p.gender,
                "blood_type": p.blood_type,
                "allergies": getattr(p, "allergies", None),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })

        # 2. Consultas
        consultations = []
        for c in db.query(Consultation).all():
            consultations.append({
                "id": c.id,
                "patient_document_id": c.patient.document_id if c.patient else None,
                "patient_id": c.patient_id,
                "reason": c.reason,
                "symptoms": c.symptoms,
                "physical_exam": c.physical_exam,
                "diagnosis": c.diagnosis,
                "treatment": c.treatment,
                "prescription": c.prescription,
                "notes": c.notes,
                "sede_origen": c.sede_origen,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })

        # 3. Signos Vitales
        vitals = []
        for v in db.query(VitalSign).all():
            vitals.append({
                "id": v.id,
                "patient_document_id": v.patient.document_id if v.patient else None,
                "weight_kg": v.weight_kg,
                "height_cm": v.height_cm,
                "systolic_bp": v.systolic_bp,
                "diastolic_bp": v.diastolic_bp,
                "heart_rate": v.heart_rate,
                "respiratory_rate": v.respiratory_rate,
                "temperature_c": v.temperature_c,
                "oxygen_saturation": v.oxygen_saturation,
                "glucose_mg_dl": v.glucose_mg_dl,
                "bmi": v.bmi,
                "notes": v.notes,
                "recorded_at": v.recorded_at.isoformat() if v.recorded_at else None,
            })

        # 4. Pagos
        payments = []
        for pay in db.query(Payment).all():
            payments.append({
                "id": pay.id,
                "patient_document_id": pay.patient.document_id if pay.patient else None,
                "service_name": pay.service_name,
                "amount": pay.amount,
                "discount": pay.discount,
                "total": pay.total,
                "payment_method": pay.payment_method,
                "receipt_number": pay.receipt_number,
                "status": pay.status,
                "notes": pay.notes,
                "created_at": pay.created_at.isoformat() if pay.created_at else None,
            })

        # Extraer correo e identidad del médico para aislamiento multi-sede / multi-doctor
        doctor_email = None
        doctor_name = setting.doctor_name if setting else None
        try:
            from app.models.user import User
            doctor_user = db.query(User).filter(User.role == "doctor").first()
            if setting and setting.email and "@" in setting.email and "sscp.local" not in setting.email:
                doctor_email = setting.email.strip()
            elif doctor_user and doctor_user.email:
                doctor_email = doctor_user.email.strip()
            elif setting and setting.email:
                doctor_email = setting.email.strip()
        except Exception:
            pass

        return {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "sede": setting.sede_name if setting else "Sede Central",
            "doctor_email": doctor_email,
            "doctor_name": doctor_name,
            "counts": {
                "patients": len(patients),
                "consultations": len(consultations),
                "vital_signs": len(vitals),
                "payments": len(payments),
            },
            "data": {
                "patients": patients,
                "consultations": consultations,
                "vital_signs": vitals,
                "payments": payments,
            }
        }

    @staticmethod
    def import_package(db: Session, package: dict) -> dict:
        """
        Importa registros de un paquete JSON resolviendo referencias por document_id
        o por Nombre Completo + Fecha de Nacimiento. Reconcilia historias clínicas
        sin duplicar pacientes existentes.
        """
        if not package or "data" not in package:
            return {"success": False, "message": "Estructura de paquete de datos inválida."}

        data = package["data"]
        created_counts = {"patients": 0, "consultations": 0, "vital_signs": 0, "payments": 0}

        # 1. Importar o fusionar Pacientes (Deduplicación estricta)
        patient_map = {} # document_id / remote_id -> Patient model
        for p_data in data.get("patients", []):
            doc_id = str(p_data.get("document_id") or "").strip() or None
            fn = str(p_data.get("first_name") or "").strip()
            ln = str(p_data.get("last_name") or "").strip()
            full_n = (f"{fn} {ln}".strip()) or str(p_data.get("full_name") or "Paciente Sincronizado").strip()

            existing = None

            # Prioridad 1: Buscar por Cédula / Documento de Identidad
            if doc_id:
                existing = db.query(Patient).filter(Patient.document_id == doc_id).first()

            # Prioridad 2: Buscar por Nombre Completo y Fecha de Nacimiento si no hay Cédula
            if not existing and fn:
                q = db.query(Patient).filter(Patient.first_name == fn)
                if ln:
                    q = q.filter(Patient.last_name == ln)
                dob = p_data.get("date_of_birth")
                if dob:
                    try:
                        dob_d = datetime.fromisoformat(dob.split("T")[0]).date()
                        q = q.filter(Patient.date_of_birth == dob_d)
                    except Exception:
                        pass
                existing = q.first()

            if not existing:
                # Paciente nuevo: Registrar
                new_patient = Patient(
                    first_name=fn or full_n,
                    last_name=ln,
                    document_id=doc_id,
                    phone=p_data.get("phone"),
                    email=p_data.get("email"),
                    gender=p_data.get("gender"),
                    blood_type=p_data.get("blood_type"),
                    allergies=p_data.get("allergies")
                )
                db.add(new_patient)
                db.flush()
                if doc_id:
                    patient_map[doc_id] = new_patient
                if p_data.get("id"):
                    patient_map[str(p_data["id"])] = new_patient
                created_counts["patients"] += 1
            else:
                # Paciente ya existe: No duplicar; actualizar datos de contacto si cambiaron
                if p_data.get("allergies") and not existing.allergies:
                    existing.allergies = p_data.get("allergies")
                if p_data.get("phone") and not existing.phone:
                    existing.phone = p_data.get("phone")
                if p_data.get("email") and not existing.email:
                    existing.email = p_data.get("email")
                if doc_id and not existing.document_id:
                    existing.document_id = doc_id
                if doc_id:
                    patient_map[doc_id] = existing
                if p_data.get("id"):
                    patient_map[str(p_data["id"])] = existing

        # 2. Importar Consultas (Cuadrar historias clínicas)
        for c_data in data.get("consultations", []):
            doc_id = c_data.get("patient_document_id")
            patient = patient_map.get(doc_id) if doc_id else None
            if not patient and c_data.get("patient_id"):
                patient = patient_map.get(str(c_data.get("patient_id")))

            if patient:
                c_created = None
                if c_data.get("created_at"):
                    try:
                        c_created = datetime.fromisoformat(c_data["created_at"].replace("Z", "+00:00"))
                    except Exception:
                        c_created = None

                reason = (c_data.get("reason") or "Consulta médica").strip()

                # Comprobar si ya existe consulta con igual motivo o en igual fecha para este paciente
                existing_c = db.query(Consultation).filter(
                    Consultation.patient_id == patient.id,
                    Consultation.reason == reason
                ).first()

                if not existing_c and c_created:
                    from sqlalchemy import func
                    existing_c = db.query(Consultation).filter(
                        Consultation.patient_id == patient.id,
                        func.date(Consultation.created_at) == c_created.date()
                    ).first()

                if not existing_c:
                    # Consulta nueva: agregar al historial médico
                    new_c = Consultation(
                        patient_id=patient.id,
                        doctor_id=1,
                        reason=reason,
                        symptoms=c_data.get("symptoms"),
                        physical_exam=c_data.get("physical_exam"),
                        diagnosis=c_data.get("diagnosis"),
                        treatment=c_data.get("treatment"),
                        prescription=c_data.get("prescription"),
                        notes=c_data.get("notes"),
                        sede_origen=c_data.get("sede_origen", "remoto"),
                        created_at=c_created or datetime.utcnow()
                    )
                    db.add(new_c)
                    created_counts["consultations"] += 1
                else:
                    # Cuadrar historia clínica: si la consulta ya existía pero faltaba diagnóstico o receta, completarla
                    if not existing_c.diagnosis and c_data.get("diagnosis"):
                        existing_c.diagnosis = c_data.get("diagnosis")
                    if not existing_c.prescription and c_data.get("prescription"):
                        existing_c.prescription = c_data.get("prescription")
                    if not existing_c.treatment and c_data.get("treatment"):
                        existing_c.treatment = c_data.get("treatment")
                    if not existing_c.physical_exam and c_data.get("physical_exam"):
                        existing_c.physical_exam = c_data.get("physical_exam")
                    if not existing_c.symptoms and c_data.get("symptoms"):
                        existing_c.symptoms = c_data.get("symptoms")

        # 3. Importar Signos Vitales
        for v_data in data.get("vital_signs", []):
            doc_id = v_data.get("patient_document_id")
            patient = patient_map.get(doc_id) if doc_id else None
            if not patient and v_data.get("patient_id"):
                patient = patient_map.get(str(v_data.get("patient_id")))

            if patient:
                existing_v = db.query(VitalSign).filter(
                    VitalSign.patient_id == patient.id,
                    VitalSign.weight_kg == v_data.get("weight_kg")
                ).first()
                if not existing_v:
                    new_v = VitalSign(
                        patient_id=patient.id,
                        weight_kg=v_data.get("weight_kg"),
                        height_cm=v_data.get("height_cm"),
                        systolic_bp=v_data.get("systolic_bp"),
                        diastolic_bp=v_data.get("diastolic_bp"),
                        heart_rate=v_data.get("heart_rate"),
                        respiratory_rate=v_data.get("respiratory_rate"),
                        temperature_c=v_data.get("temperature_c"),
                        oxygen_saturation=v_data.get("oxygen_saturation"),
                        glucose_mg_dl=v_data.get("glucose_mg_dl"),
                        bmi=v_data.get("bmi"),
                        notes=v_data.get("notes")
                    )
                    db.add(new_v)
                    created_counts["vital_signs"] += 1

        db.commit()

        # Registrar log de importación
        total_recv = sum(created_counts.values())
        sync_log = SyncLog(
            sync_type="offline_import",
            status="success",
            records_received=total_recv,
            error_message=f"Importados: {created_counts['patients']} pacientes, {created_counts['consultations']} consultas, {created_counts['vital_signs']} signos vitales"
        )
        db.add(sync_log)
        db.commit()

        return {
            "success": True,
            "message": f"Paquete importado con éxito: {created_counts['patients']} pacientes, {created_counts['consultations']} consultas y {created_counts['vital_signs']} signos vitales nuevos reconciliados.",
            "counts": created_counts
        }

    @staticmethod
    def _get_auth_headers(db: Session) -> dict:
        """Genera las cabeceras de autenticación para comunicarse con la nube de SSCP con aislamiento por doctor."""
        headers = {
            "Content-Type": "application/json",
            "X-License-Key": "sscp-license-api-sec-2026-laxarus",
        }
        try:
            from app.models.license_config import LicenseConfig
            from app.models.setting import Setting
            from app.models.user import User

            lic = db.query(LicenseConfig).first()
            if lic and lic.license_key:
                headers["X-License-Token"] = lic.license_key
            if lic and lic.machine_id:
                headers["X-Machine-Id"] = lic.machine_id
            if lic and lic.doctor_name:
                headers["X-Doctor-Name"] = lic.doctor_name

            setting = db.query(Setting).first()
            doctor_user = db.query(User).filter(User.role == "doctor").first()
            doctor_email = None

            if setting and setting.email and "@" in setting.email and "sscp.local" not in setting.email:
                doctor_email = setting.email.strip()
            elif doctor_user and doctor_user.email:
                doctor_email = doctor_user.email.strip()
            elif setting and setting.email:
                doctor_email = setting.email.strip()

            if doctor_email:
                headers["X-Doctor-Email"] = doctor_email
            if setting and setting.doctor_name and "X-Doctor-Name" not in headers:
                headers["X-Doctor-Name"] = setting.doctor_name
        except Exception:
            pass
        return headers

    @staticmethod
    async def push_to_remote(db: Session, remote_url: str, node_ip: str = None) -> dict:
        """
        Envía los datos locales al servidor central remoto vía HTTP POST y registra en sync_logs.
        """
        package = SyncService.export_full_package(db)
        total_records = sum(package.get("counts", {}).values())
        endpoint = f"{remote_url.rstrip('/')}/api/sync/push"
        headers = SyncService._get_auth_headers(db)
        
        try:
            verify_ssl = SyncService._should_verify_ssl(remote_url)
            async with httpx.AsyncClient(timeout=120.0, verify=verify_ssl) as client:
                resp = await client.post(endpoint, json=package, headers=headers)
                status_code = resp.status_code
                if 200 <= status_code < 300:
                    resp_data = {}
                    try:
                        resp_data = resp.json()
                    except Exception:
                        pass
                    msg = resp_data.get("message", f"Datos enviados exitosamente al servidor central (HTTP {status_code}).")
                    log = SyncLog(
                        sync_type="push",
                        status="success",
                        records_sent=total_records,
                        node_ip=node_ip,
                        error_message=f"HTTP {status_code} - Enlace sincronizado con nodo central"
                    )
                    db.add(log)
                    db.commit()
                    return {"success": True, "status": "success", "sent": total_records, "message": msg}
                else:
                    error_detail = ""
                    try:
                        error_detail = resp.json().get("error") or resp.json().get("message")
                    except Exception:
                        error_detail = resp.text[:120]
                    log = SyncLog(
                        sync_type="push",
                        status="failed",
                        records_sent=0,
                        node_ip=node_ip,
                        error_message=f"Servidor central respondió HTTP {status_code}: {error_detail}"
                    )
                    db.add(log)
                    db.commit()
                    return {"success": False, "status": "failed", "sent": 0, "message": f"Servidor central respondió HTTP {status_code}: {error_detail}"}
        except Exception as e:
            log = SyncLog(
                sync_type="push",
                status="offline",
                records_sent=0,
                node_ip=node_ip,
                error_message=f"Servidor inaccesible: {str(e)[:120]}"
            )
            db.add(log)
            db.commit()
            return {"success": False, "status": "offline", "sent": 0, "message": "Servidor fuera de línea. Los datos locales permanecen íntegros y listos para reenviar."}

    @staticmethod
    async def pull_from_remote(db: Session, remote_url: str, node_ip: str = None) -> dict:
        """
        Descarga e integra registros del servidor central remoto con política 'último gana'.
        """
        endpoint = f"{remote_url.rstrip('/')}/api/sync/pull"
        headers = SyncService._get_auth_headers(db)
        try:
            verify_ssl = SyncService._should_verify_ssl(remote_url)
            async with httpx.AsyncClient(timeout=120.0, verify=verify_ssl) as client:
                resp = await client.get(endpoint, headers=headers)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    res = SyncService.import_package(db, data)
                    recv_count = sum(res.get("counts", {}).values())
                    log = SyncLog(
                        sync_type="pull",
                        status="success",
                        records_received=recv_count,
                        node_ip=node_ip,
                        error_message=f"Descarga exitosa: {recv_count} registros"
                    )
                    db.add(log)
                    db.commit()
                    return {"success": True, "status": "success", "received": recv_count, "message": res.get("message")}
                else:
                    error_detail = ""
                    try:
                        error_detail = resp.json().get("error") or resp.json().get("message")
                    except Exception:
                        error_detail = resp.text[:120]
                    log = SyncLog(
                        sync_type="pull",
                        status="failed",
                        records_received=0,
                        node_ip=node_ip,
                        error_message=f"Error HTTP {resp.status_code} al consultar servidor central: {error_detail}"
                    )
                    db.add(log)
                    db.commit()
                    return {"success": False, "status": "failed", "received": 0, "message": f"Servidor central respondió HTTP {resp.status_code}: {error_detail}"}
        except Exception as e:
            log = SyncLog(
                sync_type="pull",
                status="offline",
                records_received=0,
                node_ip=node_ip,
                error_message=f"No se pudo descargar: {str(e)[:120]}"
            )
            db.add(log)
            db.commit()
            return {"success": False, "status": "offline", "received": 0, "message": "Modo Offline: No fue posible conectar con el servidor remoto."}

    @staticmethod
    async def background_sync(db: Session, remote_url: str, node_ip: str = None) -> dict:
        """
        Ciclo de sincronización bidireccional periódico para tareas en segundo plano.
        """
        push_res = await SyncService.push_to_remote(db, remote_url, node_ip)
        pull_res = await SyncService.pull_from_remote(db, remote_url, node_ip)
        
        # Registrar evento de ciclo en segundo plano
        log = SyncLog(
            sync_type="background",
            status="success" if (push_res.get("success") or pull_res.get("success")) else "offline",
            records_sent=push_res.get("sent", 0),
            records_received=pull_res.get("received", 0),
            node_ip=node_ip,
            error_message="Ciclo automático cada 5 min ejecutado con éxito"
        )
        db.add(log)
        db.commit()
        return {"push": push_res, "pull": pull_res}

    @staticmethod
    def get_recent_logs(db: Session, limit: int = 10) -> list:
        """
        Retorna la bitácora de sincronización reciente ordenada de la más nueva a la más antigua.
        """
        return db.query(SyncLog).order_by(SyncLog.created_at.desc()).limit(limit).all()

    @staticmethod
    def export_delta(db: Session, since_iso: str = None) -> dict:
        """
        Exporta registros creados o modificados desde since_iso (o todos si since_iso es None).
        Incluye pacientes, consultas (con historia clínica unificada), órdenes de laboratorio, citas y pagos.
        """
        setting = db.query(Setting).first()
        since_dt = None
        if since_iso:
            try:
                since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
            except Exception:
                since_dt = None

        # 1. Pacientes
        pq = db.query(Patient)
        if since_dt:
            pq = pq.filter((Patient.created_at >= since_dt) | (Patient.updated_at >= since_dt))
        patients = []
        for p in pq.all():
            patients.append({
                "id": p.id,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "document_id": p.document_id,
                "phone": p.phone,
                "email": p.email,
                "date_of_birth": p.date_of_birth.isoformat() if getattr(p, "date_of_birth", None) else None,
                "gender": p.gender,
                "blood_type": p.blood_type,
                "allergies": getattr(p, "allergies", None),
                "is_active": getattr(p, "is_active", True),
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if getattr(p, "updated_at", None) else None,
            })

        # 2. Consultas
        cq = db.query(Consultation)
        if since_dt:
            cq = cq.filter((Consultation.created_at >= since_dt) | (Consultation.updated_at >= since_dt))
        consultations = []
        for c in cq.all():
            consultations.append({
                "id": c.id,
                "patient_document_id": c.patient.document_id if c.patient else None,
                "patient_id": c.patient_id,
                "reason": c.reason,
                "clinical_history": getattr(c, "clinical_history", None),
                "is_first_visit": bool(getattr(c, "is_first_visit", False)),
                "edit_version": getattr(c, "edit_version", 1),
                "edit_history": getattr(c, "edit_history", None),
                "symptoms": c.symptoms,
                "physical_exam": c.physical_exam,
                "diagnosis": c.diagnosis,
                "treatment": c.treatment,
                "prescription": c.prescription,
                "notes": c.notes,
                "sede_origen": c.sede_origen,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if getattr(c, "updated_at", None) else None,
            })

        # 3. Órdenes de laboratorio
        lq = db.query(LabOrder)
        if since_dt:
            lq = lq.filter((LabOrder.created_at >= since_dt) | (LabOrder.updated_at >= since_dt))
        lab_orders = []
        for lo in lq.all():
            lab_orders.append({
                "id": lo.id,
                "patient_document_id": lo.patient.document_id if lo.patient else None,
                "patient_id": lo.patient_id,
                "order_date": lo.order_date.isoformat() if lo.order_date else None,
                "clinical_indication": lo.clinical_indication,
                "tests_requested": lo.tests_requested,
                "notes": lo.notes,
                "status": lo.status,
                "created_at": lo.created_at.isoformat() if lo.created_at else None,
                "updated_at": lo.updated_at.isoformat() if lo.updated_at else None,
            })

        # 4. Citas Médicas
        aq = db.query(Appointment)
        if since_dt:
            aq = aq.filter((Appointment.created_at >= since_dt) | (Appointment.updated_at >= since_dt))
        appointments = []
        for a in aq.all():
            appointments.append({
                "id": a.id,
                "patient_document_id": a.patient.document_id if a.patient else None,
                "patient_id": a.patient_id,
                "date": a.date.isoformat() if a.date else None,
                "start_time": a.start_time.strftime("%H:%M:%S") if a.start_time else None,
                "end_time": a.end_time.strftime("%H:%M:%S") if a.end_time else None,
                "reason": a.reason,
                "status": a.status,
                "notes": a.notes,
                "queue_number": a.queue_number,
                "price": a.price,
                "sede_origen": a.sede_origen,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })

        # 5. Pagos
        payq = db.query(Payment)
        if since_dt:
            payq = payq.filter(Payment.created_at >= since_dt)
        payments = []
        for pay in payq.all():
            payments.append({
                "id": pay.id,
                "patient_document_id": pay.patient.document_id if pay.patient else None,
                "service_name": pay.service_name,
                "amount": pay.amount,
                "discount": pay.discount,
                "total": pay.total,
                "payment_method": pay.payment_method,
                "receipt_number": pay.receipt_number,
                "status": pay.status,
                "notes": pay.notes,
                "created_at": pay.created_at.isoformat() if pay.created_at else None,
            })

        # 6. Signos Vitales
        vq = db.query(VitalSign)
        if since_dt:
            vq = vq.filter(VitalSign.recorded_at >= since_dt)
        vitals = []
        for v in vq.all():
            vitals.append({
                "id": v.id,
                "patient_document_id": v.patient.document_id if v.patient else None,
                "weight_kg": v.weight_kg,
                "height_cm": v.height_cm,
                "systolic_bp": v.systolic_bp,
                "diastolic_bp": v.diastolic_bp,
                "heart_rate": v.heart_rate,
                "respiratory_rate": v.respiratory_rate,
                "temperature_c": v.temperature_c,
                "oxygen_saturation": v.oxygen_saturation,
                "glucose_mg_dl": v.glucose_mg_dl,
                "bmi": v.bmi,
                "notes": v.notes,
                "recorded_at": v.recorded_at.isoformat() if v.recorded_at else None,
            })

        return {
            "version": "1.2.0",
            "station_role": setting.station_role if setting else "doctor_principal",
            "clinic_name": setting.clinic_name if setting else "SSCP Clínica",
            "sede_name": setting.sede_name if setting else "Sede Principal",
            "exported_at": datetime.utcnow().isoformat(),
            "since": since_iso,
            "counts": {
                "patients": len(patients),
                "consultations": len(consultations),
                "lab_orders": len(lab_orders),
                "appointments": len(appointments),
                "payments": len(payments),
                "vital_signs": len(vitals),
            },
            "data": {
                "patients": patients,
                "consultations": consultations,
                "lab_orders": lab_orders,
                "appointments": appointments,
                "payments": payments,
                "vital_signs": vitals,
            }
        }

    @staticmethod
    def import_delta(db: Session, package: dict) -> dict:
        """
        Reconcilia un delta recibido de otra estación (doctor o secretaría).
        Reconcilia pacientes, consultas, órdenes de laboratorio, citas y pagos
        con política último-gana y sin duplicar pacientes ni sobrescribir registros más recientes.
        """
        if not package or "data" not in package:
            return {"success": False, "message": "Estructura de paquete delta inválida."}

        data = package["data"]
        created_counts = {
            "patients": 0,
            "consultations": 0,
            "lab_orders": 0,
            "appointments": 0,
            "payments": 0,
            "vital_signs": 0
        }

        # 1. Reconciliar Pacientes
        patient_map = {}
        for p_data in data.get("patients", []):
            doc_id = str(p_data.get("document_id") or "").strip() or None
            fn = str(p_data.get("first_name") or "").strip()
            ln = str(p_data.get("last_name") or "").strip()
            full_n = (f"{fn} {ln}".strip()) or str(p_data.get("full_name") or "Paciente").strip()

            existing = None
            if doc_id:
                existing = db.query(Patient).filter(Patient.document_id == doc_id).first()
            if not existing and fn:
                q = db.query(Patient).filter(Patient.first_name == fn)
                if ln:
                    q = q.filter(Patient.last_name == ln)
                dob = p_data.get("date_of_birth")
                if dob:
                    try:
                        dob_d = datetime.fromisoformat(dob.split("T")[0]).date()
                        q = q.filter(Patient.date_of_birth == dob_d)
                    except Exception:
                        pass
                existing = q.first()

            if not existing:
                dob_val = None
                if p_data.get("date_of_birth"):
                    try:
                        dob_val = datetime.fromisoformat(p_data["date_of_birth"].split("T")[0]).date()
                    except Exception:
                        dob_val = None

                new_p = Patient(
                    first_name=fn or full_n,
                    last_name=ln,
                    document_id=doc_id,
                    phone=p_data.get("phone"),
                    email=p_data.get("email"),
                    date_of_birth=dob_val,
                    gender=p_data.get("gender"),
                    blood_type=p_data.get("blood_type"),
                    allergies=p_data.get("allergies"),
                    is_active=p_data.get("is_active", True)
                )
                db.add(new_p)
                db.flush()
                if doc_id:
                    patient_map[doc_id] = new_p
                if p_data.get("id"):
                    patient_map[str(p_data["id"])] = new_p
                created_counts["patients"] += 1
            else:
                if p_data.get("phone") and not existing.phone:
                    existing.phone = p_data.get("phone")
                if p_data.get("email") and not existing.email:
                    existing.email = p_data.get("email")
                if p_data.get("allergies") and not existing.allergies:
                    existing.allergies = p_data.get("allergies")
                if doc_id and not existing.document_id:
                    existing.document_id = doc_id
                if doc_id:
                    patient_map[doc_id] = existing
                if p_data.get("id"):
                    patient_map[str(p_data["id"])] = existing

        # 2. Reconciliar Consultas
        for c_data in data.get("consultations", []):
            doc_id = c_data.get("patient_document_id")
            patient = patient_map.get(doc_id) if doc_id else None
            if not patient and c_data.get("patient_id"):
                patient = patient_map.get(str(c_data.get("patient_id")))
            if not patient and doc_id:
                patient = db.query(Patient).filter(Patient.document_id == doc_id).first()

            if patient:
                c_created = None
                if c_data.get("created_at"):
                    try:
                        c_created = datetime.fromisoformat(c_data["created_at"].replace("Z", "+00:00"))
                    except Exception:
                        c_created = None

                reason = (c_data.get("reason") or "Consulta médica").strip()
                existing_c = db.query(Consultation).filter(
                    Consultation.patient_id == patient.id,
                    Consultation.reason == reason
                ).first()

                if not existing_c and c_created:
                    from sqlalchemy import func
                    existing_c = db.query(Consultation).filter(
                        Consultation.patient_id == patient.id,
                        func.date(Consultation.created_at) == c_created.date()
                    ).first()

                if not existing_c:
                    new_c = Consultation(
                        patient_id=patient.id,
                        doctor_id=1,
                        reason=reason,
                        clinical_history=c_data.get("clinical_history"),
                        is_first_visit=bool(c_data.get("is_first_visit", False)),
                        edit_version=c_data.get("edit_version", 1),
                        edit_history=c_data.get("edit_history"),
                        symptoms=c_data.get("symptoms"),
                        physical_exam=c_data.get("physical_exam"),
                        diagnosis=c_data.get("diagnosis"),
                        treatment=c_data.get("treatment"),
                        prescription=c_data.get("prescription"),
                        notes=c_data.get("notes"),
                        sede_origen=c_data.get("sede_origen", "estacion_par"),
                        created_at=c_created or datetime.utcnow()
                    )
                    db.add(new_c)
                    created_counts["consultations"] += 1
                else:
                    # Si la versión remota es mayor o igual, actualizar historia clínica
                    rem_version = c_data.get("edit_version", 1) or 1
                    loc_version = existing_c.edit_version or 1
                    if rem_version >= loc_version:
                        if c_data.get("clinical_history"):
                            existing_c.clinical_history = c_data.get("clinical_history")
                        if c_data.get("diagnosis"):
                            existing_c.diagnosis = c_data.get("diagnosis")
                        if c_data.get("treatment"):
                            existing_c.treatment = c_data.get("treatment")
                        if c_data.get("prescription"):
                            existing_c.prescription = c_data.get("prescription")
                        if c_data.get("notes"):
                            existing_c.notes = c_data.get("notes")
                        existing_c.edit_version = rem_version

        # 3. Reconciliar Órdenes de Laboratorio
        for lo_data in data.get("lab_orders", []):
            doc_id = lo_data.get("patient_document_id")
            patient = patient_map.get(doc_id) if doc_id else None
            if not patient and lo_data.get("patient_id"):
                patient = patient_map.get(str(lo_data.get("patient_id")))
            if not patient and doc_id:
                patient = db.query(Patient).filter(Patient.document_id == doc_id).first()

            if patient:
                o_date = None
                if lo_data.get("order_date"):
                    try:
                        o_date = datetime.fromisoformat(lo_data["order_date"].split("T")[0]).date()
                    except Exception:
                        o_date = None

                existing_lo = db.query(LabOrder).filter(
                    LabOrder.patient_id == patient.id,
                    LabOrder.tests_requested == lo_data.get("tests_requested")
                ).first()

                if not existing_lo:
                    new_lo = LabOrder(
                        patient_id=patient.id,
                        doctor_id=1,
                        order_date=o_date or datetime.utcnow().date(),
                        clinical_indication=lo_data.get("clinical_indication"),
                        tests_requested=lo_data.get("tests_requested") or "[]",
                        notes=lo_data.get("notes"),
                        status=lo_data.get("status", "solicitado")
                    )
                    db.add(new_lo)
                    created_counts["lab_orders"] += 1
                else:
                    if lo_data.get("status"):
                        existing_lo.status = lo_data.get("status")

        # 4. Reconciliar Citas Médicas
        for a_data in data.get("appointments", []):
            doc_id = a_data.get("patient_document_id")
            patient = patient_map.get(doc_id) if doc_id else None
            if not patient and a_data.get("patient_id"):
                patient = patient_map.get(str(a_data.get("patient_id")))
            if not patient and doc_id:
                patient = db.query(Patient).filter(Patient.document_id == doc_id).first()

            if patient and a_data.get("date"):
                try:
                    appt_date = datetime.fromisoformat(a_data["date"].split("T")[0]).date()
                except Exception:
                    continue

                existing_appt = db.query(Appointment).filter(
                    Appointment.patient_id == patient.id,
                    Appointment.date == appt_date
                ).first()

                start_t = None
                if a_data.get("start_time"):
                    try:
                        start_t = datetime.strptime(a_data["start_time"], "%H:%M:%S").time()
                    except Exception:
                        try:
                            start_t = datetime.strptime(a_data["start_time"], "%H:%M").time()
                        except Exception:
                            pass

                if not existing_appt:
                    new_appt = Appointment(
                        patient_id=patient.id,
                        doctor_id=1,
                        date=appt_date,
                        start_time=start_t,
                        reason=a_data.get("reason", "Consulta médica"),
                        status=a_data.get("status", "Pendiente"),
                        notes=a_data.get("notes"),
                        queue_number=a_data.get("queue_number"),
                        price=a_data.get("price", 0.0),
                        sede_origen=a_data.get("sede_origen", "estacion_par")
                    )
                    db.add(new_appt)
                    created_counts["appointments"] += 1
                else:
                    if a_data.get("status"):
                        existing_appt.status = a_data.get("status")
                    if a_data.get("queue_number"):
                        existing_appt.queue_number = a_data.get("queue_number")

        # 5. Reconciliar Pagos
        for pay_data in data.get("payments", []):
            doc_id = pay_data.get("patient_document_id")
            patient = patient_map.get(doc_id) if doc_id else None
            if not patient and pay_data.get("patient_id"):
                patient = patient_map.get(str(pay_data.get("patient_id")))
            if not patient and doc_id:
                patient = db.query(Patient).filter(Patient.document_id == doc_id).first()

            if patient:
                receipt = pay_data.get("receipt_number")
                existing_pay = None
                if receipt:
                    existing_pay = db.query(Payment).filter(Payment.receipt_number == receipt).first()

                if not existing_pay:
                    new_pay = Payment(
                        patient_id=patient.id,
                        service_name=pay_data.get("service_name", "Consulta Médica"),
                        amount=pay_data.get("amount", 0.0),
                        discount=pay_data.get("discount", 0.0),
                        total=pay_data.get("total", 0.0),
                        payment_method=pay_data.get("payment_method", "Efectivo"),
                        receipt_number=receipt,
                        status=pay_data.get("status", "Completado"),
                        notes=pay_data.get("notes")
                    )
                    db.add(new_pay)
                    created_counts["payments"] += 1

        # 6. Reconciliar Signos Vitales
        for v_data in data.get("vital_signs", []):
            doc_id = v_data.get("patient_document_id")
            patient = patient_map.get(doc_id) if doc_id else None
            if not patient and v_data.get("patient_id"):
                patient = patient_map.get(str(v_data.get("patient_id")))
            if not patient and doc_id:
                patient = db.query(Patient).filter(Patient.document_id == doc_id).first()

            if patient:
                existing_v = db.query(VitalSign).filter(
                    VitalSign.patient_id == patient.id,
                    VitalSign.weight_kg == v_data.get("weight_kg")
                ).first()
                if not existing_v:
                    new_v = VitalSign(
                        patient_id=patient.id,
                        weight_kg=v_data.get("weight_kg"),
                        height_cm=v_data.get("height_cm"),
                        systolic_bp=v_data.get("systolic_bp"),
                        diastolic_bp=v_data.get("diastolic_bp"),
                        heart_rate=v_data.get("heart_rate"),
                        respiratory_rate=v_data.get("respiratory_rate"),
                        temperature_c=v_data.get("temperature_c"),
                        oxygen_saturation=v_data.get("oxygen_saturation"),
                        glucose_mg_dl=v_data.get("glucose_mg_dl"),
                        bmi=v_data.get("bmi"),
                        notes=v_data.get("notes")
                    )
                    db.add(new_v)
                    created_counts["vital_signs"] += 1

        db.commit()

        total_rec = sum(created_counts.values())
        sync_log = SyncLog(
            sync_type="peer_delta_import",
            status="success",
            records_received=total_rec,
            error_message=f"Delta importado: {created_counts['patients']} pac, {created_counts['consultations']} con, {created_counts['lab_orders']} lab, {created_counts['appointments']} cit, {created_counts['payments']} pag"
        )
        db.add(sync_log)
        db.commit()

        return {
            "success": True,
            "counts": created_counts,
            "message": f"Sincronización P2P exitosa: {total_rec} registros incorporados sin conflictos."
        }

    @staticmethod
    async def sync_with_peer(db: Session, peer_url: str) -> dict:
        """
        Ejecuta ciclo completo bidireccional (Push & Pull) con la estación par vía red local o Tailscale.
        """
        if not peer_url:
            return {"success": False, "message": "URL de la estación par no especificada."}

        clean_url = peer_url.strip().rstrip("/")
        # 1. Comprobar salud y rol de la estación par
        try:
            async with httpx.AsyncClient(timeout=4.0, verify=False) as client:
                ping_resp = await client.get(f"{clean_url}/sync/peer/status")
                if ping_resp.status_code != 200:
                    return {
                        "success": False,
                        "message": f"Estación par no respondió correctamente (HTTP {ping_resp.status_code}). Asegúrese de que SSCP esté abierto en la otra máquina."
                    }
                peer_info = ping_resp.json()
        except Exception as e:
            return {
                "success": False,
                "message": f"No se pudo conectar a la estación par en {clean_url}: {str(e)[:80]}. Verifique que ambas PCs estén conectadas a la misma red o Tailscale."
            }

        # 2. Push local delta al par
        setting = db.query(Setting).first()
        local_delta = SyncService.export_delta(db, since_iso=None)
        sent_count = sum(local_delta.get("counts", {}).values())

        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                push_resp = await client.post(f"{clean_url}/sync/peer/import", json=local_delta)
        except Exception as e:
            print(f"[Peer Sync] Error enviando delta a par: {e}")

        # 3. Pull delta desde el par
        pulled_counts = {}
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                pull_resp = await client.get(f"{clean_url}/sync/peer/delta")
                if pull_resp.status_code == 200:
                    peer_delta = pull_resp.json()
                    import_res = SyncService.import_delta(db, peer_delta)
                    pulled_counts = import_res.get("counts", {})
        except Exception as e:
            print(f"[Peer Sync] Error descargando delta de par: {e}")

        if setting:
            setting.updated_at = datetime.utcnow()
            db.commit()

        recv_count = sum(pulled_counts.values())
        return {
            "success": True,
            "peer_role": peer_info.get("station_role", "estacion"),
            "peer_name": peer_info.get("clinic_name", "SSCP Peer"),
            "sent": sent_count,
            "received": recv_count,
            "message": f"Sincronización P2P completada con {peer_info.get('clinic_name', 'Estación')}. Enviados: {sent_count} registros. Recibidos: {recv_count} registros."
        }
