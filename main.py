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
from fastapi import FastAPI, Header, HTTPException, Request
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.app.async_app import AsyncApp

from application.case_channel_service import CaseChannelService
from application.case_service import CaseService
from config.branch_mapping import get_branch_for_user, get_team_for_user, is_superuser
from config.settings import get_settings
from domain.case import CaseStatus, InvalidCaseTransition
from infrastructure.case_repository import CaseRepository
from infrastructure.salesforce_client import SalesforceClient
from infrastructure.slack_client import SlackClient
from views.case_detail_modal import CALLBACK_ID, build_case_detail_modal
from views.home import build_home_view, format_status_label

settings = get_settings()

slack_app = AsyncApp(token=settings.slack.bot_token, signing_secret=settings.slack.signing_secret)

# Una sola instancia de cada cliente/repositorio para toda la vida del
# proceso — se cierra en el shutdown de FastAPI, más abajo.
salesforce_client = SalesforceClient(settings.salesforce)
slack_client = SlackClient(settings.slack)
case_repository = CaseRepository(salesforce_client)
case_service = CaseService(case_repository)
case_channel_service = CaseChannelService(case_repository, slack_client)

# Filtro de estado por usuario, solo en memoria — se resetea si el
# proceso reinicia. Alcanza para la demo, no hace falta una DB para esto.
_user_status_filter: dict[str, CaseStatus | None] = {}


async def _publish_home(client, user_id: str) -> None:
    """Arma y publica el App Home para un usuario puntual, aplicando su filtro de estado si tiene uno."""
    if is_superuser(user_id):
        cases = await case_service.list_all_cases()
        branch_label = "Todas las sucursales"
    else:
        team = get_team_for_user(user_id)
        if team:
            cases = await case_service.list_cases_for_team(team)
            branch_label = f"Equipo {team}"
        else:
            branch = get_branch_for_user(user_id)
            cases = await case_service.list_cases_for_branch(branch) if branch else []
            branch_label = branch or "Sin sucursal asignada"

    selected_status = _user_status_filter.get(user_id)
    if selected_status is not None:
        cases = [case for case in cases if case.status == selected_status]

    await client.views_publish(user_id=user_id, view=build_home_view(branch_label, cases, selected_status))


@slack_app.event("app_home_opened")
async def handle_app_home_opened(event, client):
    await _publish_home(client, event["user"])


@slack_app.action("filter_status")
async def handle_filter_status(ack, body, client):
    await ack()
    user_id = body["user"]["id"]
    selected_value = body["actions"][0]["selected_option"]["value"]
    _user_status_filter[user_id] = None if selected_value == "all" else CaseStatus(selected_value)
    await _publish_home(client, user_id)


@slack_app.action("refresh_home")
async def handle_refresh_home(ack, body, client):
    await ack()
    await _publish_home(client, body["user"]["id"])


@slack_app.action("view_case_detail")
async def handle_view_case_detail(ack, body, client):
    await ack()
    case_id = body["actions"][0]["value"]
    case = await case_service.get_case(case_id)
    await client.views_open(trigger_id=body["trigger_id"], view=build_case_detail_modal(case))


@slack_app.view(CALLBACK_ID)
async def handle_case_detail_submission(ack, body, client, view):
    values = view["state"]["values"]
    case_id = view["private_metadata"]
    user_id = body["user"]["id"]

    action = None
    if "action_block" in values:
        selected = values["action_block"]["selected_action"].get("selected_option")
        action = selected["value"] if selected else None

    team = None
    if "team_block" in values:
        selected_team = values["team_block"]["selected_team"].get("selected_option")
        team = selected_team["value"] if selected_team else None

    comment = None
    if "comment_block" in values:
        comment = values["comment_block"]["comment_input"].get("value")

    if action == "derive_to_internal_team" and not team:
        await ack(
            response_action="errors",
            errors={"team_block": "Elegí un equipo interno para derivar el caso."},
        )
        return

    try:
        if action == "start_progress":
            await case_service.start_progress(case_id)
        elif action == "derive_to_internal_team":
            await case_service.derive_to_internal_team(case_id, team)
        elif action == "return_to_call_center":
            await case_service.return_to_call_center(case_id)
        elif action == "close_case":
            await case_service.close_case(case_id)
    except InvalidCaseTransition as exc:
        await ack(response_action="errors", errors={"action_block": str(exc)})
        return

    if comment or action:
        case = await case_service.get_case(case_id)
        if action:
            status_label = format_status_label(case.status)
            if case.channel:
                await slack_client.post_message(
                    case.channel, f"🔄 *Estado actualizado a:* {status_label}\n_por <@{user_id}>_"
                )
        if comment:
            await case_service.add_comment(case_id, f"(Comentario agregado desde Slack)\n{comment}")
            if case.channel:
                await slack_client.post_message(
                    case.channel, f"💬 *Comentario agregado por <@{user_id}>:*\n{comment}"
                )

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


@api.post("/salesforce/webhook")
async def salesforce_webhook(payload: dict, x_webhook_secret: str = Header(default=None)):
    """
    Recibe el aviso del Flow de Salesforce cuando un caso pasa a
    'Assigned to Branch'. El canal ya lo creó Salesforce (Create a
    Salesforce Channel in Slack) — acá solo posteamos el contexto inicial.

    Payload esperado: {"case_id": "500Hu00002XhkrQIAR", "channel_id": "C0123ABCDEF"}
    """
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Webhook secret inválido")

    case_id = payload.get("case_id")
    channel_id = payload.get("channel_id")
    if not case_id or not channel_id:
        raise HTTPException(status_code=400, detail="Falta 'case_id' o 'channel_id' en el payload")

    await case_channel_service.post_initial_message(case_id, channel_id)
    return {"status": "ok"}


@api.on_event("shutdown")
async def shutdown():
    await salesforce_client.aclose()


if __name__ == "__main__":
    uvicorn.run(api, host="0.0.0.0", port=settings.port)