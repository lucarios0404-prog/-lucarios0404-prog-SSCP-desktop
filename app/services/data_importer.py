"""
Data Importer Service for SSCP Desktop.
Supports importing patients and clinical histories from:
- 'Consulta Práctica' legacy databases (.mdb format)
- CSV / TXT tabular exports
- Excel (.xlsx) spreadsheets
"""
import re
import csv
import io
import json
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.patient import Patient
from app.models.consultation import Consultation
from app.models.audit_log import ClinicalAuditLog

def clean_utf8(val: Any) -> str:
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    return val.strip()

def strip_rtf(rtf_str: str) -> str:
    if not rtf_str:
        return ""
    rtf_str = clean_utf8(rtf_str)
    if not rtf_str.startswith("{\\rtf"):
        return rtf_str.strip()
    pattern = re.compile(r'\\([a-z]+)(-?\d+)? ?|[{}]|\\\n|\\r|\\f', re.IGNORECASE)
    cleaned = re.sub(pattern, '', rtf_str)
    return cleaned.strip()

def split_name(full_name: str) -> Tuple[str, str]:
    full_name = clean_utf8(full_name)
    if not full_name:
        return ("Paciente", "Sin Nombre")
    if "," in full_name:
        parts = full_name.split(",", 1)
        return (parts[1].strip(), parts[0].strip())
    
    parts = full_name.split()
    if len(parts) == 1:
        return (parts[0], "")
    elif len(parts) == 2:
        return (parts[0], parts[1])
    elif len(parts) == 3:
        return (f"{parts[0]} {parts[1]}", parts[2])
    else:
        # 4 or more: first 2 given names, remaining are surnames
        return (" ".join(parts[:2]), " ".join(parts[2:]))

def parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    
    s = clean_utf8(val)
    if not s:
        return None
    
    # Common date formats: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
        "%d/%m/%y", "%d-%m-%y", "%Y%m%d"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s.split()[0], fmt).date()
        except Exception:
            continue
    return None

def parse_datetime(date_val: Any, time_val: Any = None) -> datetime:
    d = parse_date(date_val)
    if not d:
        return datetime.utcnow()
    
    t_str = clean_utf8(time_val) if time_val else "08:00"
    try:
        if ":" in t_str:
            parts = t_str.split(":")
            h = int(parts[0])
            m = int(parts[1][:2])
            return datetime(d.year, d.month, d.day, h, m)
    except Exception:
        pass
    return datetime(d.year, d.month, d.day, 8, 0)

