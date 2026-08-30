"""
Caso de uso: crear el canal de Slack asociado a un caso.

Orquesta CaseRepository (Salesforce) y SlackClient (Slack) — es el único
lugar de la app que conoce a los dos al mismo tiempo. Se dispara desde
el webhook que recibe el aviso de Salesforce cuando un caso pasa a
"Assigned to Branch" (ver main.py).
"""

from domain.case import Case
from infrastructure.case_repository import CaseRepository
from infrastructure.slack_client import SlackClient


class CaseChannelService:
    def __init__(self, repository: CaseRepository, slack_client: SlackClient):
        self._repository = repository
        self._slack_client = slack_client

    async def create_channel_for_case(self, case_id: str) -> Case:
        """
        Crea el canal de Slack para un caso (si todavía no tiene uno),
        postea la Description + comentarios existentes como mensaje
        inicial, y guarda el Id del canal en Salesforce.

        Es idempotente: si el caso ya tiene un `channel` asignado, no
        hace nada y lo devuelve tal cual — así un reintento del webhook
        de Salesforce no genera canales ni mensajes duplicados.
        """
        case = await self._repository.get_case(case_id)

        if case.channel:
            return case

        channel_name = f"caso-{case.case_number}"
        channel_id = await self._slack_client.create_channel(channel_name)

        comments = await self._repository.list_case_comments(case_id)
        await self._slack_client.post_message(channel_id, self._build_initial_message(case, comments))

        case.channel = channel_id
        await self._repository.save(case)
        return case

    @staticmethod
    def _build_initial_message(case: Case, comments: list[str]) -> str:
        description = case.description or "_Sin descripción_"
        if comments:
            comments_text = "\n".join(f"• {comment}" for comment in comments)
        else:
            comments_text = "_Sin comentarios previos_"

        return (
            f"📋 *Caso #{case.case_number} derivado a {case.branch}*\n\n"
            f"*Asunto:* {case.subject}\n\n"
            f"*Descripción:*\n{description}\n\n"
            f"*Comentarios previos:*\n{comments_text}"
        )