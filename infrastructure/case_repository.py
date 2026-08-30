"""
Repositorio de Case: traduce entre los registros crudos de Salesforce
y el modelo de dominio `Case`. Es la única capa que conoce los nombres
de campo y los valores de picklist reales de Salesforce — el resto de
la app trabaja siempre con `domain.Case`, nunca con dicts crudos.
"""

from datetime import datetime

from domain.case import Case, CaseStatus
from infrastructure.salesforce_client import SalesforceClient

# Mapeo entre nuestro CaseStatus y el valor real que devuelve el picklist
# Status de Salesforce por API.
#
# OJO con esto: para los dos valores que agregamos nosotros (Assigned to
# Branch / Returned to Call Center), el valor que Salesforce devuelve por
# API es el "API Name" tal cual se tipeó al crearlos — SIN espacios (ej.
# "AssignedToBranch") — no el label que se ve en pantalla ("Assigned to
# Branch"). Los 4 valores originales sí coinciden label = API Name porque
# fueron renombrados así previamente.
_STATUS_TO_SALESFORCE: dict[CaseStatus, str] = {
    CaseStatus.NEW: "New",
    CaseStatus.ASSIGNED_TO_BRANCH: "AssignedToBranch",
    CaseStatus.IN_PROGRESS: "In Progress",
    CaseStatus.ESCALATED_INTERNAL: "Escalated",
    CaseStatus.RETURNED_TO_CALL_CENTER: "ReturnedToCallCenter",
    CaseStatus.CLOSED: "Closed",
}
_SALESFORCE_TO_STATUS: dict[str, CaseStatus] = {v: k for k, v in _STATUS_TO_SALESFORCE.items()}

_QUERY_FIELDS = (
    "Id, CaseNumber, Subject, Description, Status, "
    "Branch__c, Internal_Team__c, CreatedDate, LastModifiedDate"
)


def _parse_salesforce_datetime(value: str) -> datetime:
    """Salesforce devuelve fechas tipo '2026-08-29T10:15:30.000+0000'."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")


def _escape_soql_string(value: str) -> str:
    """Escapa comillas simples y backslashes antes de interpolar en un SOQL."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class CaseRepository:
    """Traduce Case (dominio) <-> registros de Salesforce, vía SalesforceClient."""

    def __init__(self, client: SalesforceClient):
        self._client = client

    def _to_domain(self, record: dict) -> Case:
        salesforce_status = record["Status"]
        if salesforce_status not in _SALESFORCE_TO_STATUS:
            raise ValueError(
                f"Valor de Status desconocido en Salesforce: '{salesforce_status}' "
                f"(caso {record.get('CaseNumber')}). Revisar el mapeo en case_repository.py."
            )
        return Case(
            id=record["Id"],
            case_number=record["CaseNumber"],
            subject=record["Subject"],
            description=record.get("Description"),
            status=_SALESFORCE_TO_STATUS[salesforce_status],
            branch=record.get("Branch__c") or "",
            assigned_team=record.get("Internal_Team__c"),
            created_at=_parse_salesforce_datetime(record["CreatedDate"]),
            updated_at=_parse_salesforce_datetime(record["LastModifiedDate"]),
        )

    async def get_case(self, case_id: str) -> Case:
        """Trae un caso puntual por Id."""
        record = await self._client.get_sobject("Case", case_id)
        return self._to_domain(record)

    async def list_cases_for_branch(self, branch: str) -> list[Case]:
        """Trae todos los casos de una sucursal puntual (lo que ve el usuario en el App Home)."""
        soql = (
            f"SELECT {_QUERY_FIELDS} FROM Case "
            f"WHERE Branch__c = '{_escape_soql_string(branch)}' "
            f"ORDER BY CreatedDate DESC"
        )
        result = await self._client.query(soql)
        return [self._to_domain(record) for record in result["records"]]

    async def list_all_cases(self) -> list[Case]:
        """
        Trae todos los casos de la demo (de cualquier sucursal) — para el
        superuser. Sigue filtrando por Branch__c != null para no traer
        casos de otras demos ajenas a este proyecto.
        """
        soql = f"SELECT {_QUERY_FIELDS} FROM Case WHERE Branch__c != null ORDER BY CreatedDate DESC"
        result = await self._client.query(soql)
        return [self._to_domain(record) for record in result["records"]]

    async def save(self, case: Case) -> None:
        """
        Persiste el estado actual del Case en Salesforce.
        No valida transiciones — eso ya lo hizo `domain.Case` antes de llegar acá
        (ver assign_to_branch, derive_to_internal_team, etc.).
        """
        await self._client.update_sobject(
            "Case",
            case.id,
            {
                "Status": _STATUS_TO_SALESFORCE[case.status],
                "Branch__c": case.branch,
                "Internal_Team__c": case.assigned_team,
            },
        )