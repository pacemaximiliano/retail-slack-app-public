"""
Punto de entrada de la app.

Conecta Bolt (modo HTTP, sin Socket Mode) con FastAPI, arma las
dependencias (SalesforceClient -> CaseRepository -> CaseService) una
sola vez al arrancar, y registra los handlers de Slack:

- app_home_opened: publica el listado de casos de la sucursal del usuario
  (o de todas, si es superuser).
- view_case_detail (botón "Gestionar" del Home): abre el modal, en la
  pantalla que corresponda según el estado del caso.
- start_progress / show_close_case_form / show_derive_case_form /
  back_to_choice: navegan entre las pantallas del modal (Assigned to
  Branch -> In Progress -> elegir), con views.update, sin cerrar nunca
  el modal.
- close_case_modal / derive_case_modal (submit de las pantallas con
  campos): ejecutan el cierre o la derivación.
- derive_to_internal_team / finish_internal_work: acciones del modal de
  equipo interno (sin cambios en esta ronda).
- team_select_modal (submit del modal secundario): confirma a qué
  equipo derivar, desde el equipo interno.
- case_detail_modal (submit del modal, solo para los estados que no
  cambiaron): guarda el comentario, si se escribió alguno.
"""

import re

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
from views.case_detail_modal import (
    CALLBACK_ID,
    CLOSE_CASE_CALLBACK_ID,
    DERIVE_CASE_CALLBACK_ID,
    TEAM_SELECT_CALLBACK_ID,
    build_case_detail_modal,
    build_close_case_form,
    build_derive_case_form,
    build_in_progress_choice_screen,
    build_message_modal,
    build_team_select_modal,
)
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
_user_status_filter: dict[str, set[CaseStatus]] = {}


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

    selected_statuses = _user_status_filter.get(user_id, set())
    if selected_statuses:
        cases = [case for case in cases if case.status in selected_statuses]

    await client.views_publish(user_id=user_id, view=build_home_view(branch_label, cases, selected_statuses))


async def _notify_status_change(case, user_id: str) -> None:
    """Postea en el canal del caso que su estado cambió, si tiene canal."""
    if case.channel:
        status_label = format_status_label(case.status)
        await slack_client.post_message(
            case.channel, f"🔄 *Estado actualizado a:* {status_label}\n_por <@{user_id}>_"
        )


async def _post_comment_if_any(case_id: str, case, comment: str | None, user_id: str) -> None:
    """Guarda un comentario (si se escribió alguno) en Salesforce y lo postea al canal."""
    if not comment:
        return
    await case_service.add_comment(case_id, f"(Comentario agregado desde Slack)\n{comment}")
    if case.channel:
        await slack_client.post_message(case.channel, f"💬 *Comentario agregado por <@{user_id}>:*\n{comment}")


async def _run_case_action(ack, body, client, action_coro) -> None:
    """
    Helper compartido por los botones de acción simples del modal de
    equipo interno (Finalizar): ejecuta la transición, notifica al
    canal, y reemplaza el modal por uno de confirmación (o error).
    """
    await ack()
    user_id = body["user"]["id"]
    try:
        case = await action_coro()
    except InvalidCaseTransition as exc:
        await client.views_update(view_id=body["view"]["id"], view=build_message_modal(f"❌ {exc}"))
        return

    await _notify_status_change(case, user_id)
    await client.views_update(
        view_id=body["view"]["id"],
        view=build_message_modal(f"✅ Caso actualizado a *{format_status_label(case.status)}*."),
    )
    await _publish_home(client, user_id)


@slack_app.event("app_home_opened")
async def handle_app_home_opened(event, client):
    await _publish_home(client, event["user"])


@slack_app.action(re.compile(r"^filter_status_"))
async def handle_filter_status_button(ack, body, client):
    await ack()
    user_id = body["user"]["id"]
    selected_value = body["actions"][0]["value"]
    current = _user_status_filter.setdefault(user_id, set())

    if selected_value == "all":
        current.clear()
    else:
        status = CaseStatus(selected_value)
        if status in current:
            current.remove(status)
        else:
            current.add(status)

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


@slack_app.action("start_progress")
async def handle_start_progress(ack, body, client):
    """Assigned to Branch -> In Progress. No cierra el modal, pasa a la pantalla de elección."""
    await ack()
    case_id = body["view"]["private_metadata"]
    user_id = body["user"]["id"]

    try:
        case = await case_service.start_progress(case_id)
    except InvalidCaseTransition as exc:
        await client.views_update(view_id=body["view"]["id"], view=build_message_modal(f"❌ {exc}"))
        return

    await _notify_status_change(case, user_id)
    await client.views_update(view_id=body["view"]["id"], view=build_case_detail_modal(case))
    await _publish_home(client, user_id)


@slack_app.action("show_close_case_form")
async def handle_show_close_case_form(ack, body, client):
    await ack()
    case_id = body["view"]["private_metadata"]
    case = await case_service.get_case(case_id)
    await client.views_update(view_id=body["view"]["id"], view=build_close_case_form(case))


