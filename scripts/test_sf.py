"""
Script de prueba manual — NO es parte de la app final.
Sirve solo para confirmar que la conexión a Salesforce funciona
antes de seguir construyendo el resto del código.

Se ejecuta parado en la raíz del proyecto con:
    python test_sf.py
"""

import asyncio

from config.settings import get_settings
from infrastructure.salesforce_client import SalesforceClient


async def main():
    client = SalesforceClient(get_settings().salesforce)
    result = await client.query(
        "SELECT Id, CaseNumber, Subject, Status, Branch__c, Internal_Team__c "
        "FROM Case WHERE Branch__c != null"
    )
    print(f"Total de casos encontrados: {result['totalSize']}\n")
    for record in result["records"]:
        print(record)
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())