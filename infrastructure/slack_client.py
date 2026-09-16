"""
Cliente de bajo nivel para la Web API de Slack (mensajes). Independiente
de Bolt — lo usa tanto `application/` (para postear el contexto inicial
de un caso) como `main.py` (para postear comentarios desde el modal).
"""

from slack_sdk.web.async_client import AsyncWebClient

from config.settings import SlackSettings


class SlackClient:
    def __init__(self, settings: SlackSettings):
        self._client = AsyncWebClient(token=settings.bot_token)

    async def post_message(self, channel_id: str, text: str) -> None:
        """
        Postea un mensaje de texto simple (mrkdwn) en un canal.
        Funciona sin que el bot sea miembro del canal, gracias al scope
        chat:write.public — necesario porque los canales los crea
        Salesforce (Create a Salesforce Channel in Slack), no nosotros.
        """
        await self._client.chat_postMessage(channel=channel_id, text=text, mrkdwn=True)