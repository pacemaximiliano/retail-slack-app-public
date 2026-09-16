"""
Caso de uso: postear el contexto inicial de un caso en su canal de Slack.

El canal en sí ya lo crea Salesforce (action nativa "Create a Salesforce
Channel in Slack"), configurada como pública a nivel organización — por
eso no hace falta invitar al bot ni usar ninguna API de admin: alcanza
con el scope chat:write.public para postear directo. Se dispara desde
el webhook que recibe el aviso de Salesforce (ver main.py).
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
        canal (público) que Salesforce ya creó y vinculó al registro.
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