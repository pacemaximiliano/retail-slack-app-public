"""
Punto de entrada de la app.

Conecta Bolt (modo HTTP, sin Socket Mode) con FastAPI, arma las
dependencias (SalesforceClient -> CaseRepository -> CaseService) una
sola vez al arrancar, y registra los handlers de Slack:

- app_home_opened: publica el listado de casos de la sucursal del usuario
  (o de todas, si es superuser).
- view_case_detail (botón): abre el modal de detalle de un caso.
- case_detail_modal (submit del modal): ejecuta la acción elegida y
  refresca el App Home.
"""

import uvicorn
from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.app.async_app import AsyncApp

from application.case_service import CaseService
from config.branch_mapping import get_branch_for_user, is_superuser
from config.settings import get_settings
from domain.case import InvalidCaseTransition
from infrastructure.case_repository import CaseRepository
from infrastructure.salesforce_client import SalesforceClient
from views.case_detail_modal import CALLBACK_ID, build_case_detail_modal
from views.home import build_home_view

settings = get_settings()

slack_app = AsyncApp(token=settings.slack.bot_token, signing_secret=settings.slack.signing_secret)

# Una sola instancia para toda la vida del proceso — se cierra en el
# shutdown de FastAPI, más abajo.
salesforce_client = SalesforceClient(settings.salesforce)
case_service = CaseService(CaseRepository(salesforce_client))


async def _publish_home(client, user_id: str) -> None:
    """Arma y publica el App Home para un usuario puntual."""
    if is_superuser(user_id):
        cases = await case_service.list_all_cases()
        branch_label = "Todas las sucursales"
    else:
        branch = get_branch_for_user(user_id)
        cases = await case_service.list_cases_for_branch(branch) if branch else []
        branch_label = branch or "Sin sucursal asignada"

    await client.views_publish(user_id=user_id, view=build_home_view(branch_label, cases))


@slack_app.event("app_home_opened")
async def handle_app_home_opened(event, client):
    await _publish_home(client, event["user"])


@slack_app.action("view_case_detail")
async def handle_view_case_detail(ack, body, client):
    await ack()
    case_id = body["actions"][0]["value"]
    case = await case_service.get_case(case_id)
    await client.views_open(trigger_id=body["trigger_id"], view=build_case_detail_modal(case))


@slack_app.view(CALLBACK_ID)
async def handle_case_detail_submission(ack, body, client, view):
    values = view["state"]["values"]
    action = values["action_block"]["selected_action"]["selected_option"]["value"]
    team_option = values.get("team_block", {}).get("selected_team", {}).get("selected_option")
    team = team_option["value"] if team_option else None
    case_id = view["private_metadata"]
    user_id = body["user"]["id"]

    try:
        if action == "start_progress":
            await case_service.start_progress(case_id)
        elif action == "derive_to_internal_team":
            if not team:
                await ack(
                    response_action="errors",
                    errors={"team_block": "Elegí un equipo interno para derivar el caso."},
                )
                return
            await case_service.derive_to_internal_team(case_id, team)
        elif action == "return_to_call_center":
            await case_service.return_to_call_center(case_id)
        elif action == "close_case":
            await case_service.close_case(case_id)
    except InvalidCaseTransition as exc:
        await ack(response_action="errors", errors={"action_block": str(exc)})
        return

    await ack()
    await _publish_home(client, user_id)


api = FastAPI()
handler = AsyncSlackRequestHandler(slack_app)


@api.post("/slack/events")
async def slack_events(req: Request):
    """Único endpoint que recibe TODO de Slack: eventos, botones y submits de modal."""
    return await handler.handle(req)


@api.get("/health")
async def health():
    return {"status": "ok"}


@api.on_event("shutdown")
async def shutdown():
    await salesforce_client.aclose()


if __name__ == "__main__":
    uvicorn.run(api, host="0.0.0.0", port=settings.port)