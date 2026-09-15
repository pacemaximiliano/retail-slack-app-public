"""
Caso de uso: postear el contexto inicial de un caso en su canal de Slack.

El canal en sí ya lo crea Salesforce (vía la action nativa "Create a
Salesforce Channel in Slack" en el Flow), que también guarda su Id en
Slack_Channel__c. Este servicio solo agrega el mensaje de contexto
(Description + comentarios existentes) — se dispara desde el webhook
que recibe el aviso de Salesforce (ver main.py).
"""

from domain.case import Case
from infrastructure.case_repository import CaseRepository
from infrastructure.slack_client import SlackClient


class CaseChannelService:
    def __init__(self, repository: CaseRepository, slack_client: SlackClient):
        self._repository = repository
        self._slack_client = slack_client

    async def post_initial_message(self, case_id: str, channel_id: str) -> Case:
        """
        Postea la Description + comentarios existentes de un caso en el
        canal que Salesforce ya creó. No valida si ya se posteó antes —
        si el Flow se dispara de nuevo para una re-derivación real, es
        correcto que se postee un mensaje de contexto nuevo.
        """
        case = await self._repository.get_case(case_id)
        comments = await self._repository.list_case_comments(case_id)
        await self._slack_client.post_message(channel_id, self._build_initial_message(case, comments))
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