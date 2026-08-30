"""
Script de prueba manual — NO es parte de la app final.
Verifica que CaseRepository traduce bien entre Salesforce y domain.Case.

Se ejecuta parado en la raíz del proyecto con:
    python test_repository.py
"""

import asyncio

from config.settings import get_settings
from infrastructure.case_repository import CaseRepository
from infrastructure.salesforce_client import SalesforceClient


async def main():
    client = SalesforceClient(get_settings().salesforce)
    repo = CaseRepository(client)

    cases = await repo.list_cases_for_branch("Sucursal Centro")
    print(f"Casos encontrados para 'Sucursal Centro': {len(cases)}\n")
    for c in cases:
        print(f"{c.case_number} | {c.status.value} | {c.branch} | {c.subject}")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())