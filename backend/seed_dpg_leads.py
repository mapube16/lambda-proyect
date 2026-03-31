"""
Seed demo leads for dpgseguros@gmail.com
Run: python seed_dpg_leads.py
"""
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

LEADS = [
    {
        "company_name": "Constructora Bolívar SAS",
        "url": "https://constructorabolivar.com",
        "phone": "+57 601 3456789",
        "address": "Cra 7 # 32-45, Bogotá",
        "score": 91,
        "puntaje": 91,
        "system_state": "SUCCESS_READY_FOR_REVIEW",
        "estado": "CHECKPOINT",
        "decisor": {"nombre": "Carlos Méndez", "cargo": "Gerente General"},
        "criterios": ["Flota de 12 volquetas propias", "Contrato activo con IDU por $8.000M", "Sin póliza de responsabilidad civil vigente"],
        "senales_intencion": ["Ampliación de flota en Q1", "Nuevo contrato en licitación", "Gerente buscando correduría"],
        "canales": [{"canal": "email", "probabilidad": 75}, {"canal": "whatsapp", "probabilidad": 85}, {"canal": "linkedin", "probabilidad": 60}],
        "recomendacion_agente": "Alta prioridad. Contrato con IDU activo exige póliza de cumplimiento. Ventana de oportunidad abierta.",
        "expediente_markdown": "## Constructora Bolívar SAS\n\n**Sector:** Construcción\n**Ciudad:** Bogotá\n**Empleados:** ~80\n\n### Por qué es un buen prospecto\nEmpresa con contrato activo de $8.000M con el IDU para obra vial en la Calle 80. Tienen flota propia de 12 volquetas y no tienen correduría de seguros formal. El gerente Carlos Méndez está en proceso de buscar opciones para cumplir requisitos del contrato.\n\n### Cobertura sugerida\n- Póliza de cumplimiento (obligatoria IDU)\n- Todo riesgo de contratista\n- RC extracontractual\n- Seguro de flota",
        "expediente_json": {"score": 91, "sector": "construccion", "ciudad": "Bogotá", "empleados": 80},
        "historial_conversacion": [],
    },
    {
        "company_name": "Transportes Rápido Tolima Ltda",
        "url": "https://rapidotolima.com.co",
        "phone": "+57 8 2612345",
        "address": "Av. Ferrocarril # 5-23, Ibagué",
        "score": 87,
        "puntaje": 87,
        "system_state": "SUCCESS_READY_FOR_REVIEW",
        "estado": "CHECKPOINT",
        "decisor": {"nombre": "Adriana Vargas", "cargo": "Directora Administrativa"},
        "criterios": ["Flota de 34 camiones de carga pesada", "Operación intermunicipal activa", "Renovación de póliza en abril"],
        "senales_intencion": ["Póliza actual vence en 30 días", "Buscando mejores tarifas", "Accidente reciente sin cobertura suficiente"],
        "canales": [{"canal": "whatsapp", "probabilidad": 90}, {"canal": "email", "probabilidad": 70}],
        "recomendacion_agente": "Urgente. Póliza vence pronto y tienen siniestro reciente. Momento ideal para entrar con propuesta competitiva.",
        "expediente_markdown": "## Transportes Rápido Tolima Ltda\n\n**Sector:** Transporte de carga\n**Ciudad:** Ibagué\n**Empleados:** ~45\n\n### Por qué es un buen prospecto\nTransportadora con 34 camiones en ruta Bogotá-Medellín-Cali. Póliza actual con AXA vence el 15 de abril. Tuvieron un accidente en enero con carga de electrodomésticos que superó la cobertura. Adriana Vargas está activamente cotizando.\n\n### Cobertura sugerida\n- SOAT + seguro de carga\n- RC por transporte de mercancías\n- Pérdida total de vehículos\n- Accidentes de tránsito",
        "expediente_json": {"score": 87, "sector": "transporte", "ciudad": "Ibagué", "empleados": 45},
        "historial_conversacion": [],
    },
    {
        "company_name": "Frigorífico del Llano SAS",
        "url": "https://frigorificodellano.com",
        "phone": "+57 8 6623456",
        "address": "Km 3 Vía Puerto López, Villavicencio",
        "score": 83,
        "puntaje": 83,
        "system_state": "SUCCESS_READY_FOR_REVIEW",
        "estado": "CHECKPOINT",
        "decisor": {"nombre": "Jorge Ospina", "cargo": "Gerente Financiero"},
        "criterios": ["Planta con $12B en activos físicos", "Proceso de certificación INVIMA", "Sin seguro de interrupción de negocio"],
        "senales_intencion": ["Ampliación de cuartos fríos en curso", "Exportaciones iniciando a Venezuela", "Auditoría de riesgos programada"],
        "canales": [{"canal": "email", "probabilidad": 80}, {"canal": "linkedin", "probabilidad": 65}],
        "recomendacion_agente": "Prospecto sólido. Activos sin cobertura adecuada. La expansión los expone más. Entrada por auditoría de riesgos.",
        "expediente_markdown": "## Frigorífico del Llano SAS\n\n**Sector:** Agroindustria / Manufactura frigorífica\n**Ciudad:** Villavicencio\n**Empleados:** ~110\n\n### Por qué es un buen prospecto\nFrigorífico con planta de sacrificio y procesamiento. $12B en maquinaria y cámaras frías. No tienen seguro de interrupción de negocio, lo que los deja expuestos ante fallas eléctricas o averías de compresores. Iniciando exportación a Venezuela exige cobertura internacional.\n\n### Cobertura sugerida\n- Todo riesgo industrial\n- Interrupción de negocio\n- Responsabilidad de producto\n- Cobertura de exportación",
        "expediente_json": {"score": 83, "sector": "agroindustria", "ciudad": "Villavicencio", "empleados": 110},
        "historial_conversacion": [],
    },
    {
        "company_name": "Clínica Especializada Santa Rosa",
        "url": "https://clinicasantarosa.com.co",
        "phone": "+57 4 3789012",
        "address": "Cl 50 # 40-12, Medellín",
        "score": 88,
        "puntaje": 88,
        "system_state": "SUCCESS_READY_FOR_REVIEW",
        "estado": "CHECKPOINT",
        "decisor": {"nombre": "Dra. Lucía Henao", "cargo": "Directora Médica"},
        "criterios": ["50 camas habilitadas", "Glosa de EPS por $800M en disputa", "RC médica vencida desde diciembre"],
        "senales_intencion": ["Demanda de paciente en curso", "Proceso de acreditación ICONTEC", "Búsqueda activa de corredora"],
        "canales": [{"canal": "linkedin", "probabilidad": 78}, {"canal": "email", "probabilidad": 82}],
        "recomendacion_agente": "Alta urgencia. RC médica vencida con demanda activa. Necesitan cobertura inmediata. Entrada por el área jurídica.",
        "expediente_markdown": "## Clínica Especializada Santa Rosa\n\n**Sector:** Salud\n**Ciudad:** Medellín\n**Empleados:** ~120\n\n### Por qué es un buen prospecto\nClínica de segundo nivel con servicios de cirugía y urgencias. Tienen RC médica vencida desde diciembre y una demanda de paciente por complicación quirúrgica activa. Dra. Henao está buscando corredora urgente antes de la audiencia de conciliación en mayo.\n\n### Cobertura sugerida\n- RC médica (urgente)\n- Todo riesgo hospitalario\n- Pérdida de documentos clínicos\n- Directores y administradores",
        "expediente_json": {"score": 88, "sector": "salud", "ciudad": "Medellín", "empleados": 120},
        "historial_conversacion": [],
    },
    {
        "company_name": "Ferretería Industrial Colmena SAS",
        "url": "https://ferreteriaindustrialcolmena.com",
        "phone": "+57 2 8834567",
        "address": "Zona Industrial, Cali",
        "score": 76,
        "puntaje": 76,
        "system_state": "SUCCESS_READY_FOR_REVIEW",
        "estado": "APROBADO",
        "hitl_status": "approved",
        "decisor": {"nombre": "Ramiro Castaño", "cargo": "Socio Gerente"},
        "criterios": ["Bodega propia de 2.400 m²", "Inventario promedio de $4B", "Distribuidor exclusivo de 3 marcas industriales"],
        "senales_intencion": ["Robo parcial en enero sin cobertura suficiente", "Ampliando portafolio de crédito con Bancolombia", "Buscando póliza todo riesgo"],
        "canales": [{"canal": "whatsapp", "probabilidad": 88}, {"canal": "email", "probabilidad": 72}],
        "recomendacion_agente": "Lead aprobado. Tuvieron robo y no tenían cobertura de inventario. Motivación alta.",
        "expediente_markdown": "## Ferretería Industrial Colmena SAS\n\n**Sector:** Retail con inventario / Distribución industrial\n**Ciudad:** Cali\n**Empleados:** ~25\n\n### Por qué es un buen prospecto\nFerretería distribuidora mayorista. Bodega de 2.400m² con inventario promedio de $4B en herramientas y materiales industriales. En enero tuvieron un robo que les costó $180M sin cobertura completa. Ramiro está activamente buscando póliza antes de renovar crédito con Bancolombia.\n\n### Cobertura sugerida\n- Todo riesgo comercio\n- Hurto e infidelidad de empleados\n- RC de producto\n- Lucro cesante",
        "expediente_json": {"score": 76, "sector": "retail", "ciudad": "Cali", "empleados": 25},
        "historial_conversacion": [],
    },
]