@slack_app.action("show_derive_case_form")
async def handle_show_derive_case_form(ack, body, client):
    await ack()
    case_id = body["view"]["private_metadata"]
    case = await case_service.get_case(case_id)
    await client.views_update(view_id=body["view"]["id"], view=build_derive_case_form(case))


@slack_app.action("back_to_choice")
async def handle_back_to_choice(ack, body, client):
    await ack()
    case_id = body["view"]["private_metadata"]
    case = await case_service.get_case(case_id)
    await client.views_update(view_id=body["view"]["id"], view=build_in_progress_choice_screen(case))


@slack_app.view(CLOSE_CASE_CALLBACK_ID)
async def handle_close_case_submission(ack, body, client, view):
    """Submit real del modal — Slack exige uno porque esta pantalla tiene un bloque `input`."""
    case_id = view["private_metadata"]
    user_id = body["user"]["id"]
    values = view["state"]["values"]
    comment = values.get("close_comment_block", {}).get("close_comment_input", {}).get("value")

    try:
        case = await case_service.close_case(case_id)
    except InvalidCaseTransition as exc:
        await ack(response_action="update", view=build_message_modal(f"❌ {exc}"))
        return

    await ack(response_action="update", view=build_message_modal("✅ Caso cerrado."))
    await _post_comment_if_any(case_id, case, comment, user_id)
    await _notify_status_change(case, user_id)
    await _publish_home(client, user_id)


@slack_app.view(DERIVE_CASE_CALLBACK_ID)
async def handle_derive_case_submission(ack, body, client, view):
    """
    Submit real del modal — el campo de equipo NO es opcional, así que
    Slack lo valida solo (error nativo en rojo) sin que tengamos que
    programarlo a mano.
    """
    case_id = view["private_metadata"]
    user_id = body["user"]["id"]
    values = view["state"]["values"]
    comment = values.get("derive_comment_block", {}).get("derive_comment_input", {}).get("value")
    team = values["derive_team_block"]["selected_team"]["selected_option"]["value"]

    try:
        case = await case_service.derive_to_internal_team(case_id, team)
    except InvalidCaseTransition as exc:
        await ack(response_action="update", view=build_message_modal(f"❌ {exc}"))
        return

    await ack(response_action="update", view=build_message_modal(f"✅ Caso derivado a *{team}*."))
    await _post_comment_if_any(case_id, case, comment, user_id)
    await _notify_status_change(case, user_id)
    await _publish_home(client, user_id)


@slack_app.action("derive_to_internal_team")
async def handle_derive_button(ack, body, client):
    """Desde el modal de equipo interno: abre el modal secundario para re-derivar a otro equipo."""
    await ack()
    case_id = body["view"]["private_metadata"]
    await client.views_push(trigger_id=body["trigger_id"], view=build_team_select_modal(case_id))


@slack_app.action("finish_internal_work")
async def handle_finish_internal_work(ack, body, client):
    case_id = body["view"]["private_metadata"]
    await _run_case_action(ack, body, client, lambda: case_service.finish_internal_work(case_id))


@slack_app.view(TEAM_SELECT_CALLBACK_ID)
async def handle_team_select_submission(ack, body, client, view):
    case_id = view["private_metadata"]
    user_id = body["user"]["id"]
    team = view["state"]["values"]["team_block"]["selected_team"]["selected_option"]["value"]

    try:
        case = await case_service.derive_to_internal_team(case_id, team)
    except InvalidCaseTransition as exc:
        await ack(response_action="errors", errors={"team_block": str(exc)})
        return

    await _notify_status_change(case, user_id)
    await ack(response_action="clear")  # cierra el modal secundario Y el principal
    await _publish_home(client, user_id)


@slack_app.view(CALLBACK_ID)
async def handle_case_detail_submission(ack, body, client, view):
    """Solo aplica a los estados sin cambios (equipo interno, terminales) — guarda el comentario."""
    values = view["state"]["values"]
    case_id = view["private_metadata"]
    user_id = body["user"]["id"]

    comment = None
    if "comment_block" in values:
        comment = values["comment_block"]["comment_input"].get("value")

    await ack()

    if comment:
        case = await case_service.get_case(case_id)
        await _post_comment_if_any(case_id, case, comment, user_id)


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
    Salesforce Channel in Slack, configurado como público) — acá solo
    posteamos el contexto inicial.

    Payload esperado: {"caseId": "500Hu00002XhkrQIAR", "channelId": "C0123ABCDEF"}
    (camelCase a propósito: nombres con guion bajo generan un bug de
    Salesforce al armar la clase Apex del External Service).
    """
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Webhook secret inválido")

    case_id = payload.get("caseId")
    channel_id = payload.get("channelId")
    if not case_id or not channel_id:
        raise HTTPException(status_code=400, detail="Falta 'caseId' o 'channelId' en el payload")

    await case_channel_service.post_initial_message(case_id, channel_id)
    return {"status": "ok"}


@api.on_event("shutdown")
async def shutdown():
    await salesforce_client.aclose()


if __name__ == "__main__":
    uvicorn.run(api, host="0.0.0.0", port=settings.port)