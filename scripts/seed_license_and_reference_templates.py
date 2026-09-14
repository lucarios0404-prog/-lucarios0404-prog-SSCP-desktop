import sys
from pathlib import Path

# Añadir raíz de sscp-desktop al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import SessionLocal
from app.models.template import ClinicalTemplate
from app.models.user import User

def seed_templates():
    db = SessionLocal()
    try:
        admin_user = db.query(User).first()
        doctor_id = admin_user.id if admin_user else None

        templates_to_seed = [
            # ===================== LICENCIAS MÉDICAS (REPOSO) =====================
            {
                "category": "license",
                "title": "Reposo Laboral / Escolar Estándar (3 Días)",
                "content": (
                    "Diagnóstico: Trastorno Funcional Agudo / Causa Médica Incapacitante Temporal\n"
                    "Días de Reposo: 3\n"
                    "Dirigido a: A quien pueda interesar\n"
                    "Indicaciones: Se certifica que el/la paciente amerita reposo médico domiciliario y abstención de actividades laborales y físicas por 3 días. Cumplir tratamiento médico pautado, reposo relativo en cama e hidratación adecuada. Reevaluación en consulta si los síntomas persisten."
                ),
            },
            {
                "category": "license",
                "title": "Síndrome Gripal / Cuadro Respiratorio Agudo (3 Días)",
                "content": (
                    "Diagnóstico: Infección Respiratoria Aguda de Vías Aéreas Superiores / Síndrome Gripal\n"
                    "Días de Reposo: 3\n"
                    "Dirigido a: Departamento de Gestión Humana / Institución Educativa\n"
                    "Indicaciones: Reposo médico estricto en domicilio con aislamiento preventivo durante 3 días. Mantener hidratación oral constante, reposo en cama y cumplimiento de pauta analgésica/antipirética prescrita. Reevaluar en caso de disnea o fiebre mantenida."
                ),
            },
            {
                "category": "license",
                "title": "Lumbalgia Aguda Mecánica / Mialgia Severa (4 Días)",
                "content": (
                    "Diagnóstico: Lumbalgia Aguda Mecánica / Contractura Muscular Paravertebral\n"
                    "Días de Reposo: 4\n"
                    "Dirigido a: Gestión Humana / Empresa Empleadora\n"
                    "Indicaciones: Reposo físico relativo en cama en posición antálgica por 4 días. Evitar carga de peso, flexo-extensiones de tronco y bipedestación prolongada. Aplicar calor local seco y administrar medicación analgésica y miorrelajante."
                ),
            },
            {
                "category": "license",
                "title": "Gastroenteritis Aguda / Cuadro Gastrointestinal (2 Días)",
                "content": (
                    "Diagnóstico: Gastroenteritis Aguda Infecciosa / Trastorno Gastrointestinal Agudo\n"
                    "Días de Reposo: 2\n"
                    "Dirigido a: A quien pueda interesar\n"
                    "Indicaciones: Reposo domiciliario por 48 horas. Dieta blanda astringente, libre de grasas y lácteos. Hidratación constante con sales de rehidratación oral (SRO) a libre demanda. Reincorporación condicionada a tolerancia oral y cese de evacuaciones líquidas."
                ),
            },
            {
                "category": "license",
                "title": "Post-Procedimiento Clínico / Reposo Menor (5 Días)",
                "content": (
                    "Diagnóstico: Estado Post-Procedimiento Clínico Ambulatorio Menor\n"
                    "Días de Reposo: 5\n"
                    "Dirigido a: A quien pueda interesar\n"
                    "Indicaciones: Reposo absoluto las primeras 48 horas y reposo relativo hasta completar 5 días. Mantener zona de herida limpia y seca, evitar esfuerzos físicos o movimientos bruscos. Acudir a cita de control programada para seguimiento y retiro de suturas."
                ),
            },

            # ===================== REFERENCIAS MÉDICAS (INTERCONSULTA) =====================
            {
                "category": "reference",
                "title": "Interconsulta a Cardiología (Evaluación Cardiovascular)",
                "content": (
                    "Especialidad: Especialista en Cardiología\n"
                    "Institución: Centro Cardiovascular / Departamento de Cardiología\n"
                    "Motivo: Evaluación de cifras tensionales elevadas y estratificación de riesgo cardiovascular\n"
                    "Resumen Clínico: Paciente en seguimiento clínico que presenta cifras tensionales elevadas fuera de meta terapéutica y sintomatología compatible. Se refiere a su distinguido servicio para valoración especializada, realización de electrocardiograma (ECG), ecocardiograma transtorácico y optimización de terapia antihipertensiva.\n"
                    "Notas: Se anexan últimos registros de signos vitales, analíticas de laboratorio recientes y antecedentes patológicos relevantes."
                ),
            },
            {
                "category": "reference",
                "title": "Interconsulta a Cirugía General (Valoración Quirúrgica)",
                "content": (
                    "Especialidad: Servicio de Cirugía General\n"
                    "Institución: Hospital / Centro Quirúrgico Especializado\n"
                    "Motivo: Evaluación de masa o cuadro doloroso localizado con posible resolución quirúrgica\n"
                    "Resumen Clínico: Paciente que consulta por cuadro sintomático focalizado con evolución progresiva y hallazgos al examen físico sugestivos de patología quirúrgica. Se deriva a su servicio para valoración integral por especialista y determinación de conducta resolutiva.\n"
                    "Notas: Se adjuntan estudios de imágenes y analíticas preoperatorias básicas practicadas en nuestro centro."
                ),
            },
            {
                "category": "reference",
                "title": "Interconsulta a Oftalmología (Agudeza Visual y Fondo de Ojo)",
                "content": (
                    "Especialidad: Dr(a). Especialista en Oftalmología\n"
                    "Institución: Clínica Oftalmológica / Centro de la Visión\n"
                    "Motivo: Disminución progresiva de agudeza visual y control de fondo de ojo\n"
                    "Resumen Clínico: Paciente en seguimiento médico general que relata pérdida subjetiva de visión, cefaleas o astenopía. Se refiere para examen oftalmológico integral, agudeza visual con refracción, biomicroscopía y evaluación de fondo de ojo.\n"
                    "Notas: Se adjunta historial clínico de enfermedades metabólicas y tratamiento actual."
                ),
            },
            {
                "category": "reference",
                "title": "Interconsulta a Medicina Interna (Manejo Multidisciplinario)",
                "content": (
                    "Especialidad: Especialista en Medicina Interna\n"
                    "Institución: Departamento de Medicina Interna / Consulta Especializada\n"
                    "Motivo: Evaluación de patología médica compleja y ajuste terapéutico integral\n"
                    "Resumen Clínico: Paciente que amerita abordaje integral por Medicina Interna debido a coexistencia de múltiples comorbilidades y síntomas persistentes. Se solicita interconsulta para reevaluación diagnóstica, conciliación farmacológica y seguimiento conjunto.\n"
                    "Notas: Se remite con resumen de consultas previas y reporte de analíticas complementarias."
                ),
            },
            {
                "category": "reference",
                "title": "Interconsulta a Ginecología y Obstetricia (Control Integral)",
                "content": (
                    "Especialidad: Especialista en Ginecología y Obstetricia\n"
                    "Institución: Centro de Atención a la Mujer / Consulta Ginecológica\n"
                    "Motivo: Control ginecológico especializado y correlación diagnóstica\n"
                    "Resumen Clínico: Paciente femenina referida para valoración ginecológica exhaustiva, tamizaje preventivo y correlación clínica de sintomatología pélvica o menstrual referida en consulta.\n"
                    "Notas: Se adjuntan antecedentes gineco-obstétricos y estudios analíticos preliminares."
                ),
            },
        ]

        print("Verificando y sembrando plantillas para Licencias y Referencias...")
        added_count = 0
        for tpl_data in templates_to_seed:
            exists = db.query(ClinicalTemplate).filter(
                ClinicalTemplate.category == tpl_data["category"],
                ClinicalTemplate.title == tpl_data["title"]
            ).first()
            if not exists:
                tpl = ClinicalTemplate(
                    doctor_id=doctor_id,
                    category=tpl_data["category"],
                    title=tpl_data["title"],
                    content=tpl_data["content"],
                    is_global=True
                )
                db.add(tpl)
                added_count += 1
                print(f"  + Sembrada: [{tpl_data['category'].upper()}] {tpl_data['title']}")
            else:
                print(f"  = Ya existe: [{tpl_data['category'].upper()}] {tpl_data['title']}")

        db.commit()
        print(f"\nProceso finalizado. Se agregaron {added_count} nuevas plantillas clínicas.")

    finally:
        db.close()

if __name__ == "__main__":
    seed_templates()
