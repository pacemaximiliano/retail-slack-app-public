"""
Cliente de bajo nivel para la API REST de Salesforce.

Se encarga únicamente de autenticación (OAuth 2.0 Client Credentials Flow)
y de las llamadas HTTP genéricas contra la API REST. No conoce nada del
dominio (Case, etc.) — eso lo resuelve `infrastructure/case_repository.py`
en el próximo paso, usando este cliente como base.
"""

import httpx

from config.settings import SalesforceSettings


class SalesforceAuthError(Exception):
    """Falló la autenticación contra Salesforce."""


class SalesforceApiError(Exception):
    """La API de Salesforce devolvió un error (4xx/5xx) en una operación puntual."""


class SalesforceClient:
    def __init__(self, settings: SalesforceSettings):
        self._settings = settings
        self._access_token: str | None = None
        self._instance_url: str | None = None
        self._http = httpx.AsyncClient(timeout=10.0)

    async def _authenticate(self) -> None:
        """Pide un access_token nuevo vía Client Credentials Flow."""
        token_url = f"{self._settings.login_url}/services/oauth2/token"
        response = await self._http.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.client_id,
                "client_secret": self._settings.client_secret,
            },
        )
        if response.status_code != 200:
            raise SalesforceAuthError(
                f"No se pudo autenticar contra Salesforce ({response.status_code}): {response.text}"
            )
        data = response.json()
        self._access_token = data["access_token"]
        self._instance_url = data["instance_url"]

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """
        Hace un request autenticado a la API REST de Salesforce.
        Si el token no existe o expiró (401), (re)autentica y reintenta una vez.
        `path` es relativo, ej. "/services/data/v61.0/sobjects/Case/500...".
        """
        if self._access_token is None:
            await self._authenticate()

        url = f"{self._instance_url}{path}"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        response = await self._http.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
            await self._authenticate()
            headers = {"Authorization": f"Bearer {self._access_token}"}
            response = await self._http.request(method, url, headers=headers, **kwargs)

        return response

    async def query(self, soql: str) -> dict:
        """Ejecuta una consulta SOQL. Devuelve el JSON crudo de Salesforce."""
        path = f"/services/data/{self._settings.api_version}/query"
        response = await self._request("GET", path, params={"q": soql})
        self._raise_if_error(response)
        return response.json()

    async def get_sobject(self, object_name: str, record_id: str) -> dict:
        """Obtiene un registro puntual por Id, ej. get_sobject('Case', '500...')."""
        path = f"/services/data/{self._settings.api_version}/sobjects/{object_name}/{record_id}"
        response = await self._request("GET", path)
        self._raise_if_error(response)
        return response.json()

    async def create_sobject(self, object_name: str, fields: dict) -> str:
        """Crea un registro nuevo. Devuelve el Id generado por Salesforce."""
        path = f"/services/data/{self._settings.api_version}/sobjects/{object_name}"
        response = await self._request("POST", path, json=fields)
        self._raise_if_error(response)
        return response.json()["id"]

    async def update_sobject(self, object_name: str, record_id: str, fields: dict) -> None:
        """Actualiza campos puntuales de un registro (PATCH parcial)."""
        path = f"/services/data/{self._settings.api_version}/sobjects/{object_name}/{record_id}"
        response = await self._request("PATCH", path, json=fields)
        self._raise_if_error(response)

    @staticmethod
    def _raise_if_error(response: httpx.Response) -> None:
        """
        Si la respuesta es un error, incluye el body real de Salesforce en la
        excepción — httpx.raise_for_status() por sí solo no lo muestra, y ese
        body es donde Salesforce explica la causa real (errorCode + message).
        """
        if response.status_code not in (200, 201, 204):
            raise SalesforceApiError(
                f"Error de Salesforce ({response.status_code}) en {response.request.url}: {response.text}"
            )

    async def aclose(self) -> None:
        """Cierra la conexión HTTP subyacente. Llamar al apagar la app."""
        await self._http.aclose()