"""
Caso de uso vinculado al webhook de creación de canal.

El canal en sí ya lo crea Salesforce (action nativa "Create a Salesforce
Channel in Slack"), y el Asunto/Descripción del caso ya se ven directo
en el modal "Gestionar" — por eso ya no hace falta postear ningún
mensaje al crear el canal. Se mantiene este método (y el webhook que lo
llama en main.py) por si en el futuro hace falta hacer algo en este
punto del flujo.
"""

from domain.case import Case
from infrastructure.case_repository import CaseRepository
from infrastructure.slack_client import SlackClient


class CaseChannelService:
    def __init__(self, repository: CaseRepository, slack_client: SlackClient):
        self._repository = repository
        self._slack_client = slack_client

    async def post_initial_message(self, case_id: str, channel_id: str) -> Case:
        """No postea nada — ver docstring del módulo."""
        return await self._repository.get_case(case_id)