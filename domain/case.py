"""
Modelo de dominio: Case (Caso).

Esta capa no conoce nada de Slack ni de Salesforce — son entidades y
reglas de negocio puras. La capa de `infrastructure/` se encarga de
traducir esto hacia/desde la API de Salesforce, y `application/` de
orquestar los casos de uso.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    """Estados posibles de un caso a lo largo de su ciclo de vida."""

    NEW = "new"  # Recién creado por Call Center, sin derivar todavía
    ASSIGNED_TO_BRANCH = "assigned_to_branch"  # Derivado a una sucursal
    IN_PROGRESS = "in_progress"  # La sucursal lo está trabajando
    ESCALATED_INTERNAL = "escalated_internal"  # Derivado a un equipo interno de la sucursal
    RETURNED_TO_CALL_CENTER = "returned_to_call_center"  # Devuelto a Call Center
    CLOSED = "closed"  # Resuelto y cerrado


# Transiciones permitidas: desde qué estado se puede pasar a cuáles otros.
_ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.NEW: {CaseStatus.ASSIGNED_TO_BRANCH},
    CaseStatus.ASSIGNED_TO_BRANCH: {
        CaseStatus.IN_PROGRESS,
        CaseStatus.ESCALATED_INTERNAL,
        CaseStatus.RETURNED_TO_CALL_CENTER,
    },
    CaseStatus.IN_PROGRESS: {
        CaseStatus.ESCALATED_INTERNAL,
        CaseStatus.RETURNED_TO_CALL_CENTER,
        CaseStatus.CLOSED,
    },
    CaseStatus.ESCALATED_INTERNAL: {
        CaseStatus.IN_PROGRESS,
        CaseStatus.RETURNED_TO_CALL_CENTER,
        CaseStatus.CLOSED,
    },
    CaseStatus.RETURNED_TO_CALL_CENTER: {CaseStatus.ASSIGNED_TO_BRANCH},
    CaseStatus.CLOSED: set(),  # Estado terminal, no se puede salir de acá
}


class InvalidCaseTransition(Exception):
    """Se intentó mover un caso a un estado no permitido desde su estado actual."""

    def __init__(self, current: CaseStatus, target: CaseStatus):
        self.current = current
        self.target = target
        super().__init__(f"No se puede pasar de '{current.value}' a '{target.value}'.")


class Case(BaseModel):
    """Representa un caso de Salesforce, en su forma de dominio."""

    id: str = Field(..., description="Id interno de Salesforce (Case.Id).")
    case_number: str = Field(..., description="Número visible del caso (Case.CaseNumber).")
    subject: str
    description: str | None = None
    status: CaseStatus
    branch: str = Field(..., description="Sucursal (branch) actualmente responsable del caso.")
    assigned_team: str | None = Field(default=None, description="Equipo interno de la sucursal, si fue derivado internamente.")
    channel: str | None = Field(default=None, description="Id del canal de Slack asociado a este caso (ej. 'C0123ABCDEF').")
    created_at: datetime
    updated_at: datetime

    def _transition_to(self, target: CaseStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidCaseTransition(self.status, target)
        self.status = target

    def assign_to_branch(self, branch: str) -> None:
        """Call Center deriva el caso a una sucursal."""
        self._transition_to(CaseStatus.ASSIGNED_TO_BRANCH)
        self.branch = branch
        self.assigned_team = None

    def start_progress(self) -> None:
        """La sucursal empieza a trabajar el caso (o lo retoma después de una derivación interna)."""
        self._transition_to(CaseStatus.IN_PROGRESS)
        self.assigned_team = None

    def derive_to_internal_team(self, team: str) -> None:
        """La sucursal deriva el caso a un equipo interno."""
        self._transition_to(CaseStatus.ESCALATED_INTERNAL)
        self.assigned_team = team

    def return_to_call_center(self) -> None:
        """La sucursal devuelve el caso a Call Center."""
        self._transition_to(CaseStatus.RETURNED_TO_CALL_CENTER)
        self.assigned_team = None

    def close(self) -> None:
        """Cierra el caso. Es un estado terminal."""
        self._transition_to(CaseStatus.CLOSED)