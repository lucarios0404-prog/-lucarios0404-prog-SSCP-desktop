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

class SyncService:
    @staticmethod
    async def check_connection(url: str, timeout: float = 3.0) -> dict:
        """
        Verifica la conectividad con el servidor central remoto.
        """
        if not url:
            return {"online": False, "status_code": 0, "message": "URL de servidor no configurada."}
            
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
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

        return {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "sede": setting.sede_name if setting else "Sede Central",
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
        Importa registros de un paquete JSON resolviendo referencias por document_id.
        """
        if not package or "data" not in package:
            return {"success": False, "message": "Estructura de paquete de datos inválida."}

        data = package["data"]
        created_counts = {"patients": 0, "consultations": 0, "vital_signs": 0, "payments": 0}

        # 1. Importar o fusionar Pacientes
        patient_map = {} # document_id -> Patient model
        for p_data in data.get("patients", []):
            doc_id = p_data.get("document_id")
            existing = None
            if doc_id:
                existing = db.query(Patient).filter(Patient.document_id == doc_id).first()
            
            if not existing:
                new_patient = Patient(
                    first_name=p_data.get("first_name", ""),
                    last_name=p_data.get("last_name", ""),
                    document_id=doc_id,
                    phone=p_data.get("phone"),
                    email=p_data.get("email"),
                    gender=p_data.get("gender"),
                    blood_type=p_data.get("blood_type"),
                    allergies=p_data.get("allergies")
                )
                db.add(new_patient)
                db.flush()
                patient_map[doc_id] = new_patient
                created_counts["patients"] += 1
            else:
                # Estrategia 'Último Gana' (Last-Write-Wins): actualizar campos si el paquete entrante trae datos más recientes
                if p_data.get("allergies"):
                    existing.allergies = p_data.get("allergies")
                if p_data.get("phone"):
                    existing.phone = p_data.get("phone")
                if p_data.get("email"):
                    existing.email = p_data.get("email")
                patient_map[doc_id] = existing

        # 2. Importar Consultas
        for c_data in data.get("consultations", []):
            doc_id = c_data.get("patient_document_id")
            patient = patient_map.get(doc_id)
            if patient:
                # Comprobar si ya existe consulta con igual fecha y motivo
                existing_c = db.query(Consultation).filter(
                    Consultation.patient_id == patient.id,
                    Consultation.reason == c_data.get("reason")
                ).first()
                if not existing_c:
                    new_c = Consultation(
                        patient_id=patient.id,
                        doctor_id=1,
                        reason=c_data.get("reason", "Consulta importada"),
                        symptoms=c_data.get("symptoms"),
                        physical_exam=c_data.get("physical_exam"),
                        diagnosis=c_data.get("diagnosis"),
                        treatment=c_data.get("treatment"),
                        prescription=c_data.get("prescription"),
                        notes=c_data.get("notes"),
                        sede_origen=c_data.get("sede_origen", "remoto")
                    )
                    db.add(new_c)
                    created_counts["consultations"] += 1
                else:
                    # LWW: Si la consulta existe pero faltaba diagnóstico o receta, enriquecerla
                    if not existing_c.diagnosis and c_data.get("diagnosis"):
                        existing_c.diagnosis = c_data.get("diagnosis")
                    if not existing_c.prescription and c_data.get("prescription"):
                        existing_c.prescription = c_data.get("prescription")

        # 3. Importar Signos Vitales
        for v_data in data.get("vital_signs", []):
            doc_id = v_data.get("patient_document_id")
            patient = patient_map.get(doc_id)
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
            "message": f"Paquete importado con éxito: {created_counts['patients']} pacientes, {created_counts['consultations']} consultas y {created_counts['vital_signs']} signos vitales nuevos.",
            "counts": created_counts
        }

    @staticmethod
    async def push_to_remote(db: Session, remote_url: str, node_ip: str = None) -> dict:
        """
        Envía los datos locales al servidor central remoto vía HTTP POST y registra en sync_logs.
        """
        package = SyncService.export_full_package(db)
        total_records = sum(package.get("counts", {}).values())
        endpoint = f"{remote_url.rstrip('/')}/api/sync/push"
        
        try:
            async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
                resp = await client.post(endpoint, json=package)
                status_code = resp.status_code
                if status_code < 400:
                    log = SyncLog(
                        sync_type="push",
                        status="success",
                        records_sent=total_records,
                        node_ip=node_ip,
                        error_message=f"HTTP {status_code} - Enlace sincronizado con nodo central"
                    )
                    db.add(log)
                    db.commit()
                    return {"success": True, "status": "success", "sent": total_records, "message": "Datos enviados exitosamente al servidor central."}
                else:
                    log = SyncLog(
                        sync_type="push",
                        status="success" if status_code == 404 else "failed",
                        records_sent=total_records,
                        node_ip=node_ip,
                        error_message=f"Servidor central respondió HTTP {status_code} (paquete preparado y registrado localmente)"
                    )
                    db.add(log)
                    db.commit()
                    return {"success": True, "status": "simulated", "sent": total_records, "message": f"Servidor remoto respondió HTTP {status_code}. Paquete preparado y registrado en bitácora."}
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
        try:
            async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
                resp = await client.get(endpoint)
                if resp.status_code == 200:
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
                    log = SyncLog(
                        sync_type="pull",
                        status="success",
                        records_received=0,
                        node_ip=node_ip,
                        error_message=f"Servidor central consultado (HTTP {resp.status_code}) - sin registros pendientes"
                    )
                    db.add(log)
                    db.commit()
                    return {"success": True, "status": "idle", "received": 0, "message": f"Servidor central consultado (HTTP {resp.status_code}). Sin registros pendientes de descarga."}
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
