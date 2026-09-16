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
        # Cliente separado con User Token — las APIs admin.* de Slack
        # rechazan Bot Tokens sin importar el scope (error 'not_allowed_token_type').
        self._admin_client = AsyncWebClient(token=settings.admin_user_token)
        self._bot_user_id: str | None = None

    async def _get_bot_user_id(self) -> str:
        """Resuelve (y cachea) el Id de usuario del propio bot."""
        if self._bot_user_id is None:
            response = await self._client.auth_test()
            self._bot_user_id = response["user_id"]
        return self._bot_user_id

    async def ensure_bot_in_channel(self, channel_id: str) -> None:
        """
        Se invita a sí mismo (el bot) a un canal, vía la API de administrador
        de Enterprise Grid (admin.conversations.invite) — hace falta porque
        los Salesforce Channels no agregan al bot como miembro por defecto,
        y Slack no deja que un bot se sume solo a un canal privado sin
        haber sido invitado. Usa el User Token de admin, no el Bot Token.
        """
        bot_user_id = await self._get_bot_user_id()
        try:
            await self._admin_client.admin_conversations_invite(channel_id=channel_id, user_ids=[bot_user_id])
        except SlackApiError as exc:
            # Si ya es miembro (ej. un reintento), no es un error real.
            if exc.response.get("error") != "already_in_channel":
                raise

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