class DataImporterService:

    @classmethod
    def parse_mdb(cls, file_path: str) -> List[Dict[str, Any]]:
        """
        Parses Microsoft Access .mdb database from Consulta Práctica.
        """
        from access_parser import AccessParser
        
        db = AccessParser(file_path)
        tables = db.catalog
        
        patients_table_name = None
        for t in ["Identificacion", "Pacientes", "PACIENTES", "identificacion", "pacientes"]:
            if t in tables:
                patients_table_name = t
                break
                
        history_table_name = None
        for t in ["Historias", "HISTORIAS", "Consultas", "historias", "consultas"]:
            if t in tables:
                history_table_name = t
                break
                
        if not patients_table_name:
            raise ValueError("No se encontró la tabla de pacientes ('Identificacion') en el archivo MDB de Consulta Práctica.")
            
        patients_raw = db.parse_table(patients_table_name)
        history_raw = db.parse_table(history_table_name) if history_table_name else {}
        
        id_pac_list = patients_raw.get('IDPac', patients_raw.get('idpac', []))
        num_patients = len(id_pac_list)
        
        patients_dict: Dict[Any, Dict[str, Any]] = {}
        for i in range(num_patients):
            id_pac = id_pac_list[i]
            name = clean_utf8(patients_raw.get('Nombre', patients_raw.get('nombre', []))[i]) if i < len(patients_raw.get('Nombre', [])) else ""
            if not name:
                continue
                
            first_name, last_name = split_name(name)
            bdate = parse_date(patients_raw.get('BirthDate', patients_raw.get('birthdate', []))[i] if i < len(patients_raw.get('BirthDate', [])) else None)
            sex = clean_utf8(patients_raw.get('Sexo', patients_raw.get('sexo', []))[i] if i < len(patients_raw.get('Sexo', [])) else "")
            gender = "Masculino" if sex.upper().startswith("M") else ("Femenino" if sex.upper().startswith("F") else "Otro")
            
            address = clean_utf8(patients_raw.get('Domicilio', patients_raw.get('domicilio', []))[i] if i < len(patients_raw.get('Domicilio', [])) else "")
            tel = clean_utf8(patients_raw.get('Tel', patients_raw.get('tel', []))[i] if i < len(patients_raw.get('Tel', [])) else "")
            num_id = clean_utf8(patients_raw.get('NumID', patients_raw.get('numid', []))[i] if i < len(patients_raw.get('NumID', [])) else "")
            obs = clean_utf8(patients_raw.get('Observaciones', patients_raw.get('observaciones', []))[i] if i < len(patients_raw.get('Observaciones', [])) else "")
            email = clean_utf8(patients_raw.get('Email', patients_raw.get('email', []))[i] if i < len(patients_raw.get('Email', [])) else "")
            
            patients_dict[id_pac] = {
                "id_pac": id_pac,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}".strip(),
                "document_id": num_id if num_id else None,
                "date_of_birth": bdate.isoformat() if bdate else None,
                "gender": gender,
                "phone": tel if tel else None,
                "email": email if email else None,
                "address": address if address else None,
                "allergies": None,
                "blood_type": None,
                "notes": obs if obs else None,
                "consultations": []
            }
            
        if history_raw:
            hist_id_pac_list = history_raw.get('IDPac', history_raw.get('idpac', []))
            num_hist = len(hist_id_pac_list)
            
            for i in range(num_hist):
                id_pac = hist_id_pac_list[i]
                if id_pac not in patients_dict:
                    continue
                    
                fecha = history_raw.get('FechaDeLaHistoria', history_raw.get('fechadelahistoria', []))[i] if i < len(history_raw.get('FechaDeLaHistoria', [])) else ""
                hora = history_raw.get('HoraDeLaHistoria', history_raw.get('horadelahistoria', []))[i] if i < len(history_raw.get('HoraDeLaHistoria', [])) else "08:00"
                
                hist_text = clean_utf8(history_raw.get('HistoriaT', history_raw.get('historiat', []))[i] if i < len(history_raw.get('HistoriaT', [])) else "")
                if not hist_text:
                    hist_text = strip_rtf(history_raw.get('Historia', history_raw.get('historia', []))[i] if i < len(history_raw.get('Historia', [])) else "")
                    
                diag = clean_utf8(history_raw.get('Diagnostico', history_raw.get('diagnostico', []))[i] if i < len(history_raw.get('Diagnostico', [])) else "")
                trat = clean_utf8(history_raw.get('Tratamiento', history_raw.get('tratamiento', []))[i] if i < len(history_raw.get('Tratamiento', [])) else "")
                resp = clean_utf8(history_raw.get('Responsable', history_raw.get('responsable', []))[i] if i < len(history_raw.get('Responsable', [])) else "")
                
                consult_dt = parse_datetime(fecha, hora)
                
                reason_str = f"Consulta: {diag}" if diag and diag.lower() not in ["sin diagnóstico especificado", "en estudio"] else "Consulta Médica / Chequeo Clínico"
                symptoms_str = hist_text if hist_text and hist_text.lower() not in ["no recabada", "none", ""] else "Consulta histórica sin descripción de síntomas registrada."

                patients_dict[id_pac]["consultations"].append({
                    "date": consult_dt.isoformat(),
                    "reason": reason_str,
                    "symptoms": symptoms_str,
                    "diagnosis": diag if diag else "Sin diagnóstico especificado",
                    "treatment": trat if trat else None,
                    "notes": hist_text if hist_text else None,
                    "doctor_name": resp if resp else None
                })
                
        return list(patients_dict.values())

    @classmethod
    def parse_csv(cls, file_content: bytes) -> List[Dict[str, Any]]:
        """
        Parses CSV or TXT tabular files with flexible column headers.
        """
        text = ""
        for encoding in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                text = file_content.decode(encoding)
                break
            except Exception:
                continue
        if not text:
            text = file_content.decode("utf-8", errors="replace")
            
        sample = text[:2048]
        delimiter = ";" if ";" in sample and sample.count(";") > sample.count(",") else ","
        
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            return []
            
        headers = [clean_utf8(h).lower() for h in rows[0]]
        patient_records: List[Dict[str, Any]] = []
        
        for row in rows[1:]:
            if not row or not any(clean_utf8(x) for x in row):
                continue
            row_dict = {}
            for idx, h in enumerate(headers):
                if idx < len(row):
                    row_dict[h] = clean_utf8(row[idx])
                    
            # Map flexible columns
            full_name = ""
            first_name = ""
            last_name = ""
            doc_id = ""
            bdate_str = ""
            phone = ""
            email = ""
            gender = "Otro"
            address = ""
            allergies = ""
            diag = ""
            trat = ""
            motivo = "Consulta Médica General"
            notes = ""
            
            for k, v in row_dict.items():
                if any(x in k for x in ["full_name", "nombre completo", "paciente"]):
                    full_name = v
                elif "nombre" in k and "completo" not in k:
                    first_name = v
                elif "apellido" in k:
                    last_name = v
                elif any(x in k for x in ["nacimiento", "fecha_nac", "birth", "f_nac"]):
                    bdate_str = v
                elif any(x in k for x in ["cedula", "cédula", "dni", "documento", "identificacion", "identificación", "numid"]) or k in ["ci", "c.i", "c.i.", "id"]:
                    doc_id = v
                elif any(x in k for x in ["telefono", "tel", "celular", "movil", "phone"]):
                    phone = v
                elif any(x in k for x in ["email", "correo"]):
                    email = v
                elif any(x in k for x in ["sexo", "genero", "gender"]):
                    gender = "Masculino" if v.lower().startswith("m") else ("Femenino" if v.lower().startswith("f") else "Otro")
                elif any(x in k for x in ["direccion", "domicilio", "address"]):
                    address = v
                elif any(x in k for x in ["alergia", "allergies"]):
                    allergies = v
                elif any(x in k for x in ["diagnostico", "diagnosis"]):
                    diag = v
                elif any(x in k for x in ["tratamiento", "treatment", "plan"]):
                    trat = v
                elif any(x in k for x in ["motivo", "reason"]):
                    motivo = v
                elif any(x in k for x in ["nota", "historia", "antecedente"]):
                    notes = v

            if not last_name and first_name and " " in first_name:
                first_name, last_name = split_name(first_name)
            elif not first_name and full_name:
                first_name, last_name = split_name(full_name)
            elif not first_name and not full_name and row:
                first_name, last_name = split_name(row[0])
                
            if not first_name:
                continue

            bdate = parse_date(bdate_str)
            consultations = []
            if diag or trat or notes:
                consultations.append({
                    "date": datetime.utcnow().isoformat(),
                    "reason": motivo if motivo else "Consulta importada",
                    "diagnosis": diag if diag else "Diagnóstico clínico",
                    "treatment": trat if trat else None,
                    "notes": notes if notes else None,
                    "doctor_name": None
                })
                
            patient_records.append({
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}".strip(),
                "document_id": doc_id if doc_id else None,
                "date_of_birth": bdate.isoformat() if bdate else None,
                "gender": gender,
                "phone": phone if phone else None,
                "email": email if email else None,
                "address": address if address else None,
                "allergies": allergies if allergies else None,
                "blood_type": None,
                "notes": notes if notes else "Importado desde archivo",
                "consultations": consultations
            })
            
        return patient_records

    @classmethod
    def parse_excel(cls, file_path: str) -> List[Dict[str, Any]]:
        """
        Parses Microsoft Excel (.xlsx) files.
        """
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        if not sheet:
            return []
            
        rows_iter = sheet.iter_rows(values_only=True)
        headers_raw = next(rows_iter, None)
        if not headers_raw:
            return []
            
        headers = [clean_utf8(h).lower() for h in headers_raw]
        patient_records: List[Dict[str, Any]] = []
        
        for row in rows_iter:
            if not row or not any(row):
                continue
            row_dict = {}
            for idx, h in enumerate(headers):
                if idx < len(row):
                    row_dict[h] = row[idx]
                    
            full_name = clean_utf8(row_dict.get("nombre completo") or row_dict.get("paciente") or "")
            first_name = clean_utf8(row_dict.get("nombre") or "")
            last_name = clean_utf8(row_dict.get("apellido") or "")
            doc_id = clean_utf8(row_dict.get("cedula") or row_dict.get("dni") or row_dict.get("documento") or "")
            bdate_val = row_dict.get("fecha de nacimiento") or row_dict.get("nacimiento") or row_dict.get("fecha_nac")
            bdate = parse_date(bdate_val)
            phone = clean_utf8(row_dict.get("telefono") or row_dict.get("celular") or "")
            email = clean_utf8(row_dict.get("email") or row_dict.get("correo") or "")
            gender_val = clean_utf8(row_dict.get("sexo") or row_dict.get("genero") or "")
            gender = "Masculino" if gender_val.lower().startswith("m") else ("Femenino" if gender_val.lower().startswith("f") else "Otro")
            address = clean_utf8(row_dict.get("direccion") or "")
            allergies = clean_utf8(row_dict.get("alergias") or "")
            notes = clean_utf8(row_dict.get("notas") or row_dict.get("observaciones") or "")
            diag = clean_utf8(row_dict.get("diagnostico") or "")
            trat = clean_utf8(row_dict.get("tratamiento") or "")

            if not first_name and full_name:
                first_name, last_name = split_name(full_name)
            elif not first_name and not full_name and row[0]:
                first_name, last_name = split_name(str(row[0]))
                
            if not first_name:
                continue

            consultations = []
            if diag or trat:
                consultations.append({
                    "date": datetime.utcnow().isoformat(),
                    "reason": "Consulta importada de Excel",
                    "diagnosis": diag if diag else "Evaluación clínica",
                    "treatment": trat if trat else None,
                    "notes": notes if notes else None,
                    "doctor_name": None
                })
                
            patient_records.append({
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}".strip(),
                "document_id": doc_id if doc_id else None,
                "date_of_birth": bdate.isoformat() if bdate else None,
                "gender": gender,
                "phone": phone if phone else None,
                "email": email if email else None,
                "address": address if address else None,
                "allergies": allergies if allergies else None,
                "blood_type": None,
                "notes": notes if notes else "Importado desde Excel",
                "consultations": consultations
            })
            
        return patient_records

    @classmethod
    def preview_data(cls, patients_data: List[Dict[str, Any]], db: Session) -> Dict[str, Any]:
        """
        Cross-references raw parsed records with current database to identify duplicates and stats.
        """
        existing_docs = {
            p.document_id: p for p in db.query(Patient).filter(Patient.document_id.isnot(None)).all()
        }
        existing_names = {
            f"{p.first_name.strip().lower()} {p.last_name.strip().lower()}": p for p in db.query(Patient).all()
        }

        total_patients = len(patients_data)
        total_consultations = sum(len(p.get("consultations", [])) for p in patients_data)
        new_count = 0
        existing_count = 0

        annotated_preview = []
        for idx, item in enumerate(patients_data):
            doc = item.get("document_id")
            name_key = f"{item.get('first_name', '').strip().lower()} {item.get('last_name', '').strip().lower()}"
            
            is_duplicate = False
            matched_patient_id = None
            if doc and doc in existing_docs:
                is_duplicate = True
                matched_patient_id = existing_docs[doc].id
            elif name_key in existing_names:
                is_duplicate = True
                matched_patient_id = existing_names[name_key].id
                
            if is_duplicate:
                existing_count += 1
                status = "Existente (Se actualizará)"
            else:
                new_count += 1
                status = "Nuevo Paciente"
                
            item["is_duplicate"] = is_duplicate
            item["matched_patient_id"] = matched_patient_id
            item["status_label"] = status
            
            if idx < 15:
                annotated_preview.append(item)

        return {
            "success": True,
            "total_patients": total_patients,
            "new_patients": new_count,
            "existing_patients": existing_count,
            "total_consultations": total_consultations,
            "preview_sample": annotated_preview,
            "all_records": patients_data
        }

    @classmethod
    def execute_import(cls, patients_data: List[Dict[str, Any]], db: Session, doctor_id: int) -> Dict[str, Any]:
        """
        Executes database insertion and updates in a safe transaction.
        """
        imported_patients = 0
        updated_patients = 0
        imported_consultations = 0

        try:
            for item in patients_data:
                first_name = clean_utf8(item.get("first_name"))
                last_name = clean_utf8(item.get("last_name"))
                if not first_name:
                    continue

                doc_id = clean_utf8(item.get("document_id")) or None
                bdate = parse_date(item.get("date_of_birth"))
                gender = clean_utf8(item.get("gender")) or "Otro"
                phone = clean_utf8(item.get("phone")) or None
                email = clean_utf8(item.get("email")) or None
                address = clean_utf8(item.get("address")) or None
                allergies = clean_utf8(item.get("allergies")) or None
                notes = clean_utf8(item.get("notes")) or None

                patient = None
                if doc_id:
                    patient = db.query(Patient).filter(Patient.document_id == doc_id).first()
                if not patient:
                    patient = db.query(Patient).filter(
                        Patient.first_name == first_name,
                        Patient.last_name == last_name
                    ).first()

                if patient:
                    # Update existing
                    if bdate: patient.date_of_birth = bdate
                    if gender: patient.gender = gender
                    if phone: patient.phone = phone
                    if email: patient.email = email
                    if address: patient.address = address
                    if allergies: patient.allergies = allergies
                    updated_patients += 1
                else:
                    # Create new
                    patient = Patient(
                        first_name=first_name,
                        last_name=last_name,
                        document_id=doc_id,
                        date_of_birth=bdate,
                        gender=gender,
                        phone=phone,
                        email=email,
                        address=address,
                        allergies=allergies,
                        blood_type=clean_utf8(item.get("blood_type")) or None,
                        sede_origen="import_consulta_practica"
                    )
                    db.add(patient)
                    db.flush() # assign patient.id
                    imported_patients += 1

                # Import consultations
                consultations = item.get("consultations", [])
                for c in consultations:
                    c_dt_str = c.get("date")
                    c_dt = datetime.fromisoformat(c_dt_str) if c_dt_str else datetime.utcnow()
                    
                    hist_notes = clean_utf8(c.get("notes")) or None
                    symptoms_val = clean_utf8(c.get("symptoms"))
                    if not symptoms_val or symptoms_val == "Importado de historia clínica anterior":
                        if hist_notes and hist_notes.lower() not in ["no recabada", "none", ""]:
                            symptoms_val = hist_notes
                        else:
                            symptoms_val = "Consulta histórica sin descripción de síntomas registrada en el sistema anterior."

                    consult = Consultation(
                        patient_id=patient.id,
                        doctor_id=doctor_id,
                        reason=clean_utf8(c.get("reason")) or "Consulta Médica / Chequeo Clínico",
                        symptoms=symptoms_val,
                        diagnosis=clean_utf8(c.get("diagnosis")) or "Sin diagnóstico especificado",
                        treatment=clean_utf8(c.get("treatment")) or None,
                        notes=hist_notes,
                        sede_origen="import_consulta_practica",
                        created_at=c_dt
                    )
                    db.add(consult)
                    imported_consultations += 1

            # Register clinical audit log
            audit = ClinicalAuditLog(
                entity_type="import",
                entity_id=doctor_id,
                action="create",
                summary=f"Importación masiva de Consulta Práctica: {imported_patients} nuevos, {updated_patients} actualizados, {imported_consultations} consultas.",
                user_id=doctor_id
            )
            db.add(audit)

            db.commit()
            return {
                "success": True,
                "imported_patients": imported_patients,
                "updated_patients": updated_patients,
                "imported_consultations": imported_consultations,
                "message": f"¡Importación exitosa! Se importaron {imported_patients} pacientes nuevos, se actualizaron {updated_patients} existentes y se incorporaron {imported_consultations} consultas médicas al historial."
            }
        except Exception as e:
            db.rollback()
            raise e
