"""
Cliente de bajo nivel para la Web API de Slack (creación de canales,
mensajes). Independiente de Bolt — lo usa tanto `application/` (para
crear el canal de un caso) como `main.py` (para postear comentarios
desde el modal).
"""

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from config.settings import SlackSettings


class SlackClient:
    def __init__(self, settings: SlackSettings):
        self._client = AsyncWebClient(token=settings.bot_token)

    async def create_channel(self, name: str) -> str:
        """
        Crea un canal público y devuelve su Id.
        Si ya existe uno con ese nombre (ej. por un reintento del webhook
        de Salesforce), devuelve el Id del existente en vez de fallar.
        """
        try:
            response = await self._client.conversations_create(name=name)
            return response["channel"]["id"]
        except SlackApiError as exc:
            if exc.response.get("error") == "name_taken":
                return await self._find_channel_id_by_name(name)
            raise

    async def _find_channel_id_by_name(self, name: str) -> str:
        cursor = None
        while True:
            response = await self._client.conversations_list(cursor=cursor, limit=200)
            for channel in response["channels"]:
                if channel["name"] == name:
                    return channel["id"]
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                raise ValueError(f"No se encontró un canal llamado '{name}' a pesar de 'name_taken'.")

    async def post_message(self, channel_id: str, text: str) -> None:
        """Postea un mensaje de texto simple (mrkdwn) en un canal."""
        await self._client.chat_postMessage(channel=channel_id, text=text, mrkdwn=True)