async def main():
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient
    from bson import ObjectId

    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "hive_office")
    client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db = client[db_name]

    # Get DPG user
    user = await db.users.find_one({"email": "dpgseguros@gmail.com"})
    if not user:
        print("ERROR: dpgseguros@gmail.com not found in DB")
        return

    user_id = str(user["_id"])
    print(f"Found user: {user_id}")

    # Create a dummy run
    run_result = await db.runs.insert_one({
        "user_id": user_id,
        "campaign_id": "",
        "status": "complete",
        "max_results": len(LEADS),
        "started_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
    })
    run_id = str(run_result.inserted_id)
    print(f"Created run: {run_id}")

    # Insert leads
    count = 0
    for lead in LEADS:
        hitl_status = lead.pop("hitl_status", "pending")
        await db.leads.insert_one({
            "run_id": run_id,
            "user_id": user_id,
            "company_name": lead.get("company_name", ""),
            "url": lead.get("url", ""),
            "phone": lead.get("phone", ""),
            "address": lead.get("address", ""),
            "score": lead.get("score"),
            "system_state": lead.get("system_state", "SUCCESS_READY_FOR_REVIEW"),
            "expediente_markdown": lead.get("expediente_markdown"),
            "expediente_json": lead.get("expediente_json", {}),
            "hitl_status": hitl_status,
            "hitl_at": None,
            "created_at": datetime.now(timezone.utc),
            "estado": lead.get("estado"),
            "decisor": lead.get("decisor"),
            "canales": lead.get("canales"),
            "canal_elegido": None,
            "puntaje": lead.get("puntaje"),
            "criterios": lead.get("criterios", []),
            "senales_intencion": lead.get("senales_intencion", []),
            "recomendacion_agente": lead.get("recomendacion_agente"),
            "motivo_nurturing": None,
            "intento_actual": 1,
            "fecha_entrada_nurturing": None,
            "ciclo_nurturing": 0,
            "historial_conversacion": [],
        })
        count += 1
        print(f"  OK {lead['company_name']}")

    print(f"\nDone! {count} leads seeded for dpgseguros@gmail.com")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
