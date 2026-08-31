"""
Casos de uso de Case: orquestan el modelo de dominio (que valida las
transiciones) y el repositorio (que persiste en Salesforce). Esta es
la capa que va a llamar directamente el código de Slack — nunca debería
necesitar tocar `infrastructure/` ni `domain/` por separado.
"""

from domain.case import Case
from infrastructure.case_repository import CaseRepository


class CaseService:
    def __init__(self, repository: CaseRepository):
        self._repository = repository

    async def list_cases_for_branch(self, branch: str) -> list[Case]:
        """Casos visibles en el App Home de una sucursal."""
        return await self._repository.list_cases_for_branch(branch)

    async def list_all_cases(self) -> list[Case]:
        """Casos visibles para un superuser (todas las sucursales)."""
        return await self._repository.list_all_cases()

    async def list_cases_for_team(self, team: str) -> list[Case]:
        """Casos visibles para alguien que sigue a un equipo interno puntual (todas las sucursales)."""
        return await self._repository.list_cases_for_team(team)

    async def get_case(self, case_id: str) -> Case:
        """Detalle de un caso puntual (para abrir el modal)."""
        return await self._repository.get_case(case_id)

    async def start_progress(self, case_id: str) -> Case:
        """La sucursal empieza a trabajar el caso."""
        case = await self._repository.get_case(case_id)
        case.start_progress()
        await self._repository.save(case)
        return case

    async def derive_to_internal_team(self, case_id: str, team: str) -> Case:
        """La sucursal deriva el caso a un equipo interno (Legal, Logistics, etc.)."""
        case = await self._repository.get_case(case_id)
        case.derive_to_internal_team(team)
        await self._repository.save(case)
        return case

    async def return_to_call_center(self, case_id: str) -> Case:
        """La sucursal devuelve el caso a Call Center."""
        case = await self._repository.get_case(case_id)
        case.return_to_call_center()
        await self._repository.save(case)
        return case

    async def close_case(self, case_id: str) -> Case:
        """Cierra el caso."""
        case = await self._repository.get_case(case_id)
        case.close()
        await self._repository.save(case)
        return case

    async def add_comment(self, case_id: str, comment_body: str) -> None:
        """Agrega un comentario al caso en Salesforce (CaseComment)."""
        await self._repository.add_comment(case_id, comment_body)