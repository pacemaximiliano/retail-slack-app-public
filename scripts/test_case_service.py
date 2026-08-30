"""
Script de prueba manual — NO es parte de la app final.
Verifica que CaseService orquesta bien domain + repository.

Se ejecuta parado en la RAÍZ del proyecto (no dentro de /scripts) con:
    python -m scripts.test_case_service
"""

import asyncio

from application.case_service import CaseService
from config.settings import get_settings
from infrastructure.case_repository import CaseRepository
from infrastructure.salesforce_client import SalesforceClient


async def main():
    client = SalesforceClient(get_settings().salesforce)
    service = CaseService(CaseRepository(client))

    cases = await service.list_cases_for_branch("Sucursal Centro")
    case = cases[0]
    print("Antes:", case.status)

    updated = await service.start_progress(case.id)
    print("Después:", updated.status)

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())