"""
Script de seed manual — NO es parte de la app final.
Crea los casos de prueba de esta demo directo por API REST,
evitando restricciones de Page Layout (que solo aplican a la UI).

Se ejecuta parado en la raíz del proyecto con:
    python seed_test_cases.py
"""

import asyncio

from config.settings import get_settings
from infrastructure.salesforce_client import SalesforceClient

TEST_CASES = [
    {"Subject": "Reclamo por producto dañado", "Branch__c": "Sucursal Centro", "Status": "New"},
    {"Subject": "Consulta de stock disponible", "Branch__c": "Sucursal Norte", "Status": "New"},
    {"Subject": "Solicitud de cambio de producto", "Branch__c": "Sucursal Centro", "Status": "New"},
    {"Subject": "Reintegro por compra online", "Branch__c": "Sucursal Sur", "Status": "New"},
    {"Subject": "Consulta por garantía extendida", "Branch__c": "Sucursal Norte", "Status": "New"},
]


async def main():
    client = SalesforceClient(get_settings().salesforce)
    for case_fields in TEST_CASES:
        case_id = await client.create_sobject("Case", case_fields)
        print(f"Creado: {case_id} — {case_fields['Subject']}")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())