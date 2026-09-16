"""
Configuración central de la aplicación.

Todas las variables sensibles (tokens, secrets, credenciales) se leen
desde un archivo .env local (no versionado) usando pydantic-settings.
Nunca hardcodear valores acá — este archivo solo define la forma
y los nombres de las variables esperadas.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackSettings(BaseSettings):
    """Credenciales y configuración de la Slack App (modo HTTP, sin Socket Mode)."""

    model_config = SettingsConfigDict(env_prefix="SLACK_", env_file=".env", extra="ignore")

    bot_token: str = Field(..., description="xoxb-... token del bot, con permisos de chat:write, chat:write.public, etc.")
    signing_secret: str = Field(..., description="Signing Secret de la app, usado para verificar requests entrantes de Slack.")


class SalesforceSettings(BaseSettings):
    """Credenciales del usuario de servicio para Salesforce (OAuth Client Credentials Flow)."""

    model_config = SettingsConfigDict(env_prefix="SALESFORCE_", env_file=".env", extra="ignore")

    client_id: str = Field(..., description="Consumer Key del Connected App.")
    client_secret: str = Field(..., description="Consumer Secret del Connected App.")
    login_url: str = Field(default="https://login.salesforce.com", description="URL base de login (o my domain) usada para pedir el token OAuth.")
    api_version: str = Field(default="v61.0", description="Versión de la API REST de Salesforce a usar.")


class AppSettings(BaseSettings):
    """Configuración general del servicio (puerto, entorno, etc.)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = Field(default="development", description="development | staging | production")
    port: int = Field(default=8000, description="Puerto en el que corre el servidor FastAPI.")
    log_level: str = Field(default="INFO")
    webhook_secret: str = Field(
        ...,
        description="Secreto compartido para verificar que el webhook de Salesforce sea legítimo.",
    )

    slack: SlackSettings = Field(default_factory=SlackSettings)
    salesforce: SalesforceSettings = Field(default_factory=SalesforceSettings)


@lru_cache
def get_settings() -> AppSettings:
    """
    Punto único de acceso a la configuración en toda la app.
    Cacheada para no re-leer el .env en cada request.

    Uso:
        from config.settings import get_settings
        settings = get_settings()
        settings.slack.bot_token
    """
    return AppSettings()